from flask import Blueprint, render_template, url_for, flash, redirect, abort, request  
from flask_login import current_user, login_required
from datetime import datetime

from sqlalchemy import func
from app.extensions import db
from app.constants.general_menus import UserRoleEnum
from app.utils.decorators import role_required
# from app.utils.scoring import top_scores
from app.models import (
    PatientProfile,
    WellnessCheck,
    LatestAIRecommendation,
    PatientProductUsage,
    Product,
)

# BLUEPRINT
patient_bp = Blueprint("patient", __name__, url_prefix="/patient")


# --------------------------------------------------------------------------
# Helper functions
# --------------------------------------------------------------------------
def _get_latest_wellness(sid) -> WellnessCheck | None:
    if not sid:
        return None
    return (
        db.session.query(WellnessCheck)
        .filter_by(sid=sid)
        .order_by(WellnessCheck.last_checkin_at.desc())
        .first()
    )


def _has_baseline(sid) -> bool:
    return bool(
        db.session.query(WellnessCheck)
        .filter_by(sid=sid)
        .first()
    )


def _compute_last_qol(wellness: WellnessCheck | None) -> tuple[int | None, str | None]:
    if not wellness:
        return None, None
    try:
        overall = wellness.overall_qol
        last_at = wellness.last_checkin_at
        return int(overall) if overall is not None else None, last_at
    except Exception:
        return None, None


# ----------------------------# ------------------------------------------------------------
# Patient: Baseline Check-in
# ------------------------------------------------------------
@patient_bp.route("/baseline_checkin", methods=["GET", "POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def baseline_checkin():
    """Handles baseline onboarding wellness + conditions + product check-in."""
    patient: PatientProfile = PatientProfile.query.filter_by(user_sid=current_user.sid).first()

    if not patient:
        flash("Patient profile not found.", "danger")
        return redirect(url_for("auth.login"))

    # If onboarding already complete, send to dashboard
    if patient.onboarding_complete:
        return redirect(url_for("patient.patient_dashboard"))
    
    # Get the alias from the linked user
    alias_name = getattr(current_user, "alias_name", "")  # Assuming alias is on User

    if request.method == "POST":
        data = request.get_json() or {}

        # -------------
        # 1️⃣ Parse Data
        # -------------
        sliders = data.get("sliders", {})
        conditions = data.get("conditions", {})       # { "Anxiety": "Moderate", "Pain": "Severe" }
        products = data.get("products", [])           # [{product_id: 12, notes: "..."}]
        preferences = data.get("preferences", {})     # {"strain_type": "Hybrid", "application_method": "Oral"}

        # -------------
        # 2️⃣ Create WellnessCheck
        # -------------
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
        db.session.flush()

        # -------------
        # 3️⃣ Update Patient Conditions / Afflictions
        # -------------
        if conditions:
            patient.set_afflictions_with_severity(conditions)

        # -------------
        # 4️⃣ Store Product Usage
        # -------------
        for p in products:
            product_id = p.get("product_id")
            if not product_id:
                continue

            # Record product attribution to wellness check
            wc.attributions.append(
                WellnessAttribution(product_id=product_id, notes=p.get("notes"))
            )

            # Record current product usage
            current_usage = CurrentPatientProductUsage(
                sid=patient.sid,
                product_id=product_id,
                start_date=datetime.utcnow()
            )
            db.session.add(current_usage)

            # Add to historical usage
            history_entry = PatientProductUsage(
                sid=patient.sid,
                product_id=product_id,
                start_date=datetime.utcnow(),
                still_using=True
            )
            db.session.add(history_entry)

        # -------------
        # 5️⃣ Store Patient Preferences
        # -------------
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

        # -------------
        # 6️⃣ Mark onboarding complete
        # -------------
        patient.onboarding_complete = True
        patient.first_wellness_check_done = True
        patient.first_product_interaction_done = True
        db.session.commit()

        return jsonify({
            "success": True,
            "redirect": url_for("patient.patient_dashboard"),
            "wellness_check_id": wc.id,
            "overall_qol": wc.overall_qol,
        })

    # If they somehow revisit after completion, bounce them out
    if patient.onboarding_complete:
        return redirect(url_for("patient.patient_dashboard"))

    # GET: render page
    return render_template(
        "patient/checkin_baseline.html",
        patient=patient,
        alias_name=alias_name
    )

# --------------------------------------------------------------------------
# Patient Dashboard
# --------------------------------------------------------------------------
@patient_bp.route("/dashboard", methods=["GET"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def patient_dashboard():
    sid = getattr(current_user, "sid", None)
    if not sid:
        abort(403, "No patient SID associated with current user")

    # --- Fetch patient profile ---
    patient: PatientProfile = db.session.get(PatientProfile, sid)
    if not patient:
        abort(404, "Patient profile not found")

    # --- Wellness / QoL ---
    latest_checkin = _get_latest_wellness(patient.sid)
    last_qol, last_checkin_date = _compute_last_qol(latest_checkin)
    has_base = _has_baseline(patient.sid)
    checkin_url = url_for("patient.checkins_hub") if has_base else url_for("patient.onboarding_hub")

    # --- Latest AI recommendation ---
    latest_recommendation = LatestAIRecommendation.query.filter_by(patient_sid=patient.sid).first()

    # --- Current products ---
    current_products = (
        db.session.query(PatientProductUsage)
        .join(Product, PatientProductUsage.product_id == Product.id)
        .filter(PatientProductUsage.sid == sid, PatientProductUsage.still_using.is_(True))
        .order_by(PatientProductUsage.updated_at.desc())
        .limit(12)
        .all()
    )

    # --- Top products (aggregate scores) ---
   #try:
    #   top_dict = top_scores(None, limit=5) or {}
    #   top_products = [p for p, _s in top_dict.get("Overall", [])]
    #xcept Exception:
    #   top_products = []

    # --- Unread messages, friends, groups counts ---
    unread_count = 0
    friends_count = 0
    group_count = 0
    try:
        from app.models import MessageReceipt, Friends, GroupMember
        unread_count = db.session.query(func.count()).filter(
            MessageReceipt.user_id == current_user.id,
            MessageReceipt.is_read.is_(False)
        ).scalar() or 0

        friends_count = db.session.query(func.count()).filter(
            Friends.user_id == current_user.id
        ).scalar() or 0

        group_count = db.session.query(func.count()).filter(
            GroupMember.user_id == current_user.id
        ).scalar() or 0
    except Exception:
        pass

    # --- Render ---
    return render_template(
        "patient/patient_dashboard.html",
        patient=patient,
        last_qol=last_qol,
        last_checkin_date=last_checkin_date,
        latest_recommendation=latest_recommendation,
        has_baseline=has_base,
        checkin_url=checkin_url,
        current_products=current_products,
        products=current_products,  # for legacy templates
        # p_products=top_products,
        unread_count=unread_count,
        friends_count=friends_count,
        group_count=group_count,
    )

 
@patient_bp.route("/checkins/hub", methods=["GET"], endpoint="checkins_hub")
@login_required
@role_required(UserRoleEnum.PATIENT)
def checkins_hub():
    WC = WellnessCheck
    UC = PatientProductUsage
    PA = PatientCondition
    WA = WellnessAttribution

    # --- User identifiers ---
    sid = getattr(getattr(current_user, "patient_profile", None), "sid", None) or getattr(current_user, "sid", None)
    user_id = getattr(current_user, "id", None)

    # --- Wellness check-ins ---
    q = db.session.query(WC)
    if sid and hasattr(WC, "sid"):
        q = q.filter(WC.sid == sid)
    elif user_id and hasattr(WC, "user_id"):
        q = q.filter(WC.user_id == user_id)

    if hasattr(WC, "deleted_at"):
        q = q.filter(WC.deleted_at.is_(None))

    ts_col = getattr(WC, "last_checkin_at", WC.id)
    rows = q.order_by(ts_col.asc()).all()
    last_row = rows[-1] if rows else None

    # --- Wellness history JSON ---
    hist = []
    for r in rows:
        hist.append({
            "ts": r.last_checkin_at,
            "overall_qol": r.overall_qol,
            "pct_change": r.pct_change_qol,
            "pain": r.pain_level,
            "mood": r.mood_level,
            "energy": r.energy_level,
            "clarity": r.clarity_level, 
            "appetite": r.appetite_level,
            "sleep": r.sleep_level,
            "is_baseline": bool(getattr(r, "is_baseline", False)),
        })

    latest_qol = getattr(last_row, "overall_qol", None) if last_row else None
    
    last_dt = getattr(last_row, "last_checkin_at", None) 

    if last_row:
        last_levels = {
            "pain_level": last_row.pain_level,
            "energy_level": last_row.energy_level,
            "clarity_level": last_row.clarity_level,
            "appetite_level": last_row.appetite_level,
            "mood_level": last_row.mood_level,
            "sleep_level": last_row.sleep_level,
        }
        last_attributions = {
            a.metric: a.overall_pct for a in getattr(last_row, "attributions", [])
        }
    else:
        last_levels = {}
        last_attributions = {}
        
    last_dt = getattr(last_row, "last_checkin_at", None)
    

    # --- Last afflictions ---
    afflictions = []
    if PA and sid:
        afflictions = (
            db.session.query(PA)
            .filter(PA.sid == sid)
            .order_by(getattr(PA, "created_at", PA.id).desc())
            .all()
        )

    # --- Product usage overlay ---
    usage_json, last_products = [], []
    if UC and sid:
        from sqlalchemy import func
        day_col = getattr(UC, "created_at", None)

        if day_col:
            agg = (
                db.session.query(func.date(day_col).label("day"), func.count("*").label("cnt"))
                .filter(UC.sid == sid)
                .group_by("day")
                .order_by("day")
                .all()
            )
            usage_json = [{"day": d.isoformat(), "count": int(c)} for d, c in agg]

        lp_rows = (
            db.session.query(UC)
            .filter(UC.sid == sid)
            .order_by(day_col.desc() if day_col else UC.id.desc())
            .limit(12)
            .all()
        )
        for p in lp_rows:
            last_products.append({
                "product_id": p.product_id,
                "dosage_mg": getattr(p, "dosage_mg", None),
                "times_per_day": getattr(p, "times_per_day", None),
                "product_name": getattr(p.product, "name", "Unknown") if p.product else "Unknown",
                "url": url_for("products.product_detail", product_id=p.product_id),
            })
        
        
    # Aggregate averages (comparative analytics)
    comparisons = {
        "pain": db.session.query(func.avg(CheckIn.pain)).scalar() or 0,
        "clarity": db.session.query(func.avg(CheckIn.clarity)).scalar() or 0,
        "energy": db.session.query(func.avg(CheckIn.energy)).scalar() or 0,
        "mood": db.session.query(func.avg(CheckIn.mood)).scalar() or 0,
        "appetite": db.session.query(func.avg(CheckIn.appetite)).scalar() or 0,
    }


    disable_checkins = not bool(rows)

    # --- Wellness attribution (per metric) ---
    last_attributions = {}
    if last_row:
        atts = last_row.attributions.all()
        for a in atts:
            for metric in ["pain", "mood", "energy", "clarity", "appetite"]:
                pct = getattr(a, f"{metric}_pct", 0.0) or 0.0
                last_attributions[metric] = last_attributions.get(metric, 0.0) + pct

    # --- AI-enhanced comparative report ---
    current_checkin = last_row
    last_checkin = rows[-2] if len(rows) > 1 else None
    products = db.session.query(Product).all()

    sliders, recommended_products, ai_feedback = get_ai_wellness_report(
        current_checkin=current_checkin,
        last_checkin=last_checkin,
        product_usage=[{"product_id": p.id, "name": p.name, "allocation": 1.0} for p in products],
        all_checkins=rows,
    )

    return render_template(
        "patient/checkins_hub.html",
        sliders=sliders,
        recommended_products=recommended_products,
        ai_feedback=ai_feedback,
        last_checkin_at=last_dt,  # pass as datetime, not isoformat or str
        latest_qol=latest_qol,
        wellness_history_json=hist,
        comparisons=comparisons,
        usage_json=usage_json,
        afflictions=AFFLICTION_LIST,
        affliction_grades=AFFLICTION_LEVELS,
        last_afflictions=afflictions,
        last_products=last_products,
        last_attributions=last_attributions,  # used in sliders & last check-in partials
        last_row=last_row,                    # pass for raw levels
        disable_checkins=disable_checkins,
        last_levels=last_levels,              # for template sliders
    )

# ---------- Helper: get last wellness check ----------
def get_last_wellness_check(sid):
    return (
        WellnessCheck.query
        .filter_by(sid=sid)
        .order_by(WellnessCheck.last_checkin_at.desc())
        .first()
    )


# ---------- Route: Product Check-in (POST) ----------
@patient_bp.route("/checkin/products", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_checkin():
    """
    Expects JSON:
    {
        "wellness_check_id": int,
        "products_changed": bool,
        "cannabis_pct": float,  # 0?100
        "products": [
            {"product_id": int, "allocation_pct": float},
            ...
        ]
    }
    """
    data = request.get_json() or {}
    wellness_check_id = data.get("wellness_check_id")
    products_changed = data.get("products_changed", False)
    cannabis_pct = data.get("cannabis_pct", 0)
    products = data.get("products", [])

    wellness_check = db.session.get(WellnessCheck, wellness_check_id)
    if not wellness_check or wellness_check.sid != current_user.sid:
        return jsonify({"error": "Invalid wellness check"}), 400

    total_qol_change = getattr(wellness_check, "overall_qol_delta", None)
    if total_qol_change is None:
        return jsonify({"error": "Wellness check missing QoL delta"}), 400

    cannabis_contribution = total_qol_change * (cannabis_pct / 100)

    # Clear existing attributions
    WellnessAttribution.query.filter_by(
        wellness_check_id=wellness_check.id
    ).delete()

    # Save per-product attributions
    if products_changed and products:
        total_alloc_pct = sum(p.get("allocation_pct", 0) for p in products)
        if not 99.9 <= total_alloc_pct <= 100.1:
            return jsonify({"error": "Product allocations must total 100%"}), 400

        for p in products:
            attribution = WellnessAttribution(
                wellness_check_id=wellness_check.id,
                product_id=p.get("product_id"),
                overall_pct=cannabis_contribution * (p.get("allocation_pct", 0) / 100),
            )
            db.session.add(attribution)

    db.session.commit()
    return jsonify({"success": True, "cannabis_qol": cannabis_contribution}), 200

# ---------- Route: Get product attributions (GET) ----------
@patient_bp.route("/checkin/products/<int:wellness_check_id>", methods=["GET"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def get_product_checkin(wellness_check_id):
    wellness_check = (
        WellnessCheck.query.options(joinedload("attributions"))
        .filter_by(id=wellness_check_id, sid=current_user.sid)
        .first()
    )
    if not wellness_check:
        return jsonify({"error": "Wellness check not found"}), 404

    result = [
        {
            "product_id": a.product_id,
            "product_name": a.product.product_name if a.product else None,
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
    return jsonify({"attributions": result}), 200

# ---------- Route: Stop using product ----------
@patient_bp.route("/products/<int:usage_id>/stop", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def stop_using_product(usage_id):
    usage = db.session.get(PatientProductUsage, usage_id)
    if not usage or usage.sid != current_user.sid or not usage.still_using:
        flash("Product not found or already stopped.", "warning")
        return redirect(request.referrer or url_for("patient.patient_dashboard"))

    end_date_str = request.form.get("end_date")
    usage.end_date = (
        datetime.strptime(end_date_str, "%Y-%m-%d")
        if end_date_str
        else datetime.utcnow()
    )
    usage.still_using = False

    db.session.commit()
    flash(f"{usage.product.product_name} marked as stopped.", "success")
    return redirect(request.referrer or url_for("patient.patient_dashboard"))

# ---------- Route: Product search (AJAX JSON) ----------
@patient_bp.get("/products/search")
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    like = f"%{q}%"
    cols = []
    for name in ("product_name", "manufacturer", "category", "description"):
        if hasattr(Product, name):
            cols.append(getattr(Product, name).ilike(like))
    if not cols:
        return jsonify([])

    rows = (
        db.session.query(Product)
        .filter(or_(*cols))
        .order_by(Product.product_name.asc())
        .limit(12)
        .all()
    )

    return jsonify(
        [
            {
                "id": p.id,
                "name": p.product_name,
                "brand": p.manufacturer or "",
                "category": p.category or "",
            }
            for p in rows
        ]
    )
    
# FILE: routes/patient.py
@patient_bp.route("/checkins/submit", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def checkin_submit():
    sid = getattr(current_user, "sid", None)
    if not sid:
        if request.is_json:
            return jsonify({"error": "No patient profile found"}), 400
        flash("Patient profile not found", "error")
        return redirect(url_for("patient.checkins_hub"))

    try:
        payload = request.get_json(silent=True)
        if payload:  # --- JSON payload path ---
            # Extract slider values
            pain = payload.get("pain_level")
            mood = payload.get("mood_level")
            energy = payload.get("energy_level")
            clarity = payload.get("clarity_level")
            appetite = payload.get("appetite_level")
            sleep = payload.get("sleep_level")
            notes = payload.get("notes", "").strip()

            # Compute QoL
            def compute_qol(levels):
                inverted_pain = 10 - (levels.get("pain_level") or 0)
                total = (
                    inverted_pain
                    + (levels.get("mood_level") or 0)
                    + (levels.get("energy_level") or 0)
                    + (levels.get("clarity_level") or 0)
                    + (levels.get("appetite_level") or 0)
                    + (levels.get("sleep_level") or 0)
                ) * 2
                return total

            qol_score = compute_qol(payload)

            # Create WellnessCheck
            wellness = WellnessCheck(
                sid=sid,
                pain_level=pain,
                mood_level=mood,
                energy_level=energy,
                clarity=clarity,
                appetite_level=appetite,
                sleep_level=sleep,
                notes=notes,
                overall_qol=qol_score
            )
            db.session.add(wellness)
            db.session.flush()

            # --- Attributions ---
            for attr in payload.get("attributions", []):
                attribution = WellnessAttribution(
                    wellness_check_id=wellness.id,
                    product_id=attr.get("product_id"),
                    pain_pct=attr.get("pain_pct"),
                    mood_pct=attr.get("mood_pct"),
                    energy_pct=attr.get("energy_pct"),
                    clarity_pct=attr.get("clarity_pct"),
                    appetite_pct=attr.get("appetite_pct"),
                    sleep_pct=attr.get("sleep_pct"),
                    overall_pct=attr.get("overall_pct"),
                )
                db.session.add(attribution)

            # --- Afflictions ---
            for aff in payload.get("afflictions", []):
                pa = PatientAffliction(
                    sid=sid,
                    wellness_check_id=wellness.id,
                    affliction_name=aff.get("name"),
                    severity=aff.get("severity", 0)
                )
                db.session.add(pa)

            # --- Product check-ins ---
            for prod in payload.get("products", []):
                uc = UsageCheckin(
                    sid=sid,
                    wellness_check_id=wellness.id,
                    product_id=prod.get("product_id"),
                    dosage_mg=prod.get("dosage_mg"),
                    times_per_day=prod.get("times_per_day"),
                )
                db.session.add(uc)

            db.session.commit()

            # --- Generate AI feedback ---
            sliders_comparison, recommended_products, ai_feedback = get_ai_wellness_report(
                current_checkin=payload,
                last_checkin=None,  # optionally fetch last wellness check
                product_usage=payload.get("products", []),
                all_checkins=[]
            )

            # Persist AI recommendation to database
            save_latest_ai_feedback(patient_sid=sid, feedback=ai_feedback)

            return jsonify({
                "success": True,
                "wellness_id": wellness.id,
                "overall_qol": qol_score,
                "ai_feedback": ai_feedback
            }), 200

        else:  # --- Form payload path ---
            metrics = ["pain", "mood", "energy", "clarity", "appetite"]
            values = {}
            for m in metrics:
                raw = request.form.get(m)
                try:
                    values[m] = int(raw)
                except (ValueError, TypeError):
                    values[m] = None

            notes = request.form.get("notes", "").strip()

            wc = WellnessCheck(
                sid=sid,
                pain_level=values.get("pain"),
                mood_level=values.get("mood"),
                energy_level=values.get("energy"),
                clarity_level=values.get("clarity"),
                appetite_level=values.get("appetite"),
                notes=notes
            )
            db.session.add(wc)
            db.session.commit()

            # Update product votes
            user_products = get_patient_products(sid)
            for p in user_products:
                upsert_patient_product_vote(patient_id=current_user.id, product_id=p.id)

            flash("Check-in submitted successfully!", "success")
            return redirect(url_for("patient.checkins_hub"))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"checkin_submit failed: {e}", exc_info=True)
        if request.is_json:
            return jsonify({"error": "Submission failed"}), 500
        flash("Check-in submission failed", "error")
        return redirect(url_for("patient.checkins_hub"))

# ===========================================
# Onboarding Submit Route (POST)
# ===========================================
@patient_bp.route("/onboarding/submit", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def onboarding_submit():
    sid = getattr(current_user, "sid", None)
    if not sid:
        return jsonify({"error": "No patient profile found"}), 400

    profile = PatientProfile.query.filter_by(sid=sid).first()
    if not profile:
        profile = PatientProfile(sid=sid)
        db.session.add(profile)

    # ----------------------------
    # 1?? Core background data
    # ----------------------------
    data = request.form or request.json or {}

    # Need-to-know section
    profile.alias = data.get("alias", profile.alias)
    profile.email = data.get("email", profile.email)
    profile.birth_date = data.get("birth_date", profile.birth_date)
    profile.zip_code = data.get("zip_code", profile.zip_code)

    # Optional name + address block
    profile.full_name = data.get("full_name", profile.full_name)
    profile.address = data.get("address", profile.address)

    # Optional model-enhancing section
    profile.weight = data.get("weight", profile.weight)
    profile.sex = data.get("sex", profile.sex)
    profile.cannabis_history = data.get("cannabis_history", profile.cannabis_history)
    profile.prescriptions = data.get("prescriptions", profile.prescriptions)

    # Update password inline if user provides current + new password
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    if current_password and new_password:
        if current_user.check_password(current_password):
            current_user.set_password(new_password)
        else:
            return jsonify({"error": "Invalid current password"}), 403

    # ----------------------------
    # 2?? Wellness baseline data
    # ----------------------------
    # Reuse existing wellness handling logic
    wellness_fields = ["pain", "mood", "sleep", "appetite", "energy", "focus"]
    baseline_data = {field: float(data.get(field, 0)) for field in wellness_fields}

    wellness_entry = PatientWellness.query.filter_by(sid=sid).order_by(PatientWellness.created_at.desc()).first()

    if not wellness_entry:
        # First-time baseline
        new_entry = PatientWellness(
            sid=sid,
            **baseline_data,
            baseline=True
        )
        db.session.add(new_entry)
    else:
        # Update or overwrite latest entry
        for k, v in baseline_data.items():
            setattr(wellness_entry, k, v)
        wellness_entry.baseline = True

    # ----------------------------
    # 3?? Product check-ins
    # ----------------------------
    # Same logic as check-in: store what products patient uses today
    product_ids = data.get("product_ids")
    if product_ids:
        # Expect a comma-separated string or list of product IDs
        if isinstance(product_ids, str):
            product_ids = [pid.strip() for pid in product_ids.split(",") if pid.strip()]
        for pid in product_ids:
            usage = PatientProductUsage.query.filter_by(sid=sid, product_id=pid).first()
            if not usage:
                usage = PatientProductUsage(sid=sid, product_id=pid)
                db.session.add(usage)
            usage.last_used = datetime.utcnow()

    # ----------------------------
    # 4?? Commit everything
    # ----------------------------
    try:
        db.session.commit()
        return jsonify({"message": "Onboarding data saved successfully."}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
    
    
        # ==================== PRODUCT SEARCH (FULL PAGE LIST) ====================
@patient_bp.get("/products", endpoint="product_list")
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_list():
    """Full product listing / filters (renders a template)."""
    from sqlalchemy import or_, and_
    Product = _Product()
    if not Product:
        flash("Products model not available.", "warning")
        return redirect(url_for("patient.onboarding_hub"))

    q = (request.args.get("q") or "").strip()
    classification = (request.args.get("classification") or request.args.get("strain") or "").strip()
    affliction = (request.args.get("affliction") or "").strip()
    terp_list = request.args.getlist("terpene") or []
    thc_min = request.args.get("thc_min", type=float)
    thc_max = request.args.get("thc_max", type=float)
    cbd_min = request.args.get("cbd_min", type=float)
    cbd_max = request.args.get("cbd_max", type=float)
    cbn_min = request.args.get("cbn_min", type=float)
    cbn_max = request.args.get("cbn_max", type=float)
    available = request.args.get("available")
    dispensary_id = request.args.get("dispensary_id", type=int)
    min_qol = request.args.get("min_qol", type=float)
    sort = request.args.get("sort", "new")
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 24, type=int), 100)

    qry = db.session.query(Product)

    if q:
        like = f"%{q}%"
        text_cols = []
        for name in ("name", "brand", "strain", "form", "classification", "description"):
            if hasattr(Product, name):
                text_cols.append(getattr(Product, name).ilike(like))
        if text_cols:
            qry = qry.filter(or_(*text_cols))

    if classification:
        if hasattr(Product, "classification"):
            qry = qry.filter(getattr(Product, "classification").ilike(classification))
        elif hasattr(Product, "strain"):
            qry = qry.filter(getattr(Product, "strain").ilike(classification))

    if affliction:
        if hasattr(Product, "affliction"):
            qry = qry.filter(getattr(Product, "affliction").ilike(affliction))
        else:
            try:
                from app.models import ProductAffliction
                qry = qry.join(ProductAffliction).filter(ProductAffliction.name.ilike(affliction))
            except Exception:
                pass

    def _col(*names):
        for n in names:
            if hasattr(Product, n):
                return getattr(Product, n)
        return None

    thc_col = _col("thc_pct", "thc_percent", "thc")
    cbd_col = _col("cbd_pct", "cbd_percent", "cbd")
    cbn_col = _col("cbn_pct", "cbn_percent", "bd")
    

    if thc_col is not None:
        if thc_min is not None:
            qry = qry.filter(thc_col >= thc_min)
        if thc_max is not None:
            qry = qry.filter(thc_col <= thc_max)
    if cbd_col is not None:
        if cbd_min is not None:
            qry = qry.filter(cbd_col >= cbd_min)
        if cbd_max is not None:
            qry = qry.filter(cbd_col <= cbd_max)
    if cbn_col is not None:
            if cbn_min is not None:
                qry = qry.filter(cbn_col >= cbn_min)
            if cbn_max is not None:
                qry = qry.filter(cbn_col <= cbn_max)
        


    if terp_list:
        applied = False
        try:
            from app.models import ProductTerpene
            qry = qry.join(ProductTerpene, ProductTerpene.product_id == Product.id)
            qry = qry.filter(ProductTerpene.name.in_(terp_list))
            applied = True
        except Exception:
            pass
        if not applied and hasattr(Product, "terpenes"):
            try:
                from sqlalchemy.orm import aliased
                Terp = aliased(getattr(Product, "terpenes").property.mapper.class_)
                qry = qry.join(Terp, Product.terpenes)
                qry = qry.filter(Terp.name.in_(terp_list))
            except Exception:
                pass

    if available or dispensary_id:
        applied = False
        for fld in ("is_available", "available", "status"):
            if hasattr(Product, fld):
                if fld == "status" and available:
                    qry = qry.filter(getattr(Product, fld).in_(["active", "approved", "published"]))
                elif fld != "status" and available:
                    qry = qry.filter(getattr(Product, fld) == True)  # noqa: E712
                applied = True
                break
        if not applied:
            try:
                from app.models import DispensaryInventory
                inv = DispensaryInventory
                cond = inv.product_id == Product.id
                if dispensary_id:
                    cond = and_(cond, inv.dispensary_id == dispensary_id)
                qry = qry.join(inv, cond)
                if available and hasattr(inv, "in_stock"):
                    qry = qry.filter(inv.in_stock == True)  # noqa: E712
            except Exception:
                pass

    Usage = _UsageModel()
    avg_eff = None
    if Usage:   
        try:
            sub = (
                db.session.query(
                    getattr(Usage, "product_id").label("pid"),
                    func.avg(getattr(Usage, "effectiveness")).label("avg_eff"),
                )
                .group_by(getattr(Usage, "product_id"))
                .subquery()
            )
            qry = qry.outerjoin(sub, sub.c.pid == Product.id)
            avg_eff = sub.c.avg_eff
            if min_qol is not None:
                thr = float(min_qol)
                if thr > 10:
                    thr = thr / 10.0
                qry = qry.filter(avg_eff >= thr)
        except Exception:
            pass

    if sort == "thc_desc" and thc_col is not None:
        qry = qry.order_by(thc_col.desc())
    elif sort == "cbd_desc" and cbd_col is not None:
        qry = qry.order_by(cbd_col.desc())
    elif sort == "cbn_desc" and cbn_col is not None:
        qry = qry.order_by(cbn_col.desc())
    elif sort == "qol_desc" and avg_eff is not None:
        qry = qry.order_by(avg_eff.desc())
    
    else:
        order_col = getattr(Product, "created_at", None) or getattr(Product, "datetime", None) or Product.id
        qry = qry.order_by(order_col.desc())

    pagination = qry.paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        "patient/product_list.html",
        products=pagination.items,
        pagination=pagination,
        classifications=classifications_master(),
        terp_names=terpenes_master(),
        filters=dict(
            q=q,
            classification=classification,
            affliction=affliction,
            thc_min=thc_min,
            thc_max=thc_max,
            cbd_min=cbd_min,
            cbd_max=cbd_max,
            cbn_min=cbn_min,
            cbn_max=cbn_max,
            terpene=terp_list,
            available=available,
            dispensary_id=dispensary_id,
            min_qol=min_qol,
            sort=sort,
        ),
        view_mode=(request.blueprint or "patient"),
    )


@patient_bp.route("/product/grassroots/new", methods=["GET", "POST"], endpoint="product_grassroots_new")
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_grassroots_new():
    Product = _Product()

    # Resolve "next" from query or form, fallback to onboarding hub
    def _nx():
        return request.values.get("next") or _safe("patient.onboarding_hub")

    if request.method == "GET":
        return render_template(
            "patient/product_grassroots_new.html",
            affliction_list=AFFLICTION_LIST(),
            application_methods=application_method_choices(),
            classifications=classifications_master(),
            terpenes_master=terpenes_master(),
            prefill_name=(request.args.get("q") or None),
            next_url=_nx(),
        )

    # POST
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("Product name is required.", "error")
        return redirect(url_for("patient.product_grassroots_new", next=_nx(), q=request.form.get("name", "").strip()))

    if not Product:
        flash("Products are not enabled in this deployment.", "error")
        return redirect(_nx())

    p = Product()

    # Review state ? pending (first matching field wins)
    for fld in ("approval_status", "status", "state"):
        if hasattr(p, fld):
            try:
                setattr(p, fld, "pending")
            except Exception:
                pass
            break

    # Basic fields
    for key in ("brand", "application_method", "classification", "affliction"):
        val = (request.form.get(key) or "").strip() or None
        if val is not None and hasattr(p, key):
            setattr(p, key, val)

    if hasattr(p, "name"):
        p.name = name

    # Stamp SIDs and audit
    user_sid = getattr(current_user, "sid", None)
    if user_sid:
        for fld in ("sid", "patient_sid", "user_sid", "owner_sid", "creator_sid", "submitted_by_sid"):
            if hasattr(p, fld):
                try: setattr(p, fld, user_sid)
                except Exception: pass
    for fld in ("submitted_by_id", "creator_id", "created_by_id", "user_id", "owner_id"):
        if hasattr(p, fld):
            try: setattr(p, fld, current_user.id)
            except Exception: pass
            break
    for rel in ("submitted_by", "creator", "created_by", "user", "owner"):
        if hasattr(p, rel):
            try: setattr(p, rel, current_user)
            except Exception: pass
            break

    try:
        db.session.add(p)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Grassroots product create failed: %s", e)
        flash("We couldn't save your product. Please try again.", "error")
        return redirect(url_for("patient.product_grassroots_new", next=_nx(), q=name))

    if request.is_json:
        return jsonify({"ok": True, "product_id": getattr(p, "id", None), "name": getattr(p, "name", name)})

    # After creating a product, go through the check-in entry (gates baseline if needed)
    checkin_ep = (
        "patient.checkin_entry" if "patient.checkin_entry" in current_app.view_functions else
        ("patient.checkins_hub" if "patient.checkins_hub" in current_app.view_functions else "patient.onboarding_hub")
    )
    return redirect(_safe(checkin_ep, new_product_id=getattr(p, "id", None), new_product_name=getattr(p, "name", name)))


@patient_bp.get("/products/<int:product_id>/modal", endpoint="product_modal")
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_modal(product_id: int):
    Product = _Product()
    if not Product:
        from flask import abort
        abort(404)
    product = Product.query.get_or_404(product_id)
    return render_template("patient/partials/product_modal.html", product=product)


def _status(p):
    for fld in ("approval_status", "status", "state"):
        if hasattr(p, fld):
            val = getattr(p, fld, None)
            if isinstance(val, str):
                s = val.strip().lower()
                if s:
                    return s
    return None

def _is_approved(p):
    return (_status(p) or "") in {"approved", "published", "active", "final", "locked", "stamped"}

def _is_editable_by_patient(p):
    # Patients can only edit grassroots/unapproved
    return not _is_approved(p)

# --- QoL computation (average positive delta in points on 0?100 scale) + upvotes ---
def _w_time(w):
    for t in ("created_at", "last_checkin_at", "updated_at", "datetime", "timestamp", "created"):
        if hasattr(w, t):
            return getattr(w, t)
    return None

def _w_score(w):
    for f in ("qol_score", "overall_score", "total_score", "overall"):
        if hasattr(w, f):
            v = getattr(w, f, None)
            if v is not None:
                try: return float(v)
                except Exception: pass
    return None

def _u_time(u):
    for t in ("created_at", "last_checkin_at", "datetime", "timestamp", "created"):
        if hasattr(u, t):
            return getattr(u, t)
    return None

def _u_sid(u):
    for f in ("sid", "patient_sid", "user_sid", "owner_sid", "creator_sid", "submitted_by_sid"):
        if hasattr(u, f):
            v = getattr(u, f, None)
            if v: return v
    return None

def _compute_qol_improvement_and_upvotes(product_id: int, *, window_hours: int = 8,
                                         lookback_days: int = 180, max_usage: int = 5000):
    """
    Avg QoL Improvement (%) = mean of positive deltas (AFTER - BEFORE) where both are within window_hours of usage.
    Upvotes = count of positive deltas. 1 point on 0?100 scale = 1%.
    """
    Usage = _UsageModel()
    WC = _WellnessModel()
    out = dict(upvotes=0, avg_improvement_pct=None, samples=0, last_delta_pct=None, last_when=None)
    examples = []
    if not Usage or not WC or not hasattr(Usage, "product_id"):
        return out, examples

    since = _dt.utcnow() - _td(days=lookback_days)

    try:
        uq = db.session.query(Usage).filter(Usage.product_id == product_id)
        tcol = None
        for t in ("created_at", "last_checkin_at", "datetime", "timestamp", "created"):
            if hasattr(Usage, t):
                tcol = getattr(Usage, t); break
        if tcol is not None:
            uq = uq.filter(tcol >= since).order_by(tcol.asc())
        usages = uq.limit(max_usage).all()
    except Exception:
        usages = []

    if not usages:
        return out, examples

    by_sid = defaultdict(list)
    for u in usages:
        sid, ts = _u_sid(u), _u_time(u)
        if sid and ts: by_sid[sid].append(ts)
    sids = list(by_sid.keys())
    if not sids:
        return out, examples

    wc_time = None
    for t in ("created_at", "last_checkin_at", "updated_at", "datetime", "timestamp", "created"):
        if hasattr(WC, t):
            wc_time = getattr(WC, t); break
    wc_sid = None
    for f in ("sid", "patient_sid", "user_sid"):
        if hasattr(WC, f):
            wc_sid = getattr(WC, f); break
    if wc_time is None or wc_sid is None:
        return out, examples

    try:
        wrows = (db.session.query(WC)
                 .filter(wc_sid.in_(sids))
                 .filter(wc_time >= since - _td(days=7))
                 .order_by(wc_sid.asc(), wc_time.asc())
                 .all())
    except Exception:
        wrows = []

    w_by_sid = defaultdict(list)
    for w in wrows:
        sid_val = None
        for f in ("sid", "patient_sid", "user_sid"):
            if hasattr(w, f):
                sid_val = getattr(w, f, None)
                if sid_val: break
        ts, sc = _w_time(w), _w_score(w)
        if sid_val and ts is not None and sc is not None:
            w_by_sid[sid_val].append((ts, sc))

    window = _td(hours=window_hours)
    positives, pairs = [], 0

    for sid, use_times in by_sid.items():
        wlist = w_by_sid.get(sid, [])
        if not wlist: continue
        for t_use in use_times:
            before = after = None
            for ts, sc in reversed(wlist):
                if ts <= t_use and (t_use - ts) <= window:
                    before = (ts, sc); break
                if ts < t_use - window: break
            for ts, sc in wlist:
                if ts >= t_use and (ts - t_use) <= window:
                    after = (ts, sc); break
                if ts > t_use + window: break
            if before and after:
                pairs += 1
                delta_pts = after[1] - before[1]
                delta_pct = float(delta_pts)
                out["last_delta_pct"] = delta_pct
                out["last_when"] = after[0]
                examples.append(dict(when=after[0], delta_pct=delta_pct, before=before[1], after=after[1]))
                if delta_pts > 0:
                    positives.append(delta_pct)

    out["samples"] = pairs
    out["upvotes"] = len(positives)
    out["avg_improvement_pct"] = (sum(positives) / len(positives)) if positives else None
    return out, examples

# ------------------------------
# Product Detail
# ------------------------------
@patient_bp.get("/product/<int:product_id>", endpoint="product_detail")
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)

    # ---------- CHEMICAL PROFILE ----------
    chem_profile = getattr(product, "profile", None)
    thc_percent = chem_profile.thc_percent if chem_profile else 0
    cbd_percent = chem_profile.cbd_percent if chem_profile else 0
    cbn_percent = chem_profile.cbn_percent if chem_profile else 0
    chem_type = chem_profile.chem_type if chem_profile else "n/a"

    # ---------- TERPENES ----------
    product_terpenes = list(getattr(product, "terpenes", []))

    # ---------- AGGREGATE / QOL SCORE ----------
    agg = getattr(product, "aggregate_score", None)
    qol_score = 0
    total_votes = 0
    min_qol = 0
    avg_qol = 0
    max_qol = 0

    if agg:
        total_votes = agg.total_votes or 0
        min_qol = agg.min_qol or 0
        avg_qol = agg.avg_qol or 0
        max_qol = agg.max_qol or 0
        qol_score = int(avg_qol)

    # ---------- STAR STRING ----------
    def stars_from_qol(q):
        if q is None or q <= 0:
            return "?" * 5
        n = max(1, min(5, int(round((q / 100.0) * 5.0))))
        return "?" * n + "?" * (5 - n)

    star_string = stars_from_qol(qol_score)

    # ---------- PREFERRED / NEARBY DISPENSARIES ----------
    preferred_dispensary, nearby_dispensaries = get_nearby_dispensaries(current_user, product)

    # ---------- INVENTORY REPORTS ----------
    inventory_reports = list(product.inventory_reports)
    report_count = len(inventory_reports)
    prices = []
    inventory_total = 0
    per_ent = {}

    for r in inventory_reports:
        ent_id = None
        for cand in ("enterprise_id", "user_id", "dispensary_id"):
            ent_id = getattr(r, cand, None)
            if ent_id is not None:
                break
        price = float(r.price) if r.price is not None else None
        qty = int(r.quantity or 0)
        inventory_total += qty
        if price is not None:
            prices.append(price)

        if ent_id is None:
            continue
        ent = per_ent.setdefault(ent_id, {"price": None, "qty": 0, "latest_at": None})
        if price is not None and (ent["price"] is None or price < ent["price"]):
            ent["price"] = price
        ent["qty"] += qty
        reported_at = getattr(r, "reported_at", None)
        if reported_at and (ent["latest_at"] is None or reported_at > ent["latest_at"]):
            ent["latest_at"] = reported_at

    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    avg_price = (sum(prices) / len(prices)) if prices else None

    dispensary_prices = []
    for ent_id, info in per_ent.items():
        disp = Dispensary.query.filter_by(user_id=ent_id).first()
        name = disp.name if disp else f"Enterprise #{ent_id}"
        dispensary_prices.append({
            "enterprise_id": ent_id,
            "name": name,
            "price": info["price"],
            "quantity": info["qty"],
            "reported_at": info["latest_at"],
        })

    # ---------- VOTES ----------
    vote_count = 0
    user_voted = False
    if 'Upvote' in globals():
        try:
            vote_count = Upvote.query.filter_by(target_type="product", target_id=product.id).count()
            if getattr(current_user, "id", None):
                user_voted = Upvote.query.filter_by(
                    target_type="product", target_id=product.id, user_id=current_user.id
                ).count() > 0
        except Exception:
            vote_count = 0
            user_voted = False

    # ---------- RENDER ----------
    return render_template(
        "patient/product_detail.html",
        product=product,
        product_terpenes=product_terpenes,
        dispensary_prices=dispensary_prices,
        agg=agg,
        min_price=min_price,
        max_price=max_price,
        avg_price=avg_price,
        chem_profile=chem_profile,
        thc_percent=thc_percent,
        cbd_percent=cbd_percent,
        cbn_percent=cbn_percent,
        chem_type=chem_type,
        inventory_total=inventory_total,
        inventory_reports=inventory_reports,
        report_count=report_count,
        qol_score=qol_score,
        star_string=star_string,
        vote_count=vote_count,
        user_voted=user_voted,
        preferred_dispensary=preferred_dispensary,
        nearby_dispensaries=nearby_dispensaries,
         min_qol=agg.min_qol if agg else 0,
        avg_qol=agg.avg_qol if agg else 0,
        max_qol=agg.max_qol if agg else 0,
    )


# ------------------------------
# Helper: nearby dispensaries
# ------------------------------
def get_nearby_dispensaries(patient, product, radius_miles=25, max_results=5):
    """
    Returns (preferred_dispensary, nearby_dispensaries)
    """
    from app.models import InventoryReport, Dispensary

    patient_coords = get_entity_coords(patient)
    if not patient_coords:
        return None, []

    # Query all inventory for this product
    inventory_rows = InventoryReport.query.filter_by(product_id=product.id).all()
    if not inventory_rows:
        return None, []

    nearby = []
    preferred = None

    for inv in inventory_rows:
        dispensary = inv.dispensary  # assumes FK from InventoryReport ? Dispensary
        if not dispensary:
            continue

        # Availability and pricing
        qty = int(inv.quantity or 0)
        price = float(inv.price) if inv.price is not None else None
        availability = qty > 0

        # Distance
        disp_coords = get_entity_coords(dispensary)
        dist = distance_miles(patient_coords, disp_coords) if (patient_coords and disp_coords) else None

        dispensary_info = {
            "name": dispensary.name,
            "price": price,
            "quantity": qty,
            "availability": availability,
            "distance": round(dist, 1) if dist is not None else None,
        }

        if getattr(patient, "preferred_dispensary_id", None) == dispensary.id:
            preferred = dispensary_info
        else:
            nearby.append(dispensary_info)

    # Sort nearby dispensaries by distance
    nearby = [d for d in nearby if d["distance"] is not None]
    nearby.sort(key=lambda x: x["distance"])

    return preferred, nearby[:max_results]



@patient_bp.route("/products/<int:product_id>/edit", methods=["GET", "POST"], endpoint="product_edit")
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_edit(product_id: int):
    Product = _Product()
    if not Product:
        flash("Products model not available.", "warning")
        return redirect(url_for("patient.onboarding_hub"))

    p = Product.query.get_or_404(product_id)

    def _status(p):
        for fld in ("approval_status", "status", "state"):
            if hasattr(p, fld):
                val = getattr(p, fld, None)
                if isinstance(val, str):
                    s = val.strip().lower()
                    if s:
                        return s
        return None

    def _is_locked(p):
        return _status(p) in ("approved", "published", "active", "final", "locked", "stamped")

    if _is_locked(p):
        flash("This product has been approved and can no longer be crowd-edited.", "info")
        return redirect(url_for("patient.product_detail", product_id=product_id))

    if request.method == "GET":
        return render_template(
            "patient./product_edit.html",
            product=p,
            classifications=classifications_master(),
            terp_names=terpenes_master(),
            is_grassroots=True,
        )

    form = request.form
    files = request.files

    def _get(name):
        v = form.get(name)
        return v.strip() if isinstance(v, str) else v

    for key in ("name", "brand", "description", "category", "classification", "application_method", "affliction", "strain", "form"):
        val = _get(key)
        if val not in (None, "") and hasattr(p, key):
            setattr(p, key, val)

    def _to_num(x):
        try:
            if x is None or str(x).strip() == "":
                return None
            return float(str(x).replace("%", "").strip())
        except Exception:
            return None

    thc = _to_num(form.get("thc_pct") or form.get("thc_percent") or form.get("thc"))
    cbd = _to_num(form.get("cbd_pct") or form.get("cbd_percent") or form.get("cbd"))
    cbn = _to_num(form.get("cbn_pct") or form.get("cbn_percent") or form.get("cbn"))

    if thc is not None:
        for fld in ("thc_pct", "thc_percent", "thc"):
            if hasattr(p, fld):
                setattr(p, fld, thc)
                break
    if cbd is not None:
        for fld in ("cbd_pct", "cbd_percent", "cbd"):
            if hasattr(p, fld):
                setattr(p, fld, cbd)
                break
    if cbn is not None:
        for fld in ("cbn_pct", "cbn_percent", "cbn"):
            if hasattr(p, fld):
                setattr(p, fld, cbn)
                break        
            

    img = files.get("image")
    if img and getattr(img, "filename", None):
        saved = _save_product_image(img)
        if saved:
            for fld in ("image_path", "image_url", "image"):
                if hasattr(p, fld):
                    setattr(p, fld, saved)
                    break
        else:
            flash("Could not save image (allowed: png, jpg, jpeg, gif, webp).", "warning")

    try:
        db.session.add(p)
        db.session.commit()
        flash("Product updated. Thanks for contributing!", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Grassroots product edit failed: %s", e)
        flash("We couldn't save your edits. Please try again.", "danger")

    return redirect(url_for("patient.product_detail", product_id=product_id))


@patient_bp.route("/products/my_submissions", methods=["GET"], endpoint="product_mysubmissions")
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_mysubmissions():
    Product = _Product()
    uid = getattr(current_user, "id", None)
    rows = []
    if Product and uid is not None:
        conds = []
        for fld in ("submitted_by_id", "creator_id", "created_by_id", "user_id", "owner_id"):
            if hasattr(Product, fld):
                conds.append(getattr(Product, fld) == uid)
        for rel in ("submitted_by", "creator", "created_by", "user", "owner"):
            if hasattr(Product, rel):
                try:
                    conds.append(getattr(Product, rel).has(id=uid))
                except Exception:
                    pass
        if conds:
            order_col = getattr(Product, "created_at", None) or getattr(Product, "datetime", None) or getattr(Product, "created", None) or Product.id
            rows = Product.query.filter(or_(*conds)).order_by(order_col.desc()).all()
    return render_template("patient/product_mysubmissions.html", submitted_products=rows)


def _fetch_profile():
    try:
        # if your patient.py already defines _get_profile(), this will call it
        return _get_profile()
    except Exception:
        return PatientProfile.query.filter_by(user_id=getattr(current_user, "id", None)).first()


# Allowed application methods ? edit these to match any constants you already have
APPLICATION_METHODS = [
    "Inhalation",
    "Oral",
    "Topical",
    "Sublingual",
    "Vape",
    "Other",
]

@patient_bp.route("/products/<int:usage_id>/update", methods=["POST"], endpoint="update_product_usage")
@login_required
@role_required(UserRoleEnum.PATIENT)
def update_product_usage(usage_id):
    from app.models import PatientProductUsage
    usage = db.session.get(PatientProductUsage, usage_id)
    if not usage or usage.sid != current_user.sid:
        abort(404)

    dosage = request.form.get("dosage_mg")
    frequency = request.form.get("times_per_day")

    if dosage: usage.dosage_mg = dosage
    if frequency: usage.times_per_day = frequency

    db.session.commit()
    flash("Product usage updated.", "success")
    return redirect(url_for("patient.patient_dashboard"))

@patient_bp.route("/products/confirm", methods=["POST"], endpoint="confirm_product_list")
@login_required
@role_required(UserRoleEnum.PATIENT)
def confirm_product_list():
    sid = current_user.sid
    if request.form.get("no_change"):
        # log that the patient confirmed their product list without changes
        flash("Product list confirmed.", "success")
    return redirect(url_for("patient.patient_dashboard"))


# ------------------
# Root tabbed page
# ------------------
@patient_bp.route("/record", methods=["GET"], endpoint="record")
@login_required
def record():
    profile = db.session.get(PatientProfile, current_user.sid)
    prefs = PatientPreference.query.filter_by(patient_id=current_user.sid).first()
    medications = PatientMedication.query.filter_by(patient_id=current_user.sid).all()
    history = PatientMedicalHistory.query.filter_by(patient_id=current_user.sid).all()

    return render_template(
        "patient/patient_record.html",
        profile=profile,
        prefs=prefs,
        medications=medications,
        history=history,
    )

# ------------------
# Tab 1: Mandatory Info
# ------------------
@patient_bp.route("/record/save/mandatory", methods=["POST"])
@login_required
def record_save_mandatory():
    data = request.get_json() or {}
    profile = db.session.get(PatientProfile, current_user.sid)
    if not profile:
        return jsonify({"ok": False, "error": "Profile not found"}), 404

    # Mandatory fields
    name = data.get("full_name", "").strip()
    alias = data.get("alias", "").strip()
    email = data.get("email", "").strip()
    zip_code = data.get("zip_code", "").strip()
    password = data.get("password", "").strip()

    if not all([name, alias, email, zip_code, password]):
        return jsonify({"ok": False, "error": "All mandatory fields must be filled"}), 400

    try:
        profile.full_name = name
        profile.alias = alias
        current_user.alias_name = alias
        current_user.alias_slug = re.sub(r"[^a-z0-9\-]+", "-", alias.lower()).strip("-") or "user"
        profile.zip_code = zip_code
        current_user.email = email
        if password:
            current_user.set_password(password)  # assuming your User model has set_password()
        db.session.add(profile)
        db.session.add(current_user)
        db.session.commit()
        return jsonify({"ok": True})
    except SQLAlchemyError as e:
        db.session.rollback()
        current_app.logger.exception(e)
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------
# Tab 2: Demographics & Current Health
# ------------------
@patient_bp.route("/record/save/demographics", methods=["POST"])
@login_required
def record_save_demographics():
    data = request.get_json() or {}
    profile = db.session.get(PatientProfile, current_user.sid)
    if not profile:
        return jsonify({"ok": False, "error": "Profile not found"}), 404

    try:
        profile.sex = data.get("sex")
        profile.address = data.get("address")
        profile.city = data.get("city")
        profile.state = data.get("state")
        profile.country = data.get("country")
        profile.height_feet = data.get("height_feet")
        profile.height_inches = data.get("height_inches")
        profile.weight_lbs = data.get("weight_lbs")
        profile.cannabis_use_start_age = data.get("cannabis_use_start_age")
        profile.cannabis_use_frequency = data.get("cannabis_use_frequency")
        profile.cannabis_use_characterization = data.get("cannabis_use_characterization")
        db.session.add(profile)
        db.session.commit()
        return jsonify({"ok": True})
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------
# Tab 3: Medical History
# ------------------
@patient_bp.route("/record/save/medical_history", methods=["POST"])
@login_required
def record_save_medical_history():
    data = request.get_json() or {}
    profile_id = current_user.sid

    try:
        # Example: Replace existing medications and conditions with new data
        meds = data.get("medications", [])
        history = data.get("history", [])

        # Clear old
        PatientMedication.query.filter_by(patient_id=profile_id).delete()
        PatientMedicalHistory.query.filter_by(patient_id=profile_id).delete()
        db.session.flush()

        for med in meds:
            db.session.add(PatientMedication(patient_id=profile_id, **med))

        for cond in history:
            db.session.add(PatientMedicalHistory(patient_id=profile_id, **cond))

        db.session.commit()
        return jsonify({"ok": True})
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500

# ------------------
# Tab 4: Patient Notes / Record
# ------------------
@patient_bp.route("/record/save/notes", methods=["POST"])
@login_required
def record_save_notes():
    data = request.get_json() or {}
    profile = db.session.get(PatientProfile, current_user.sid)
    if not profile:
        return jsonify({"ok": False, "error": "Profile not found"}), 404

    try:
        profile.patient_notes = data.get("notes")
        db.session.add(profile)
        db.session.commit()
        return jsonify({"ok": True})
    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500


# =============================================================================
# ROUTES ? SECURITY / PRIVACY
# =============================================================================
@patient_bp.route("/security", methods=["GET"], endpoint="security")
@login_required
@role_required(UserRoleEnum.PATIENT)
def security():
    profile = _get_profile()
    return render_template("patient/security.html", profile=profile)


@patient_bp.route("/security/save", methods=["POST"], endpoint="security_save")
@login_required
@role_required(UserRoleEnum.PATIENT)
def security_save():
    profile = _get_profile()
    if not profile:
        flash("Profile not found.", "danger")
        return redirect(url_for("patient.security"))
    form = request.form
    try:
        def as_bool(key: str) -> bool:
            return form.get(key) in ("on", "true", "1", "yes")
        if hasattr(profile, "public_profile_enabled"):
            profile.public_profile_enabled = as_bool("public_profile_enabled")
        if hasattr(profile, "show_alias"):
            profile.show_alias = as_bool("show_alias")
        if hasattr(profile, "show_reviews"):
            profile.show_reviews = as_bool("show_reviews")
        if hasattr(profile, "show_wellness"):
            profile.show_wellness = as_bool("show_wellness")
        db.session.commit()
        flash("Security & sharing settings updated.", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Failed to save security settings: %s", e)
        flash("Could not update settings.", "danger")

# ---------- Edit Background (GET/POST) ----------
@patient_bp.route("/background/edit", methods=["GET", "POST"], endpoint="edit_background")
@login_required
@role_required(UserRoleEnum.PATIENT)
def edit_background():
    from datetime import datetime as _dt
    Profile = _PatientProfile()
    if not Profile:
        flash("Profile unavailable.", "danger")
        return redirect(url_for("patient.onboarding_hub"))

    sid = getattr(current_user, "sid", None)
    if not sid:
        flash("Missing ID; please re-login.", "danger")
        return redirect(url_for("patient.onboarding_hub"))

    prof = db.session.get(Profile, sid)
    if prof is None:
        prof = Profile(sid=sid)
        if hasattr(prof, "user"):
            prof.user = current_user
        db.session.add(prof)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    if request.method == "GET":
        return render_template("patient/edit_background.html", profile=prof)

    form = request.form

    def _assign(obj, attr_names, value):
        if value in (None, ""):
            return False
        for a in (attr_names if isinstance(attr_names, (list, tuple)) else [attr_names]):
            if hasattr(obj, a):
                setattr(obj, a, value)
                return True
        return False

    _assign(prof, "full_name", (form.get("name") or "").strip())

    dob_raw = (form.get("dob") or "").strip()
    if dob_raw:
        parsed = None
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
            try:
                parsed = _dt.strptime(dob_raw, fmt).date()
                break
            except Exception:
                continue
        if parsed:
            _assign(prof, ["dob", "date_of_birth", "birth_date"], parsed)

    zip_in = (form.get("zip_code") or "").strip()
    if zip_in:
        _assign(prof, ["zip_code", "postal_code", "zip"], zip_in)

    email_in = (form.get("email") or "").strip()
    if email_in:
        current_user.email = email_in
        _assign(prof, "email", email_in)

    try:
        db.session.add(current_user)
        db.session.add(prof)
        db.session.flush()  # surface integrity errors here
        db.session.commit()
        flash("Background updated.", "success")
    except Exception as e:
        db.session.rollback()
        try:
            current_app.logger.exception("edit_background commit failed: %s", e)
        except Exception:
            pass
        flash("Could not save your background.", "danger")

    return redirect(url_for("patient.edit_background"))

# ---------- Edit Alias (GET/POST) ----------
@patient_bp.route("/alias/edit", methods=["GET", "POST"], endpoint="edit_alias")
@login_required
@role_required(UserRoleEnum.PATIENT)
def edit_alias():
    Profile = _PatientProfile()
    sid = getattr(current_user, "sid", None)

    if request.method == "GET":
        # Prefill
        alias_val = (
            getattr(current_user, "alias_name", None)
            or getattr(current_user, "alias", None)
        )
        if not alias_val and Profile and sid:
            prof = db.session.get(Profile, sid)
            if prof is not None and hasattr(prof, "alias"):
                alias_val = getattr(prof, "alias") or ""
        return render_template("patient/edit_alias.html", alias=alias_val or "")

    alias_in = (request.form.get("alias") or "").strip()
    if not alias_in:
        flash("Alias is required.", "warning")
        return redirect(url_for("patient.edit_alias"))

    # Save to User
    current_user.alias_name = alias_in
    try:
        current_user.alias_slug = re.sub(r"[^a-z0-9\-]+", "-", alias_in.lower()).strip("-") or "user"
    except Exception:
        pass
    # Keep legacy current_user.alias in sync for templates expecting it
    try:
        setattr(current_user, "alias", alias_in)
    except Exception:
        pass

    # Also mirror to profile.alias if present
    if Profile and sid:
        prof = db.session.get(Profile, sid) or Profile(sid=sid)
        if hasattr(prof, "alias"):
            setattr(prof, "alias", alias_in)
        db.session.add(prof)

    try:
        db.session.add(current_user)
        db.session.flush()
        db.session.commit()
        flash("Alias updated.", "success")
    except Exception as e:
        db.session.rollback()
        try:
            current_app.logger.exception("edit_alias commit failed: %s", e)
        except Exception:
            pass
        flash("Could not save alias.", "danger")

    return redirect(url_for("patient.edit_alias"))


@patient_bp.route("/settings-dashboard", methods=["GET"], endpoint="settings_dashboard")
@login_required
@role_required(UserRoleEnum.PATIENT)
def settings_dashboard():
    profile = _get_profile()
    prefs = PatientPreference.query.filter_by(patient_id=profile.sid).first()
    return render_template(
        "patient/settings_dashboard.html",
        profile=profile,
        prefs=prefs
    )

# =============================================================================
# ROUTES ? SUPPORT GROUPS (for dashboard card)
# =============================================================================
@patient_bp.get("/groups", endpoint="groups")
@login_required
@role_required(UserRoleEnum.PATIENT)
def groups():
    SupportGroup, GroupMember = _GroupModels()
    mine = []
    if SupportGroup and GroupMember:
        try:
            mine = (
                db.session.query(SupportGroup)
                .join(GroupMember, GroupMember.group_id == SupportGroup.id)
                .filter(GroupMember.user_id == current_user.id)
                .order_by(SupportGroup.id.desc())
                .limit(50)
                .all()
            )
        except Exception:
            mine = []
    return render_template("patient/groups.html", groups=mine)


@patient_bp.get("/api/groups/typeahead", endpoint="groups_typeahead")
@login_required
@role_required(UserRoleEnum.PATIENT)
def groups_typeahead():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    SupportGroup, _ = _GroupModels()
    if not SupportGroup:
        return jsonify([])
    like = f"%{q}%"
    rows = (
        db.session.query(SupportGroup)
        .filter(or_(getattr(SupportGroup, "name", None).ilike(like) if hasattr(SupportGroup, "name") else False))
        .order_by(getattr(SupportGroup, "name", SupportGroup.id).asc())
        .limit(10)
        .all()
    )
    return jsonify([{"id": getattr(r, "id", None), "name": getattr(r, "name", "Group")} for r in rows])


@patient_bp.post("/groups/join", endpoint="groups_join")
@login_required
@role_required(UserRoleEnum.PATIENT)
def groups_join():
    gid = request.form.get("group_id", type=int)
    SupportGroup, GroupMember = _GroupModels()
    if not gid or not GroupMember:
        return redirect(url_for("patient.groups"))
    try:
        exists = db.session.query(GroupMember).filter(GroupMember.user_id == current_user.id, GroupMember.group_id == gid).first()
        if not exists:
            row = GroupMember(user_id=current_user.id, group_id=gid)
            db.session.add(row)
            db.session.commit()
            flash("Joined group.", "success")
    except Exception:
        db.session.rollback()
        flash("Unable to join group.", "danger")
    return redirect(url_for("patient.groups"))

# =============================================================================
# ROUTES ? MASTER LIST JSON (for dropdowns / typeahead sources)
# =============================================================================
@patient_bp.get("/api/master/afflictions", endpoint="api_master_afflictions")
@login_required
@role_required(UserRoleEnum.PATIENT)
def api_master_afflictions():
    return jsonify(get_afflictions())


@patient_bp.get("/api/master/terpenes", endpoint="api_master_terpenes")
@login_required
@role_required(UserRoleEnum.PATIENT)
def api_master_terpenes():
    return jsonify(get_common_terpenes())


@patient_bp.get("/api/master/methods", endpoint="api_master_methods")
@login_required
@role_required(UserRoleEnum.PATIENT)
def api_master_methods():
    return jsonify(application_method_choices())

# --- AFFLICTION-BASED GROUPS -----------------------------------------------
def _afflictions_master():
    """Return the master list of afflictions (strings)."""
    out = []
    try:
        from app.constants import AFFLICTIONS as A   # if you keep them here
        out = list(A or [])
    except Exception:
        pass
    if not out:
        try:
            from app import models
            out = list(getattr(models, "AFFLICTIONS", []) or [])
        except Exception:
            pass
    if not out:
        out = list(current_app.config.get("AFFLICTIONS", []) or [])
    return [str(x).strip() for x in out if str(x).strip()]

def _aff_key(name: str) -> str:
    """slug: 'Parkinson's Disease' -> 'parkinsons-disease'"""
    s = (name or "").lower()
    s = re.sub(r"[?'`]", "", s)              # drop apostrophes
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "group"

def _aff_name_from_key(key: str) -> str:
    key = (key or "").strip().lower()
    for a in _afflictions_master():
        if _aff_key(a) == key or a.lower() == key:
            return a
    return key or "Group"

def _GroupModel():
    try:
        from app import models
        return getattr(models, "SupportGroup", None) or getattr(models, "Group", None)
    except Exception:
        return None

def _GroupMemberModel():
    try:
        from app import models
        return getattr(models, "GroupMember", None) or getattr(models, "Membership", None)
    except Exception:
        return None

def _GroupPostModel():
    try:
        from app import models
        return getattr(models, "GroupPost", None) or getattr(models, "BulletinPost", None)
    except Exception:
        return None

def _GroupLinkModel():
    try:
        from app import models
        return getattr(models, "GroupLink", None) or getattr(models, "GroupResource", None)
    except Exception:
        return None

def _user_sid():
    return getattr(current_user, "sid", None) or getattr(current_user, "id", None)

def _ensure_group_record(name: str, key: str):
    """
    If you have a Group model that only supports numeric FK membership, create/find
    a DB row that represents this affliction. Otherwise return None (virtual mode).
    """
    G = _GroupModel()
    if not G:
        return None
    try:
        q = db.session.query(G)
        row = None
        if hasattr(G, "slug"):
            row = q.filter(getattr(G, "slug") == key).first()
        if not row and hasattr(G, "name"):
            row = q.filter(getattr(G, "name") == name).first()
        if not row:
            row = G()
            if hasattr(row, "name"): row.name = name
            if hasattr(row, "slug"): row.slug = key
            for t in ("created_at", "timestamp"):
                if hasattr(row, t): setattr(row, t, _dt.utcnow())
            db.session.add(row)
            db.session.commit()
        return row
    except Exception:
        db.session.rollback()
        return None

def _is_member(sid, key, name):
    GM = _GroupMemberModel()
    if not GM or not sid:
        return False
    try:
        q = db.session.query(GM)
        cond = []
        if hasattr(GM, "group_key"):
            cond.append(getattr(GM, "group_key") == key)
        elif hasattr(GM, "group_name"):
            cond.append(getattr(GM, "group_name") == name)
        else:
            # fall back to numeric group_id via ensured group record
            G = _ensure_group_record(name, key)
            if G and hasattr(GM, "group_id") and hasattr(G, "id"):
                cond.append(getattr(GM, "group_id") == getattr(G, "id"))
        for u in ("sid", "user_sid", "patient_sid"):
            if hasattr(GM, u): cond.append(getattr(GM, u) == sid)
        return bool(q.filter(*cond).first()) if cond else False
    except Exception:
        return False

def _member_count(key, name):
    GM = _GroupMemberModel()
    if not GM:
        return 0
    try:
        q = db.session.query(GM)
        if hasattr(GM, "group_key"):
            return q.filter(getattr(GM, "group_key") == key).count()
        if hasattr(GM, "group_name"):
            return q.filter(getattr(GM, "group_name") == name).count()
        G = _ensure_group_record(name, key)
        if G and hasattr(GM, "group_id") and hasattr(G, "id"):
            return db.session.query(GM).filter(getattr(GM, "group_id") == getattr(G, "id")).count()
    except Exception:
        pass
    return 0


# -------------------- DETAIL (bulletin + resources) --------------------
@patient_bp.route("/groups/<group_key>", methods=["GET"], endpoint="group_detail")
@login_required
@role_required(UserRoleEnum.PATIENT)
def group_detail(group_key):
    key = _aff_key(group_key)
    name = _aff_name_from_key(group_key)
    sid = _user_sid()

    joined = _is_member(sid, key, name)

    # Load posts/links keyed by string key/name; fallback to numeric group_id if needed
    P, L = _GroupPostModel(), _GroupLinkModel()
    posts, links = [], []
    try:
        if P:
            q = db.session.query(P)
            if hasattr(P, "group_key"):
                q = q.filter(getattr(P, "group_key") == key)
            elif hasattr(P, "group_name"):
                q = q.filter(getattr(P, "group_name") == name)
            else:
                G = _ensure_group_record(name, key)
                if G and hasattr(P, "group_id") and hasattr(G, "id"):
                    q = q.filter(getattr(P, "group_id") == getattr(G, "id"))
            posts = q.order_by(getattr(P, "created_at", None) or getattr(P, "timestamp", None) or _dt.utcnow()).all()
    except Exception:
        posts = []
    try:
        if L:
            q = db.session.query(L)
            if hasattr(L, "group_key"):
                q = q.filter(getattr(L, "group_key") == key)
            elif hasattr(L, "group_name"):
                q = q.filter(getattr(L, "group_name") == name)
            else:
                G = _ensure_group_record(name, key)
                if G and hasattr(L, "group_id") and hasattr(G, "id"):
                    q = q.filter(getattr(L, "group_id") == getattr(G, "id"))
            links = q.order_by(getattr(L, "created_at", None) or getattr(L, "timestamp", None) or _dt.utcnow()).all()
    except Exception:
        links = []

    group = {"key": key, "name": name, "description": f"Support for {name}"}
    return render_template("patient/group_detail.html", group=group, posts=posts, links=links, docs=[], joined=joined)

# -------------------- JOIN --------------------
@patient_bp.route("/groups/join", methods=["POST"], endpoint="group_join")
@login_required
@role_required(UserRoleEnum.PATIENT)
def group_join():
    raw = request.form.get("group_key") or request.form.get("group_id") or (request.json.get("group_key") if request.is_json else None)
    next_url = request.values.get("next")
    name = _aff_name_from_key(raw)
    key = _aff_key(name)
    sid = _user_sid()
    if not key or not sid:
        flash("Missing group or user.", "danger")
        return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))

    GM = _GroupMemberModel()
    if not GM:
        flash("Groups not available.", "danger")
        return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))

    try:
        m = GM()
        # Prefer string-key storage if available
        if hasattr(m, "group_key"): m.group_key = key
        if hasattr(m, "group_name"): m.group_name = name
        # Fallback to numeric:
        if (hasattr(m, "group_id") and not getattr(m, "group_id", None)):
            G = _ensure_group_record(name, key)
            if G and hasattr(G, "id"):
                m.group_id = getattr(G, "id")
        for u in ("sid", "user_sid", "patient_sid"):
            if hasattr(m, u): setattr(m, u, sid)
        for t in ("created_at", "joined_at", "timestamp"):
            if hasattr(m, t): setattr(m, t, _dt.utcnow())
        db.session.add(m)
        db.session.commit()
        flash("Joined group.", "success")
    except Exception as e:
        db.session.rollback()
        try: current_app.logger.exception("group_join failed: %s", e)
        except Exception: pass
        flash("Could not join group.", "danger")
    return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))

# -------------------- LEAVE --------------------
@patient_bp.route("/groups/leave", methods=["POST"], endpoint="group_leave")
@login_required
@role_required(UserRoleEnum.PATIENT)
def group_leave():
    raw = request.form.get("group_key") or request.form.get("group_id") or (request.json.get("group_key") if request.is_json else None)
    next_url = request.values.get("next")
    name = _aff_name_from_key(raw)
    key = _aff_key(name)
    sid = _user_sid()
    GM = _GroupMemberModel()
    if not GM or not sid or not key:
        flash("Missing data.", "danger")
        return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))
    try:
        q = db.session.query(GM)
        cond = []
        if hasattr(GM, "group_key"): cond.append(getattr(GM, "group_key") == key)
        elif hasattr(GM, "group_name"): cond.append(getattr(GM, "group_name") == name)
        else:
            G = _ensure_group_record(name, key)
            if G and hasattr(GM, "group_id") and hasattr(G, "id"):
                cond.append(getattr(GM, "group_id") == getattr(G, "id"))
        for u in ("sid", "user_sid", "patient_sid"):
            if hasattr(GM, u): cond.append(getattr(GM, u) == sid)
        if cond:
            q.filter(*cond).delete(synchronize_session=False)
            db.session.commit()
        flash("Left group.", "success")
    except Exception as e:
        db.session.rollback()
        try: current_app.logger.exception("group_leave failed: %s", e)
        except Exception: pass
        flash("Could not leave group.", "danger")
    return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))

# -------------------- POST (bulletin) --------------------
@patient_bp.route("/groups/post", methods=["POST"], endpoint="group_post")
@login_required
@role_required(UserRoleEnum.PATIENT)
def group_post():
    P = _GroupPostModel()
    raw = request.form.get("group_key") or request.form.get("group_id")
    content = (request.form.get("content") or "").strip()
    next_url = request.values.get("next")
    if not P or not raw or not content:
        flash("Missing data.", "danger")
        return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))
    name = _aff_name_from_key(raw)
    key = _aff_key(name)
    try:
        row = P()
        if hasattr(row, "group_key"): row.group_key = key
        if hasattr(row, "group_name"): row.group_name = name
        if not (hasattr(row, "group_key") or hasattr(row, "group_name")):
            G = _ensure_group_record(name, key)
            if G and hasattr(row, "group_id") and hasattr(G, "id"):
                row.group_id = getattr(G, "id")
        for u in ("sid", "user_sid", "patient_sid"):
            if hasattr(row, u): setattr(row, u, _user_sid())
        for c in ("content", "body", "text"):
            if hasattr(row, c): setattr(row, c, content)
        for t in ("created_at", "timestamp", "posted_at"):
            if hasattr(row, t): setattr(row, t, _dt.utcnow())
        db.session.add(row); db.session.commit()
        flash("Posted.", "success")
    except Exception as e:
        db.session.rollback()
        try: current_app.logger.exception("group_post failed: %s", e)
        except Exception: pass
        flash("Could not post.", "danger")
    return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))

# -------------------- ADD LINK (resource) --------------------
@patient_bp.route("/groups/add_link", methods=["POST"], endpoint="group_add_link")
@login_required
@role_required(UserRoleEnum.PATIENT)
def group_add_link():
    L = _GroupLinkModel()
    raw = request.form.get("group_key") or request.form.get("group_id")
    url = (request.form.get("url") or "").strip()
    title = (request.form.get("title") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    next_url = request.values.get("next")
    if not L or not raw or not url:
        flash("Missing data.", "danger")
        return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))
    name = _aff_name_from_key(raw)
    key = _aff_key(name)
    try:
        row = L()
        if hasattr(row, "group_key"): row.group_key = key
        if hasattr(row, "group_name"): row.group_name = name
        if not (hasattr(row, "group_key") or hasattr(row, "group_name")):
            G = _ensure_group_record(name, key)
            if G and hasattr(row, "group_id") and hasattr(G, "id"):
                row.group_id = getattr(G, "id")
        if hasattr(row, "url"): row.url = url
        if hasattr(row, "title"): row.title = (title or None)
        for n in ("notes", "summary", "description"):
            if hasattr(row, n): setattr(row, n, notes or None)
        for t in ("created_at", "timestamp", "added_at"):
            if hasattr(row, t): setattr(row, t, _dt.utcnow())
        for u in ("sid", "user_sid", "patient_sid"):
            if hasattr(row, u): setattr(row, u, _user_sid())
        db.session.add(row); db.session.commit()
        flash("Link added.", "success")
    except Exception as e:
        db.session.rollback()
        try: current_app.logger.exception("group_add_link failed: %s", e)
        except Exception: pass
        flash("Could not add link.", "danger")
    return redirect(_safe_next_url(explicit=next_url, default_endpoint="patient.groups"))


# --- END AFFLICTION-BASED GROUPS --------------------------------------------
# -----------------------
# Communications
# -----------------------
@patient_bp.get("/comm/preview", endpoint="comm_preview")
@login_required
@role_required(UserRoleEnum.PATIENT)
def comm_preview():
    """Dashboard preview JSON for communications card (top 5 recent)."""
    try:
        # function-level imports to avoid circular import
        from app.models import Conversation, Message, MessageReceipt

        q = (
            db.session.query(Conversation)
            .join(Message, Message.conversation_id == Conversation.id)
            .join(MessageReceipt, (MessageReceipt.message_id == Message.id) & (MessageReceipt.user_id == current_user.id))
            .order_by(Message.created_at.desc())
            .limit(5)
        )

        rows = [
            {
                "id": conv.id,
                "title": conv.title or ("Broadcast" if getattr(conv, "is_broadcast", False) else ("Group" if getattr(conv, "is_group", False) else "Conversation")),
                "is_broadcast": bool(getattr(conv, "is_broadcast", False)),
                "is_group": bool(getattr(conv, "is_group", False)),
                "when": getattr(conv, "created_at", None).strftime("%b %d, %Y %I:%M %p") if getattr(conv, "created_at", None) else ""
            }
            for conv in q.all()
        ]
        return jsonify({"top": rows})
    except Exception:
        current_app.logger.exception("comm_preview failed")
        return jsonify({"top": []})


@patient_bp.get("/comm", endpoint="communications")
@login_required
@role_required(UserRoleEnum.PATIENT)
def communications():
    """Full communications page (renders patient/comm_full.html)."""
    try:
        from app.models import Conversation
        conversations = (
            db.session.query(Conversation)
            .order_by(Conversation.created_at.desc())
            .limit(50)
            .all()
        )
    except Exception:
        current_app.logger.exception("communications page load failed")
        conversations = []
    return render_template("patient/comm_full.html", conversations=conversations)


# -----------------------
# Friends & Followers
# -----------------------
@patient_bp.get("/friends/preview", endpoint="friends_preview")
@login_required
@role_required(UserRoleEnum.PATIENT)
def friends_preview():
    """Dashboard preview JSON for friends card (top 3 friends)."""
    try:
        from app.models import Friends, User

        q = (
            db.session.query(User)
            .join(Friends, Friends.friend_id == User.id)
            .filter(Friends.user_id == current_user.id)
            .order_by(User.id.desc())
            .limit(3)
        )

        rows = [
            {
                "id": u.id,
                "name": getattr(u, "name", None) or getattr(u, "display_name", "") or f"User {u.id}",
                "status": getattr(u, "status", "")
            }
            for u in q.all()
        ]
        return jsonify({"top": rows})
    except Exception:
        current_app.logger.exception("friends_preview failed")
        return jsonify({"top": []})


@patient_bp.get("/friends", endpoint="friends")
@login_required
@role_required(UserRoleEnum.PATIENT)
def friends_page():
    """Full friends page (renders patient/friends_full.html)."""
    try:
        from app.models import Friends, User

        friends_list = (
            db.session.query(User)
            .join(Friends, Friends.friend_id == User.id)
            .filter(Friends.user_id == current_user.id)
            .order_by(User.id.desc())
            .all()
        )
    except Exception:
        current_app.logger.exception("friends_page failed")
        friends_list = []

    return render_template("patient/friends_full.html", friends=friends_list)


@patient_bp.post("/friends/add", endpoint="friends_add")
@login_required
@role_required(UserRoleEnum.PATIENT)
def friends_add():
    target_id = request.form.get("user_id", type=int)
    if not target_id:
        flash("Missing user.", "warning")
        return redirect(url_for("patient.friends"))

    try:
        from app.models import Friends

        exists = db.session.query(Friends).filter(
            Friends.user_id == current_user.id,
            Friends.friend_id == target_id
        ).first()

        if not exists:
            row = Friends(user_id=current_user.id, friend_id=target_id)
            db.session.add(row)
            db.session.commit()
            flash("Friend added.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("friends_add failed")
        flash("Could not add friend.", "danger")

    return redirect(url_for("patient.friends"))


@patient_bp.post("/friends/remove", endpoint="friends_remove")
@login_required
@role_required(UserRoleEnum.PATIENT)
def friends_remove():
    target_id = request.form.get("user_id", type=int)
    if not target_id:
        return redirect(url_for("patient.friends"))

    try:
        from app.models import Friends
        db.session.query(Friends).filter(
            Friends.user_id == current_user.id,
            Friends.friend_id == target_id
        ).delete()
        db.session.commit()
        flash("Friend removed.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("friends_remove failed")
        flash("Could not remove friend.", "danger")

    return redirect(url_for("patient.friends"))






