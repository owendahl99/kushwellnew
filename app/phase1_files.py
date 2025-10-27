# build_phase1_files.py
# Phase 1 builder: Patient Record + Public Patient Profile (privacy-aware)
# Run once from your repo root:  python build_phase1_files.py
from __future__ import annotations
import os, sys, json, textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP  = ROOT / "app"

# ------------------------------------------------------------
# File payloads (production-ready)
# ------------------------------------------------------------

FILES: dict[str, str] = {}

# 1) SERVICES: patient_record_service.py
FILES["app/services/patient_record_service.py"] = r'''
from __future__ import annotations
from datetime import datetime, date
from typing import Any, Dict, Tuple, Optional, Iterable

from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from app.extensions import db
from app.models import User

# Optional models that may exist in your schema.
# We import lazily inside functions to avoid hard failures in case of minor model naming differences.
# Expected useful models:
#  - PatientProfile
#  - PatientPreference
#  - PatientCondition (afflictions)
#  - Medication / MedicalRecord (if present)


def _commit_safely() -> Tuple[bool, Optional[str]]:
    try:
        db.session.commit()
        return True, None
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception("[patient_record_service] DB error")
        return False, str(e)


def _set_if_has(obj, field: str, value: Any):
    """Set attribute only if model has field; avoid AttributeError on variant schemas."""
    if hasattr(obj, field):
        setattr(obj, field, value)


# -----------------------------
# Account / Identity
# -----------------------------
def update_account(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    """
    Update top-level account fields on User and linked PatientProfile where applicable.
    Expected fields: name, email, alias, password, zip_code
    """
    alias = (form.get("alias") or "").strip() or None
    name = (form.get("name") or "").strip() or None
    email = (form.get("email") or "").strip() or None
    zip_code = (form.get("zip_code") or "").strip() or None
    new_password = form.get("password") or None

    if alias:
        _set_if_has(user, "alias_name", alias)

    if name:
        _set_if_has(user, "name", name)

    if email:
        _set_if_has(user, "email", email)

    if zip_code:
        _set_if_has(user, "zip_code", zip_code)

    if new_password:
        # assume User model exposes set_password
        try:
            if hasattr(user, "set_password"):
                user.set_password(new_password)
            else:
                _set_if_has(user, "password", new_password)  # worst-case
        except Exception:
            current_app.logger.exception("[patient_record_service] set_password failed")
            return {"error": "Could not set password."}, 400

    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500
    return {"message": "Account updated."}, 200


# -----------------------------
# Preferences
# -----------------------------
def update_preferences(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    """
    Update patient preferences record.
    Fields expected in template: preferred_dispensary, preferred_providers[], preferred_manufacturers[]
    """
    from app.models import PatientProfile, PatientPreference

    profile = getattr(user, "patient_profile", None)
    if not profile:
        return {"error": "Patient profile not found."}, 404

    # get or create PatientPreference
    pref = getattr(profile, "preference", None)
    if pref is None and hasattr(PatientPreference, "__table__"):
        pref = PatientPreference(patient_id=getattr(profile, "sid", None) or getattr(profile, "id", None))
        db.session.add(pref)

    # Map fields safely
    _set_if_has(pref, "preferred_dispensary", form.get("preferred_dispensary") or None)

    # Multi-select lists may arrive as comma-str or multiple form values
    providers = form.getlist("preferred_providers") if hasattr(form, "getlist") else form.get("preferred_providers")
    manufacturers = form.getlist("preferred_manufacturers") if hasattr(form, "getlist") else form.get("preferred_manufacturers")

    # normalize -> list of ids or strings
    def norm_list(v):
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return [str(x) for x in v if str(x).strip()]
        s = str(v).strip()
        if not s:
            return []
        return [x.strip() for x in s.split(",") if x.strip()]

    _set_if_has(pref, "provider_preferences", norm_list(providers))
    _set_if_has(pref, "manufacturer_preferences", norm_list(manufacturers))

    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500
    return {"message": "Preferences updated."}, 200


# -----------------------------
# Demographics & Health
# -----------------------------
def update_demographics(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    """
    Update demographics on PatientProfile: sex, address, city, state, country, height/weight.
    """
    from app.models import PatientProfile

    profile = getattr(user, "patient_profile", None)
    if not profile:
        return {"error": "Patient profile not found."}, 404

    # Map expected fields if present on model
    for k in ["sex", "address", "city", "state", "country"]:
        _set_if_has(profile, k, (form.get(k) or "").strip() or None)

    def to_int(v, lo=None, hi=None):
        try:
            if v in (None, ""): return None
            iv = int(v)
            if lo is not None and iv < lo: return None
            if hi is not None and iv > hi: return None
            return iv
        except Exception:
            return None

    def to_float(v):
        try:
            if v in (None, ""): return None
            return float(v)
        except Exception:
            return None

    _set_if_has(profile, "height_feet",  to_int(form.get("height_feet"), 0, 8))
    _set_if_has(profile, "height_inches",to_int(form.get("height_inches"), 0, 11))
    _set_if_has(profile, "weight_lbs",   to_float(form.get("weight_lbs")))

    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500
    return {"message": "Demographics updated."}, 200


# -----------------------------
# Cannabis Use
# -----------------------------
def update_cannabis(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    """
    Update cannabis use details on PatientProfile.
    Fields: cannabis_use_start_age, cannabis_use_frequency, cannabis_use_characterization
    """
    from app.models import PatientProfile

    profile = getattr(user, "patient_profile", None)
    if not profile:
        return {"error": "Patient profile not found."}, 404

    def to_int(v):
        try:
            if v in (None, ""): return None
            return int(v)
        except Exception:
            return None

    _set_if_has(profile, "cannabis_use_start_age", to_int(form.get("cannabis_use_start_age")))
    _set_if_has(profile, "cannabis_use_frequency", (form.get("cannabis_use_frequency") or "").strip() or None)
    _set_if_has(profile, "cannabis_use_characterization", (form.get("cannabis_use_characterization") or "").strip() or None)

    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500
    return {"message": "Cannabis use updated."}, 200


# -----------------------------
# Medical History (basic scaffold with safety)
# -----------------------------
def update_history(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    """
    Persist basic patient history entry (condition/diagnosis date/status/notes).
    If you have richer models (e.g., Condition entries), insert one row.
    """
    try:
        from app.models import PatientCondition, PatientProfile
    except Exception:
        PatientCondition = None

    profile = getattr(user, "patient_profile", None)
    if not profile:
        return {"error": "Patient profile not found."}, 404

    # If a dedicated PatientCondition model exists, create a row; else, write to profile notes if available.
    if PatientCondition is not None:
        entry = PatientCondition(
            patient_id=getattr(profile, "sid", None) or getattr(profile, "id", None),
            condition_name=(form.get("condition_name") or "").strip() or None,
            diagnosis_date=(form.get("diagnosis_date") or None),
            status=(form.get("status") or "").strip() or None,
            notes=(form.get("notes") or "").strip() or None,
        )
        db.session.add(entry)
    else:
        # fallback: append to profile.notes if present
        raw = f"{datetime.utcnow().isoformat()} :: {form.get('condition_name','')} :: {form.get('status','')} :: {form.get('notes','')}"
        if hasattr(profile, "notes") and isinstance(profile.notes, str):
            profile.notes = (profile.notes or "") + "\n" + raw

    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500
    return {"message": "Medical history updated."}, 200


# -----------------------------
# Afflictions (add/remove)
# -----------------------------
def add_affliction(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    """
    Add an affliction (name + severity). Returns new row data for JS append.
    """
    try:
        from app.models import PatientCondition, PatientProfile
    except Exception:
        return {"error": "Affliction model not available."}, 500

    profile = getattr(user, "patient_profile", None)
    if not profile:
        return {"error": "Patient profile not found."}, 404

    name = (form.get("name") or "").strip()
    severity = (form.get("severity") or "").strip()
    if not name or not severity:
        return {"error": "Name and severity are required."}, 400

    row = PatientCondition(
        patient_id=getattr(profile, "sid", None) or getattr(profile, "id", None),
        condition_name=name,
        severity=severity
    )
    db.session.add(row)
    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500

    return {"id": getattr(row, "id", None), "name": name, "severity": severity}, 200


def remove_affliction(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    try:
        from app.models import PatientCondition
    except Exception:
        return {"error": "Affliction model not available."}, 500

    aff_id = form.get("affliction_id")
    if not aff_id:
        return {"error": "Missing affliction_id."}, 400

    row = PatientCondition.query.get(aff_id)
    if not row:
        return {"error": "Affliction not found."}, 404

    db.session.delete(row)
    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500
    return {"message": "Affliction removed."}, 200


# -----------------------------
# Security / Sharing (privacy)
# -----------------------------
def save_security_settings(user: User, form: Dict[str, Any]) -> Tuple[dict, int]:
    """
    Persist alias + discoverability + field-level visibility matrix into User.
    Input names follow security.html (vis_<key> for each key).
    """
    # Identity
    alias = (form.get("alias") or "").strip() or None
    pref_display = (form.get("preferred_display") or "real").strip().lower()
    discoverable_alias = bool(form.get("discoverable_alias"))
    discoverable_name  = bool(form.get("discoverable_name"))

    if alias is not None:
        _set_if_has(user, "alias_name", alias)
    if pref_display in ("real", "alias"):
        _set_if_has(user, "preferred_display", pref_display)

    # discoverable object
    discoverable_obj = {"by_alias": discoverable_alias, "by_name": discoverable_name}
    if hasattr(user, "discoverable"):
        user.discoverable = discoverable_obj
    else:
        # store inside privacy JSON under "discoverable"
        pass

    # Visibility matrix
    fields = [
        "alias","real_name","date_of_birth","recommendations","qol_scores","afflictions",
        "afflictions_over_time","favorite_dispensary","favorites","voting_history"
    ]
    # Load or init current privacy JSON
    priv = getattr(user, "privacy", None) or {}
    vis = priv.get("visibility", {}) if isinstance(priv, dict) else {}

    for key in fields:
        v = (form.get(f"vis_{key}") or "private").strip().lower()
        if v not in ("private","friends","public"): v = "private"
        vis[key] = v

    priv["visibility"] = vis
    priv["discoverable"] = discoverable_obj
    _set_if_has(user, "privacy", priv)

    ok, err = _commit_safely()
    if not ok:
        return {"error": err or "Database error"}, 500
    return {"message": "Security & sharing settings saved."}, 200
'''

# 2) SERVICES: public_profile_service.py
FILES["app/services/public_profile_service.py"] = r'''
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
'''

# 3) ROUTES: patient_record.py (adds endpoints to the existing patient blueprint)
FILES["app/routes/patient_record.py"] = r'''
from __future__ import annotations
from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

# We attach routes to the existing 'patient' blueprint so your templates that call
# url_for('patient.update_*') continue to resolve correctly.
try:
    from app.routes.patient import patient_bp  # existing blueprint
except Exception:  # fallback: create a surrogate if not present (still works, but endpoints differ)
    patient_bp = Blueprint("patient", __name__, url_prefix="/patient")

from app.services import patient_record_service


@patient_bp.get("/record", endpoint="patient_record")
@login_required
def patient_record_page():
    """Render the multi-tab patient record UI (uses your existing template if present)."""
    # Prepare any server-provided choices here if needed
    return render_template("patient_record.html")


# ---------- Account ----------
@patient_bp.post("/record/account", endpoint="update_account")
@login_required
def update_account():
    msg, code = patient_record_service.update_account(current_user, request.form)
    if code == 200:
        flash(msg.get("message","Saved"), "success")
        return redirect(url_for("patient.patient_record"))
    flash(msg.get("error","Error"), "danger")
    return redirect(url_for("patient.patient_record"))


# ---------- Preferences ----------
@patient_bp.post("/record/preferences", endpoint="update_preferences")
@login_required
def update_preferences():
    msg, code = patient_record_service.update_preferences(current_user, request.form)
    if code == 200:
        flash(msg.get("message","Saved"), "success")
    else:
        flash(msg.get("error","Error"), "danger")
    return redirect(url_for("patient.patient_record"))


# ---------- Demographics ----------
@patient_bp.post("/record/demographics", endpoint="update_demographics")
@login_required
def update_demographics():
    msg, code = patient_record_service.update_demographics(current_user, request.form)
    if code == 200:
        flash(msg.get("message","Saved"), "success")
    else:
        flash(msg.get("error","Error"), "danger")
    return redirect(url_for("patient.patient_record"))


# ---------- Cannabis Use ----------
@patient_bp.post("/record/cannabis", endpoint="update_cannabis")
@login_required
def update_cannabis():
    msg, code = patient_record_service.update_cannabis(current_user, request.form)
    if code == 200:
        flash(msg.get("message","Saved"), "success")
    else:
        flash(msg.get("error","Error"), "danger")
    return redirect(url_for("patient.patient_record"))


# ---------- History ----------
@patient_bp.post("/record/history", endpoint="update_history")
@login_required
def update_history():
    msg, code = patient_record_service.update_history(current_user, request.form)
    if code == 200:
        flash(msg.get("message","Saved"), "success")
    else:
        flash(msg.get("error","Error"), "danger")
    return redirect(url_for("patient.patient_record"))


# ---------- Afflictions add/remove (AJAX) ----------
@patient_bp.post("/record/afflictions/add", endpoint="add_affliction")
@login_required
def add_affliction():
    msg, code = patient_record_service.add_affliction(current_user, request.form)
    return (jsonify(msg), code)


@patient_bp.post("/record/afflictions/remove", endpoint="remove_affliction")
@login_required
def remove_affliction():
    msg, code = patient_record_service.remove_affliction(current_user, request.form)
    return (jsonify(msg), code)


# ---------- Security & Sharing (matches security.html -> url_for('patient.security_save')) ----------
@patient_bp.post("/security/save", endpoint="security_save")
@login_required
def security_save():
    msg, code = patient_record_service.save_security_settings(current_user, request.form)
    if code == 200:
        flash(msg.get("message","Saved"), "success")
    else:
        flash(msg.get("error","Error"), "danger")
    # Back to dashboard or to a security page if you have one; dashboard is safer here:
    return redirect(url_for("patient.patient_dashboard"))
'''

# 4) ROUTES: public_profiles.py (new blueprint for public patient pages)
FILES["app/routes/public_profiles.py"] = r'''
from __future__ import annotations
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user

from app.services.public_profile_service import build_public_profile

public_profiles_bp = Blueprint("public_profiles", __name__, url_prefix="/patients")

@public_profiles_bp.get("/<alias_slug>", endpoint="public_profile")
def public_profile(alias_slug: str):
    """
    Public, read-only patient profile (privacy-aware).
    Renders HTML for browsers and returns JSON if ?format=json is provided.
    """
    viewer = current_user if getattr(current_user, "is_authenticated", False) else None
    data, status = build_public_profile(viewer, alias_slug)
    if (request.args.get("format") or "").lower() == "json":
        return jsonify(data), status
    if status != 200:
        return render_template("public_profile.html", error=data.get("error","Not found"), payload=None), status
    return render_template("public_profile.html", error=None, payload=data)
'''

# 5) TEMPLATE: public_profile.html
FILES["app/templates/public_profile.html"] = r'''
{% extends "base.html" %}
{% block title %}Patient Profile{% endblock %}
{% block content %}
<section class="mx-auto max-w-4xl p-4 md:p-6">
  {% if error %}
    <div class="kw-card" style="background:#3b0d0d;color:#fff;padding:12px;border-radius:10px;">{{ error }}</div>
  {% else %}
  <header class="flex items-center gap-4 mb-4">
    <div class="rounded-full h-12 w-12 flex items-center justify-center text-xl font-bold bg-emerald-700 text-white">
      {{ payload.avatar_initial }}
    </div>
    <div>
      <h1 class="text-2xl font-bold">{{ payload.display_name }}</h1>
      <div class="text-sm opacity-75">alias: {{ payload.alias_slug }}</div>
    </div>
  </header>

  <div class="grid md:grid-cols-2 gap-4">
    {% if payload.sections.alias or payload.sections.real_name %}
    <div class="kw-card p-3 rounded-xl bg-white/5 border border-white/10">
      <h2 class="font-semibold mb-2">Identity</h2>
      <div class="text-sm">Alias: {{ payload.sections.alias or '—' }}</div>
      <div class="text-sm">Real name: {{ payload.sections.real_name or '—' }}</div>
      <div class="text-sm">DOB: {{ payload.sections.date_of_birth or '—' }}</div>
    </div>
    {% endif %}

    {% if payload.sections.afflictions %}
    <div class="kw-card p-3 rounded-xl bg-white/5 border border-white/10">
      <h2 class="font-semibold mb-2">Afflictions</h2>
      <ul class="list-disc ml-5">
        {% for a in payload.sections.afflictions %}
          <li>{{ a.name }}{% if a.severity %} — <em>{{ a.severity }}</em>{% endif %}</li>
        {% endfor %}
      </ul>
    </div>
    {% endif %}

    {% if payload.sections.qol_summary %}
    <div class="kw-card p-3 rounded-xl bg-white/5 border border-white/10">
      <h2 class="font-semibold mb-2">Quality of Life</h2>
      <div class="text-sm">Latest Overall QoL: {{ payload.sections.qol_summary.latest_overall_qol if payload.sections.qol_summary.latest_overall_qol is not none else '—' }}</div>
    </div>
    {% endif %}

    {% if payload.sections.preferences %}
    <div class="kw-card p-3 rounded-xl bg-white/5 border border-white/10">
      <h2 class="font-semibold mb-2">Preferences</h2>
      <div class="text-sm">Strain Type: {{ payload.sections.preferences.strain_type or '—' }}</div>
      <div class="text-sm">Application: {{ payload.sections.preferences.application_method or '—' }}</div>
    </div>
    {% endif %}

    {% if payload.sections.top_products %}
    <div class="kw-card p-3 rounded-xl bg-white/5 border border-white/10 md:col-span-2">
      <h2 class="font-semibold mb-2">Top Products</h2>
      <div class="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {% for p in payload.sections.top_products %}
          <div class="p-3 rounded-xl bg-white/5 border border-white/10">
            <div class="font-semibold">{{ p.name }}</div>
            <div class="text-sm opacity-75">Avg QoL: {{ "%.2f"|format(p.avg_qol) }} ({{ p.votes }} votes)</div>
            <a class="kw-link" href="{{ url_for('products.detail', product_id=p.id) }}">View</a>
          </div>
        {% endfor %}
      </div>
    </div>
    {% endif %}
  </div>

  <footer class="mt-6 text-sm opacity-70">
    {% if payload.meta.friends_count is not none %}
      Friends: {{ payload.meta.friends_count }}
    {% endif %}
  </footer>
  {% endif %}
</section>
{% endblock %}
'''

# We DO NOT ship patient_record.html here because you already uploaded one.
# But if it's missing, we can write a safe, compatible fallback (same form action names).
FALLBACK_PATIENT_RECORD = r'''
{% extends "base.html" %}
{% block title %}Patient Record{% endblock %}
{% block content %}
<section class="kw-shell" style="max-width:900px;margin:auto;">
  <h1 class="kw-title">Patient Record</h1>
  <p class="kw-meta">This is a fallback template because patient_record.html was not present.</p>

  <form method="post" action="{{ url_for('patient.update_account') }}" class="kw-form">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <h2>Account</h2>
    <label>Name <input class="kw-input" name="name"></label>
    <label>Email <input class="kw-input" name="email" type="email"></label>
    <label>Alias <input class="kw-input" name="alias"></label>
    <label>Zip Code <input class="kw-input" name="zip_code"></label>
    <label>Password <input class="kw-input" name="password" type="password"></label>
    <button class="kw-btn" type="submit">Save</button>
  </form>

  <hr style="margin:16px 0;opacity:.4;"/>

  <form method="post" action="{{ url_for('patient.update_demographics') }}" class="kw-form">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <h2>Demographics</h2>
    <label>Sex
      <select class="kw-input" name="sex"><option>Male</option><option>Female</option><option>Other</option></select>
    </label>
    <label>Address <input class="kw-input" name="address"></label>
    <label>City <input class="kw-input" name="city"></label>
    <label>State <input class="kw-input" name="state"></label>
    <label>Country <input class="kw-input" name="country"></label>
    <div style="display:flex;gap:8px;">
      <input class="kw-input" name="height_feet" placeholder="ft">
      <input class="kw-input" name="height_inches" placeholder="in">
      <input class="kw-input" name="weight_lbs" placeholder="lbs">
    </div>
    <button class="kw-btn" type="submit">Save</button>
  </form>

  <hr style="margin:16px 0;opacity:.4;"/>

  <form method="post" action="{{ url_for('patient.update_cannabis') }}" class="kw-form">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <h2>Cannabis Use</h2>
    <label>Start Age <input class="kw-input" name="cannabis_use_start_age" type="number"></label>
    <label>Frequency
      <select class="kw-input" name="cannabis_use_frequency">
        <option value="">Select</option>
        <option value="daily">Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
      </select>
    </label>
    <label>Characterization <textarea class="kw-input" name="cannabis_use_characterization"></textarea></label>
    <button class="kw-btn" type="submit">Save</button>
  </form>
</section>
{% endblock %}
'''

# ------------------------------------------------------------
# Write files
# ------------------------------------------------------------
def write_file(path: Path, content: str, overwrite: bool = True) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return f"SKIP (exists)  -> {path}"
    path.write_text(content, encoding="utf-8")
    return f"WROTE          -> {path}"

def main():
    if not APP.exists():
        print("ERROR: 'app/' folder was not found. Run this script from your project root.", file=sys.stderr)
        sys.exit(1)

    results = []
    # Write services and routes and public_profile template (overwrite allowed)
    for rel, body in FILES.items():
        results.append(write_file(ROOT / rel, body, overwrite=True))

    # Ensure __init__ in services package exposes our new modules
    services_init = APP / "services" / "__init__.py"
    if services_init.exists():
        txt = services_init.read_text(encoding="utf-8")
        needed = ["patient_record_service", "public_profile_service"]
        changed = False
        for name in needed:
            if name not in txt:
                # append safe import/export lines
                txt += f"\nfrom app.services import {name}\n"
                if "__all__" in txt:
                    # try to extend __all__ safely
                    pass
                changed = True
        if changed:
            results.append(write_file(services_init, txt, overwrite=True))

    # Only create patient_record.html if missing
    pr_template = APP / "templates" / "patient_record.html"
    if not pr_template.exists():
        results.append(write_file(pr_template, FALLBACK_PATIENT_RECORD, overwrite=False))
    else:
        results.append(f"SKIP (exists)  -> {pr_template}")

    # Summary
    print("\n".join(results))
    print("\nPhase 1 build complete:")
    print(" - Patient record endpoints attached to existing 'patient' blueprint")
    print(" - Privacy-aware public patient profile at: /patients/<alias_slug>")
    print("Next: restart your Flask app and navigate to:")
    print("  • /patient/record")
    print("  • /patients/<alias_slug>   (uses User.alias_slug)")
    print()

if __name__ == "__main__":
    main()
