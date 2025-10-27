
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
