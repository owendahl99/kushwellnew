# FILE: app/services/patient_service.py
from __future__ import annotations
from datetime import datetime
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import func

from app.extensions import db
from app.models import (
    PatientProfile,
    WellnessCheck,
    PatientPreference,
    CurrentPatientProductUsage,
    PatientProductUsage,
    LatestAIRecommendation,
    MessageReceipt,
    Friends,
    GroupMember,
)
from app.utils import wellness
from app.utils.wellness_feedback import generate_feedback


# ------------------------------------------------------------
# Baseline submission
# ------------------------------------------------------------
def submit_baseline(user, data: dict) -> tuple[dict, int]:
    try:
        patient: PatientProfile = PatientProfile.query.filter_by(user_sid=user.sid).first()
        if not patient:
            return {"status": "error", "message": "Patient profile not found"}, 404

        if patient.onboarding_complete:
            return {"status": "ok", "message": "Already onboarded"}, 200

        sliders = data.get("sliders", {}) or {}
        conditions = data.get("conditions", {}) or {}
        preferences = data.get("preferences", {}) or {}

        # 1️⃣ Create baseline wellness record
        wc = WellnessCheck(
            sid=patient.sid,
            pain_level=sliders.get("pain"),
            mood_level=sliders.get("mood"),
            energy_level=sliders.get("energy"),
            clarity_level=sliders.get("clarity"),
            appetite_level=sliders.get("appetite"),
            sleep_level=sliders.get("sleep"),
            checkin_date=datetime.utcnow(),
        )
        wc.compute_overall_qol()
        db.session.add(wc)

        # 2️⃣ Save afflictions / conditions
        if conditions:
            patient.set_afflictions_with_severity(conditions)

        # 3️⃣ Save preferences
        if preferences:
            pref = PatientPreference(
                patient_id=patient.sid,
                strain_type=preferences.get("strain_type"),
                company_name=preferences.get("company_name"),
                thc_min=preferences.get("thc_min"),
                thc_max=preferences.get("thc_max"),
                application_method=preferences.get("application_method"),
            )
            db.session.add(pref)

        # 4️⃣ Mark onboarding complete
        patient.onboarding_complete = True
        db.session.commit()
        return {"status": "ok", "message": "Baseline saved successfully"}, 200

    except SQLAlchemyError as db_err:
        db.session.rollback()
        current_app.logger.exception("[PatientService] SQLAlchemy error: %s", db_err)
        return {"status": "error", "message": str(db_err)}, 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("[PatientService] Exception: %s", e)
        return {"status": "error", "message": str(e)}, 500


# ------------------------------------------------------------
# Baseline context for GET form
# ------------------------------------------------------------
def get_baseline_context(user) -> dict:
    patient = PatientProfile.query.filter_by(user_sid=user.sid).first()
    alias_name = getattr(user, "alias_name", "")
    return {"patient": patient, "alias_name": alias_name}


# ------------------------------------------------------------
# Dashboard context
# ------------------------------------------------------------
def get_dashboard_context(user) -> dict:
    sid = getattr(user, "sid", None)
    patient = PatientProfile.query.filter_by(user_sid=sid).first()
    if not patient:
        raise RuntimeError("Patient profile not found")

    alias = getattr(user, "alias_name", None)
    avatar_initial = alias[0].upper() if alias else "?"

    # Product usage and recommendations
    current_products = CurrentPatientProductUsage.get_current_for_patient(sid)
    latest_recommendation = LatestAIRecommendation.query.filter_by(patient_sid=sid).first()

    # Social counters
    unread_count = (
        db.session.query(func.count()).filter(
            MessageReceipt.user_id == user.id,
            MessageReceipt.is_read.is_(False)
        ).scalar() or 0
    )
    friends_count = (
        db.session.query(func.count()).filter(Friends.user_id == user.id).scalar() or 0
    )
    group_count = (
        db.session.query(func.count()).filter(GroupMember.user_id == user.id).scalar() or 0
    )

    # Wellness and feedback
    last_check = getattr(patient, "last_wellness_check", None)
    feedback = {}
    if last_check:
        prev = getattr(patient, "previous_wellness_check", None)
        if prev:
            feedback = generate_feedback(
                last_check.to_sliders_dict(), prev.to_sliders_dict()
            )

    context = {
        "patient": patient,
        "current_products": current_products,
        "last_score": getattr(patient, "last_qol_score", None),
        "last_checkin_date": getattr(patient, "last_qol_date", None),
        "is_onboarded": getattr(patient, "is_onboarded", False),
        "latest_recommendation": latest_recommendation,
        "public_profile_data": {
            "display_name": user.display_name,
            "avatar_initial": avatar_initial,
            "alias": user.alias_name if getattr(user, "alias_public_on", False) else None,
            "quick_links": {"friends": True, "groups": True},
        },
        "avatar_initial": avatar_initial,
        "alias_name": alias,
        "unread_count": unread_count,
        "friends_count": friends_count,
        "group_count": group_count,
        "feedback": feedback,
    }
    return context


# ------------------------------------------------------------
# Stop using product
# ------------------------------------------------------------
def stop_using_product(user, usage_id: int, form_data) -> tuple[dict, int]:
    from app.models import CurrentPatientProductUsage

    usage = CurrentPatientProductUsage.query.get(usage_id)
    if not usage:
        return {"message": "Usage not found"}, 404
    if usage.sid != user.sid:
        return {"message": "Forbidden"}, 403

    try:
        end_date_str = form_data.get("end_date")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else datetime.utcnow()
        db.session.delete(usage)

        patient_usage = (
            PatientProductUsage.query
            .filter_by(sid=usage.sid, product_id=usage.product_id, still_using=True)
            .order_by(PatientProductUsage.start_date.desc())
            .first()
        )
        if patient_usage:
            patient_usage.end_date = end_date
            patient_usage.still_using = False

        db.session.commit()
        return {"message": "Product marked as discontinued"}, 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("[PatientService] stop_using_product: %s", e)
        return {"message": str(e)}, 500
