# app/services/security.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, Optional, Literal
from app.extensions import db
from flask_login import current_user

def effective_display_name(user=None):
    from app.models import User  # lazy import to avoid circular dependency
    user = user or current_user
    return user.display_name or user.username

def can_view(obj):
    from app.models import User  # same here
    user = current_user
    if user.is_admin:
        return True
    # whatever logic you already had here
    return getattr(obj, "owner_id", None) == user.id



PRIVATE  = "private"
FRIENDS  = "friends"
PUBLIC   = "public"
ALLOWED  = {PRIVATE, FRIENDS, PUBLIC}

DEFAULT_VISIBILITY: Dict[str, str] = {
    "alias": FRIENDS,
    "real_name": PRIVATE,
    "date_of_birth": PRIVATE,
    "recommendations": FRIENDS,
    "qol_scores": PRIVATE,
    "afflictions": FRIENDS,
    "afflictions_over_time": PRIVATE,
    "favorite_dispensary": FRIENDS,
    "favorites": FRIENDS,
    "voting_history": PRIVATE,
}

DEFAULT_SETTINGS: Dict[str, Any] = {
    "alias": "",
    "preferred_display": "alias",  # 'alias' | 'real'
    "discoverable": {              # explicit, required
        "by_name": False,
        "by_alias": True,
    },
    "visibility": DEFAULT_VISIBILITY.copy(),
}

@dataclass
class PrivacySettings:
    alias: str
    preferred_display: str
    discoverable_by_name: bool
    discoverable_by_alias: bool
    visibility: Dict[str, str]

def _merge_settings(raw: Optional[dict]) -> PrivacySettings:
    raw = raw or {}
    vis = DEFAULT_VISIBILITY.copy()
    vis.update(raw.get("visibility") or {})
    vis = {k: (v if v in ALLOWED else DEFAULT_VISIBILITY[k]) for k, v in vis.items()}

    disc = raw.get("discoverable") or {}
    by_name  = bool(disc.get("by_name", DEFAULT_SETTINGS["discoverable"]["by_name"]))
    by_alias = bool(disc.get("by_alias", DEFAULT_SETTINGS["discoverable"]["by_alias"]))

    alias = (raw.get("alias") or "").strip()
    pref  = (raw.get("preferred_display") or "alias").strip().lower()
    if pref not in ("alias","real"):
        pref = "alias"

    return PrivacySettings(
        alias=alias,
        preferred_display=pref,
        discoverable_by_name=by_name,
        discoverable_by_alias=by_alias,
        visibility=vis,
    )

def get_privacy(user_id: int) -> Dict[str, Any]:
    u = db.session.get(User, user_id)
    if not u:
        return DEFAULT_SETTINGS.copy()
    ps = _merge_settings(getattr(u, "privacy", None))
    return {
        "alias": ps.alias,
        "preferred_display": ps.preferred_display,
        "discoverable": {
            "by_name": ps.discoverable_by_name,
            "by_alias": ps.discoverable_by_alias,
        },
        "visibility": ps.visibility,
    }

def set_privacy(user_id: int, payload: dict) -> tuple[bool, str]:
    u = db.session.get(User, user_id)
    if not u:
        return False, "User not found."
    ps = _merge_settings(payload)
    u.privacy = {
        "alias": ps.alias,
        "preferred_display": ps.preferred_display,
        "discoverable": {
            "by_name": ps.discoverable_by_name,
            "by_alias": ps.discoverable_by_alias,
        },
        "visibility": ps.visibility,
    }
    try:
        db.session.add(u); db.session.commit()
        return True, "Security & sharing settings saved."
    except Exception as e:
        db.session.rollback()
        return False, f"Save failed: {e}"

# -------------------------- Viewer / Access Logic -----------------------------
def _is_friend(owner_id: int, viewer_id: Optional[int]) -> bool:
    if not viewer_id:
        return False
    if owner_id == viewer_id:
        return True
    try:
        from app.services.friends import is_friend as svc_is_friend
        return bool(svc_is_friend(owner_id, viewer_id))
    except Exception:
        # Fail safe: if friend service unavailable, treat as not friends
        return False

def can_view(owner: User, viewer_id: Optional[int], field_key: str) -> bool:
    """
    Tri-state gate for a single field ('alias', 'real_name', etc.) based on owner's privacy.
    Self can always view.
    """
    if viewer_id == getattr(owner, "id", None):
        return True  # self
    ps = _merge_settings(getattr(owner, "privacy", None))
    level = ps.visibility.get(field_key, PRIVATE)
    if level == PUBLIC:
        return True
    if level == FRIENDS and _is_friend(owner.id, viewer_id):
        return True
    return False

def _alias_value(owner: User) -> Optional[str]:
    """
    Where to read alias from. First the new privacy JSON, then PatientProfile.alias if present.
    (No legacy alias_* columns used.)
    """
    ps = _merge_settings(getattr(owner, "privacy", None))
    alias = (ps.alias or "").strip()
    if alias:
        return alias
    prof = getattr(owner, "patient_profile", None)
    if prof:
        a = (getattr(prof, "alias", None) or "").strip()
        return a or None
    return None

def _real_name_value(owner: User) -> Optional[str]:
    """
    Structured first/last if available via PatientProfile, else owner's legal_name().
    """
    prof = getattr(owner, "patient_profile", None)
    if prof:
        first = (getattr(prof, "first_name", None) or "").strip()
        last  = (getattr(prof, "last_name",  None) or "").strip()
        nm = f"{first} {last}".strip()
        if nm:
            return nm
    # fall back to model helper
    try:
        nm = owner.legal_name()
        return nm.strip() or None
    except Exception:
        return None

def effective_display_name(owner: User, viewer_id: Optional[int] = None) -> str:
    """
    Return the string the viewer should see, honoring per-field visibility.
    Prefers alias when visible & present, otherwise real name when visible, otherwise 'Hidden'.
    """
    if can_view(owner, viewer_id, "alias"):
        alias = _alias_value(owner)
        if alias:
            return alias

    if can_view(owner, viewer_id, "real_name"):
        real = _real_name_value(owner)
        if real:
            return real

    # Self always sees something (real name fallback)
    if viewer_id == getattr(owner, "id", None):
        return _real_name_value(owner) or "Hidden"

    return "Hidden"

def is_discoverable(owner: User, channel: Literal["by_name", "by_alias"]) -> bool:
    """
    Convenience used by search: true if this user allows discovery via the given channel.
    """
    ps = _merge_settings(getattr(owner, "privacy", None))
    if channel == "by_name":
        return bool(ps.discoverable_by_name)
    if channel == "by_alias":
        return bool(ps.discoverable_by_alias)
    return False
    


