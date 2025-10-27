
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
