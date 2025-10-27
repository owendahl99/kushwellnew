
from __future__ import annotations
from typing import Any, Dict, Tuple, Optional
from dataclasses import dataclass
from flask import current_app
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import User

# Optional tables; we guard access dynamically:
# - WellnessCheck (overall_qol, checkin_date)
# - Upvote (qol_improvement for products)
# - Product
# - PatientProfile, PatientPreference
# - Friends / Follow


def _is_friend(viewer_id: int, owner_id: int) -> bool:
    """
    Determine if viewer and owner are 'friends' (or following) per your schema.
    Tries Friends, then Follow; falls back to False.
    """
    try:
        from app.models import Friends
        if Friends.query.filter(
            ((Friends.user_id == viewer_id) & (Friends.friend_id == owner_id)) |
            ((Friends.user_id == owner_id) & (Friends.friend_id == viewer_id))
        ).first():
            return True
    except Exception:
        pass

    try:
        from app.models import Follow
        if Follow.query.filter_by(follower_id=viewer_id, target_id=owner_id).first():
            return True
    except Exception:
        pass

    return False


def _visible(privacy: dict, key: str, viewer_is_friend: bool) -> bool:
    vis = (privacy or {}).get("visibility", {})
    level = (vis.get(key) or "private").lower()
    if level == "public":
        return True
    if level == "friends" and viewer_is_friend:
        return True
    return False


def _display_name(user: User, viewer_is_friend: bool) -> str:
    pref = getattr(user, "preferred_display", "real")
    alias_on = bool(getattr(user, "alias_public_on", False))
    alias = getattr(user, "alias_name", None)
    real = getattr(user, "name", None) or getattr(user, "email", f"User {user.id}")
    if pref == "alias" and alias_on and alias:
        return alias
    return real


def _latest_qol(user: User) -> Optional[float]:
    try:
        from app.models import WellnessCheck
    except Exception:
        return None

    row = (
        WellnessCheck.query
        .filter_by(sid=getattr(user, "sid", None))
        .order_by(WellnessCheck.checkin_date.desc())
        .first()
    )
    return getattr(row, "overall_qol", None) if row else None


def _top_products(user: User, limit: int = 6) -> list[dict]:
    try:
        from app.models import Upvote, Product
    except Exception:
        return []

    q = (
        db.session.query(
            Product.id,
            Product.name,
            func.avg(Upvote.qol_improvement).label("avg_qol"),
            func.count(Upvote.id).label("votes"),
        )
        .join(Upvote, (Upvote.target_id == Product.id) & (Upvote.target_type == "product"))
        .filter(Upvote.user_id == user.id)
        .group_by(Product.id, Product.name)
        .order_by(func.coalesce(func.avg(Upvote.qol_improvement), 0).desc(), func.count(Upvote.id).desc())
        .limit(limit)
    )
    rows = q.all()
    return [{"id": r.id, "name": r.name, "avg_qol": float(r.avg_qol or 0.0), "votes": int(r.votes or 0)} for r in rows]


def _afflictions(user: User) -> list[dict]:
    try:
        from app.models import PatientCondition
    except Exception:
        return []
    # Assume PatientCondition rows linked to patient via patient_profile
    pid = getattr(getattr(user, "patient_profile", None), "id", None) or getattr(getattr(user, "patient_profile", None), "sid", None)
    if not pid:
        return []
    rows = (
        PatientCondition.query
        .filter((PatientCondition.patient_id == pid) | (getattr(PatientCondition, "sid", None) == pid))
        .order_by(PatientCondition.id.desc())
        .limit(50)
        .all()
    )
    return [{"id": getattr(r, "id", None), "name": getattr(r, "condition_name", getattr(r, "name", None)), "severity": getattr(r, "severity", None)} for r in rows]


def build_public_profile(viewer: Optional[User], alias_slug: str) -> Tuple[dict, int]:
    """
    Assemble a privacy-safe public profile JSON for /patients/<alias_slug>.
    """
    owner: User = User.query.filter_by(alias_slug=alias_slug).first()
    if not owner:
        return {"error": "Not found"}, 404

    viewer_is_friend = False
    if viewer and getattr(viewer, "id", None) and getattr(owner, "id", None):
        viewer_is_friend = _is_friend(viewer.id, owner.id)

    privacy = getattr(owner, "privacy", {}) or {}
    data: dict = {
        "alias_slug": alias_slug,
        "display_name": _display_name(owner, viewer_is_friend),
        "avatar_initial": (getattr(owner, "alias_name", "")[:1] or getattr(owner, "name", "")[:1] or "?").upper(),
        "sections": {}
    }

    # Identity
    if _visible(privacy, "alias", viewer_is_friend):
        data["sections"]["alias"] = getattr(owner, "alias_name", None)

    if _visible(privacy, "real_name", viewer_is_friend):
        data["sections"]["real_name"] = getattr(owner, "name", None)

    # DOB
    if _visible(privacy, "date_of_birth", viewer_is_friend):
        dob = getattr(owner, "date_of_birth", None)
        data["sections"]["date_of_birth"] = str(dob) if dob else None

    # Afflictions
    if _visible(privacy, "afflictions", viewer_is_friend):
        data["sections"]["afflictions"] = _afflictions(owner)

    # QoL (latest only; no formulas exposed)
    if _visible(privacy, "qol_scores", viewer_is_friend):
        data["sections"]["qol_summary"] = {"latest_overall_qol": _latest_qol(owner)}

    # Preferences (strain/application if available via PatientPreference)
    try:
        pref = getattr(getattr(owner, "patient_profile", None), "preference", None)
        if pref and _visible(privacy, "favorites", viewer_is_friend):
            data["sections"]["preferences"] = {
                "strain_type": getattr(pref, "strain_type", None),
                "application_method": getattr(pref, "application_method", None),
            }
    except Exception:
        pass

    # Top products the patient engaged with (via Upvotes)
    if _visible(privacy, "favorites", viewer_is_friend):
        data["sections"]["top_products"] = _top_products(owner, limit=6)

    # Follower / friend counters (if you expose them)
    try:
        from app.models import Friends
        friends_count = db.session.query(func.count(Friends.id)).filter(
            (Friends.user_id == owner.id) | (Friends.friend_id == owner.id)
        ).scalar() or 0
    except Exception:
        friends_count = None

    data["meta"] = {
        "viewer_is_friend": viewer_is_friend,
        "friends_count": friends_count
    }

    return data, 200
