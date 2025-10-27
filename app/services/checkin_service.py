# FILE: app/services/checkin_service.py
from __future__ import annotations
from datetime import datetime
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import (
    PatientProfile,
    WellnessCheck,
    WellnessAttribution,
    CurrentPatientProductUsage,
)
from app.utils.wellness_feedback import generate_feedback
from app.services.scoring import compute_qol_score, compute_product_score


# ------------------------------------------------------------
# Check-ins Hub Context
# ------------------------------------------------------------
def get_checkins_hub_context(user) -> dict:
    """Assemble the context for /patient/checkins/hub."""
    profile: PatientProfile = user.patient_profile
    latest_checkin: WellnessCheck = profile.last_wellness_check
    current_usage = profile.current_products if hasattr(profile, "current_products") else []

    # --- Serialize last check-in and its metrics ---
    latest_levels, last_attributions = {}, {}
    if latest_checkin:
        latest_levels = {
            "pain_level": latest_checkin.pain_level,
            "mood_level": latest_checkin.mood_level,
            "energy_level": latest_checkin.energy_level,
            "clarity_level": latest_checkin.clarity_level,
            "appetite_level": latest_checkin.appetite_level,
            "sleep_level": latest_checkin.sleep_level,
        }

        for a in latest_checkin.attributions:
            for metric in ["pain", "mood", "energy", "clarity", "appetite", "sleep"]:
                pct = getattr(a, f"{metric}_pct", 0.0) or 0.0
                last_attributions[metric] = last_attributions.get(metric, 0.0) + pct

    # --- Prepare last 12 product usages ---
    last_products, usage_json = [], []
    for p in (current_usage[-12:] if current_usage else []):
        last_products.append({
            "product_id": p.product_id,
            "product_name": getattr(p.product, "name", "Unknown") if p.product else "Unknown",
            "dosage_mg": getattr(p, "dosage_mg", None),
            "times_per_day": getattr(p, "times_per_day", None),
        })
        usage_json.append({
            "day": p.created_at.date().isoformat() if getattr(p, "created_at", None) else None,
            "count": getattr(p, "times_per_day", 1),
        })

    # --- Build feedback ---
    feedback = {}
    if latest_checkin:
        prev = profile.previous_wellness_check
        if prev:
            feedback = generate_feedback(
                latest_checkin.to_sliders_dict(), prev.to_sliders_dict()
            )

    return {
        "sliders": [],
        "recommended_products": [],
        "ai_feedback": feedback.get("paragraph", ""),
        "last_checkin_at": getattr(latest_checkin, "checkin_date", None),
        "latest_qol": getattr(latest_checkin, "overall_qol", None),
        "wellness_history_json": [wc.to_dict() for wc in profile.wellness_checks],
        "comparisons": profile.comparisons,
        "usage_json": usage_json,
        "afflictions": profile.afflictions_constants,
        "affliction_grades": profile.affliction_grades_constants,
        "last_afflictions": profile.last_afflictions,
        "last_products": last_products,
        "last_attributions": last_attributions,
        "last_row": latest_checkin,
        "disable_checkins": (latest_checkin is None),
        "last_levels": latest_levels,
    }


# ------------------------------------------------------------
# Submit a Wellness Check
# ------------------------------------------------------------
def submit_wellness_check(user, data: dict) -> tuple[dict, int]:
    """Handle creation or update of a WellnessCheck and attributions."""
    try:
        profile: PatientProfile = user.patient_profile
        checkin_id = data.get("checkin_id")
        sliders = data.get("sliders", {})
        products_changed = data.get("products_changed", False)
        cannabis_pct = float(data.get("cannabis_pct", 0))
        products = data.get("products", [])

        # --- Load or create checkin ---
        if checkin_id:
            checkin = db.session.get(WellnessCheck, checkin_id)
            if not checkin or checkin.sid != user.sid:
                return {"error": "Invalid wellness check"}, 400
        else:
            checkin = WellnessCheck(sid=user.sid)
            db.session.add(checkin)

        # --- Apply sliders ---
        for field, val in sliders.items():
            if hasattr(checkin, field):
                setattr(checkin, field, val)

        # --- Compute QoL ---
        last_checkin = profile.last_wellness_check
        checkin.overall_qol = compute_qol_score(checkin)
        checkin.pct_change_qol = (
            checkin.overall_qol - getattr(last_checkin, "overall_qol", 0.0)
        ) if last_checkin else 0.0

        db.session.flush()

        # --- Product Attributions ---
        WellnessAttribution.query.filter_by(wellness_check_id=checkin.id).delete()

        total_qol_delta = getattr(checkin, "overall_qol_delta", checkin.pct_change_qol)
        cannabis_contribution = total_qol_delta * (cannabis_pct / 100)

        if products_changed and products:
            total_alloc_pct = sum(p.get("allocation_pct", 0) for p in products)
            if not 99.9 <= total_alloc_pct <= 100.1:
                return {"error": "Product allocations must total 100%"}, 400

            for p in products:
                attrib = WellnessAttribution(
                    wellness_check_id=checkin.id,
                    product_id=p.get("product_id"),
                    overall_pct=cannabis_contribution * (p.get("allocation_pct", 0) / 100)
                )
                db.session.add(attrib)

        db.session.commit()
        return {
            "success": True,
            "checkin_id": checkin.id,
            "overall_qol": checkin.overall_qol,
            "pct_change_qol": checkin.pct_change_qol,
            "cannabis_qol": cannabis_contribution,
        }, 200

    except SQLAlchemyError as db_err:
        db.session.rollback()
        current_app.logger.exception("[CheckinService] DB error: %s", db_err)
        return {"error": str(db_err)}, 500
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("[CheckinService] Exception: %s", e)
        return {"error": str(e)}, 500


# ------------------------------------------------------------
# Update product-level attributions
# ------------------------------------------------------------
def update_product_attributions(user, data: dict) -> tuple[dict, int]:
    wellness_check_id = data.get("wellness_check_id")
    wellness_check = db.session.get(WellnessCheck, wellness_check_id)
    if not wellness_check or wellness_check.sid != user.sid:
        return {"error": "Invalid wellness check"}, 400

    products_changed = data.get("products_changed", False)
    cannabis_pct = float(data.get("cannabis_pct", 0))
    products = data.get("products", [])

    total_qol_delta = getattr(wellness_check, "overall_qol_delta", None)
    if total_qol_delta is None:
        return {"error": "Wellness check missing QoL delta"}, 400

    cannabis_contribution = total_qol_delta * (cannabis_pct / 100)

    try:
        WellnessAttribution.query.filter_by(wellness_check_id=wellness_check.id).delete()

        if products_changed and products:
            total_alloc_pct = sum(p.get("allocation_pct", 0) for p in products)
            if not 99.9 <= total_alloc_pct <= 100.1:
                return {"error": "Product allocations must total 100%"}, 400

            for p in products:
                attribution = WellnessAttribution(
                    wellness_check_id=wellness_check.id,
                    product_id=p.get("product_id"),
                    overall_pct=cannabis_contribution * (p.get("allocation_pct", 0) / 100),
                )
                db.session.add(attribution)

        db.session.commit()
        return {"success": True, "cannabis_qol": cannabis_contribution}, 200

    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("[CheckinService] update_product_attributions: %s", e)
        return {"error": str(e)}, 500


# ------------------------------------------------------------
# Retrieve product attributions for a wellness check
# ------------------------------------------------------------
def get_product_attributions(user, wellness_check_id: int) -> tuple[dict, int]:
    wellness_check = (
        WellnessCheck.query.options(joinedload("attributions"))
        .filter_by(id=wellness_check_id, sid=user.sid)
        .first()
    )
    if not wellness_check:
        return {"error": "Wellness check not found"}, 404

    result = [
        {
            "product_id": a.product_id,
            "product_name": getattr(a.product, "name", None) if a.product else None,
            "overall_pct": a.overall_pct,
            "pain_pct": a.pain_pct,
            "mood_pct": a.mood_pct,
            "energy_pct": a.energy_pct,
            "clarity_pct": a.clarity_pct,
            "appetite_pct": a.appetite_pct,
            "sleep_pct": a.sleep_pct,
        }
        for a in wellness_check.attributions
    ]
    return {"attributions": result}, 200
