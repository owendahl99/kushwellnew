from flask import Blueprint, render_template, url_for, flash, redirect, abort, request, jsonify, current_app  
from flask_login import current_user, login_required
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError  
from app.extensions import db
from app.constants.general_menus import UserRoleEnum
from app.utils.decorators import role_required
# from app.utils.scoring import top_scores
from app.models import (
    PatientProfile,
    WellnessCheck,
    LatestAIRecommendation,
    CurrentPatientProductUsage,
    PatientProductUsage,
    Product,
    PatientPreference,
    User,
    PatientMedication,
    PatientMedicalHistory,
    MessageReceipt,
    Friends,
    SupportGroup,
    GroupMember,   
)
# ------------------------------------------------------------
# Blueprint
# ------------------------------------------------------------
patient_bp = Blueprint("patient", __name__, url_prefix="/patient")

# ------------------------------------------------------------
# Baseline Check-in
# ------------------------------------------------------------
@patient_bp.route("/baseline_checkin", methods=["GET", "POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def baseline_checkin():
    """Handles baseline onboarding wellness + conditions + initial preferences.
    No product attributions or usage are created here.
    """
    from sqlalchemy.exc import SQLAlchemyError

    patient: PatientProfile = PatientProfile.query.filter_by(user_sid=current_user.sid).first()

    if not patient:
        current_app.logger.error("[BaselineCheckin] Patient profile not found for user %s", current_user.sid)
        flash("Patient profile not found.", "danger")
        return redirect(url_for("auth.login"))

    # Redirect if already onboarded
    if patient.onboarding_complete:
        current_app.logger.info("[BaselineCheckin] Patient %s already onboarded. Redirecting.", patient.sid)
        return redirect(url_for("patient.patient_dashboard"))

    alias_name = getattr(current_user, "alias_name", "")

    # ------------------------------------------------------------
    # POST submission (AJAX or fetch)
    # ------------------------------------------------------------
    if request.method == "POST":
        data = request.get_json() or {}
        current_app.logger.info("[BaselineCheckin] Received POST: %s", data)

        try:
            # 1️⃣ Wellness baseline (always created)
            sliders = data.get("sliders", {}) or {}
            current_app.logger.debug("[BaselineCheckin] Sliders received: %s", sliders)

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
            current_app.logger.debug("[BaselineCheckin] WellnessCheck object created for %s", patient.sid)

            # 2️⃣ Conditions / afflictions (optional)
            conditions = data.get("conditions", {}) or {}
            if conditions:
                current_app.logger.debug("[BaselineCheckin] Conditions received: %s", conditions)
                patient.set_afflictions_with_severity(conditions)

            # 3️⃣ Preferences (optional)
            preferences = data.get("preferences", {}) or {}
            if preferences:
                current_app.logger.debug("[BaselineCheckin] Preferences received: %s", preferences)
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
            current_app.logger.info("[BaselineCheckin] Marking patient %s onboarding_complete=True", patient.sid)

            # 5️⃣ Commit session
            db.session.commit()
            current_app.logger.info("[BaselineCheckin] Commit successful for patient %s", patient.sid)

            return jsonify({"status": "ok"}), 200

        except SQLAlchemyError as db_err:
            db.session.rollback()
            current_app.logger.exception("[BaselineCheckin] SQLAlchemyError: %s", db_err)
            return jsonify({"status": "error", "message": str(db_err)}), 500

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("[BaselineCheckin] General Exception: %s", e)
            return jsonify({"status": "error", "message": str(e)}), 500

    # ------------------------------------------------------------
    # GET: render baseline check-in form
    # ------------------------------------------------------------
    current_app.logger.info("[BaselineCheckin] Rendering baseline form for patient %s", patient.sid)
    return render_template(
        "patient/checkin_baseline.html",
        patient=patient,
        alias_name=alias_name,
    )

# --------------------------------------------------------------------------
# Patient Dashboard
# --------------------------------------------------------------------------
@patient_bp.route("/dashboard", methods=["GET"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def patient_dashboard():

    # -----------------------------
    # Ensure current_user has SID
    # -----------------------------
    sid = getattr(current_user, "sid", None)
    if not sid:
        abort(403, "No patient SID associated with current user")

    # -----------------------------
    # Patient Profile
    # -----------------------------
    patient = PatientProfile.query.filter_by(user_sid=sid).first()
    if not patient:
        abort(404, "Patient profile not found")

    # -----------------------------
    # Alias + Avatar Initial
    # -----------------------------
    alias = getattr(current_user, "alias_name", None)
    avatar_initial = alias[0].upper() if alias and len(alias) > 0 else "?"

    # -----------------------------
    # Current Product Usage
    # -----------------------------
    current_products = CurrentPatientProductUsage.get_current_for_patient(sid)

    # -----------------------------
    # Latest QoL Data
    # -----------------------------
    last_score = getattr(patient, "last_qol_score", None)
    last_checkin_date = getattr(patient, "last_qol_date", None)
    is_onboarded = getattr(patient, "is_onboarded", False)

    # -----------------------------
    # Latest AI Recommendation
    # -----------------------------
    latest_recommendation = LatestAIRecommendation.query.filter_by(
        patient_sid=patient.sid
    ).first()

    # -----------------------------
    # Social Counts
    # -----------------------------
    try:
        unread_count = (
            db.session.query(func.count())
            .filter(
                MessageReceipt.user_id == current_user.id,
                MessageReceipt.is_read.is_(False),
            )
            .scalar()
            or 0
        )

        friends_count = (
            db.session.query(func.count())
            .filter(Friends.user_id == current_user.id)
            .scalar()
            or 0
        )

        group_count = (
            db.session.query(func.count())
            .filter(GroupMember.user_id == current_user.id)
            .scalar()
            or 0
        )
    except Exception:
        unread_count = friends_count = group_count = 0

    # -----------------------------
    # User / Profile Summary
    # -----------------------------
    user = current_user
    profile = patient
    viewer_is_friend = current_user.is_friend(user.id)

    favorite_dispensary = None
    if profile and getattr(profile, "dispensaries", None):
        favorite_dispensary = profile.dispensaries[0]  # first linked dispensary

    # -----------------------------
    # Public Profile Data
    # -----------------------------
    public_profile_data = {
        "display_name": user.display_name if user else "Anonymous",
        "avatar_initial": avatar_initial,  # ✅ fixed key (was malformed)
        "alias": user.alias_name if getattr(user, "alias_public_on", False) else None,
        "favorite_dispensary": (
            favorite_dispensary.name if favorite_dispensary else None
        ),
        "can_view_afflictions": user.can_be_seen_field(
            "afflictions", viewer_is_friend=viewer_is_friend
        )
        if user
        else False,
        "can_view_qol": user.can_be_seen_field(
            "qol_scores", viewer_is_friend=viewer_is_friend
        )
        if user
        else False,
        "can_view_voting": user.can_be_seen_field(
            "voting_history", viewer_is_friend=viewer_is_friend
        )
        if user
        else False,
        "quick_links": {"friends": True, "groups": True},
    }

    # -----------------------------
    # Render Dashboard
    # -----------------------------
    return render_template(
        "patient/patient_dashboard.html",
        patient=patient,
        current_products=current_products,
        last_score=last_score,
        last_checkin_date=last_checkin_date,
        is_onboarded=is_onboarded,
        latest_recommendation=latest_recommendation,
        public_profile_data=public_profile_data,
        avatar_initial=avatar_initial,
        alias_name=alias,
        unread_count=unread_count,
        friends_count=friends_count,
        group_count=group_count,
    )

    
@patient_bp.route("/stop_using/<int:usage_id>", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def stop_using_product(usage_id):
 
    usage = CurrentPatientProductUsage.query.get_or_404(usage_id)

    # Ownership check
    if usage.sid != current_user.sid:
        abort(403, "You do not have permission to modify this record.")

    # Date from form or default to now
    end_date_str = request.form.get("end_date")
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d") if end_date_str else datetime.utcnow()

    # 1️⃣ Remove from current usage
    db.session.delete(usage)

    # 2️⃣ Update the long-term PatientProductUsage record
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

    flash("Product marked as discontinued.", "success")
    return redirect(url_for("patient.patient_dashboard"))


# ---------- Route: Check-ins Hub ----------
@patient_bp.route("/checkins/hub", methods=["GET"], endpoint="checkins_hub")
@login_required
@role_required(UserRoleEnum.PATIENT)
def checkins_hub():
    profile: PatientProfile = current_user.patient_profile
    latest_checkin: WellnessCheck = profile.last_wellness_check
    current_usage: list = profile.current_products # List of PatientProductUsage

    # Serialize latest wellness check for front-end
    latest_levels = {}
    last_attributions = {}

    if latest_checkin:
        latest_levels = {
            "pain_level": latest_checkin.pain_level,
            "mood_level": latest_checkin.mood_level,
            "energy_level": latest_checkin.energy_level,
            "clarity_level": latest_checkin.clarity_level,
            "appetite_level": latest_checkin.appetite_level,
            "sleep_level": latest_checkin.sleep_level,
        }
        # Aggregate last attributions per metric
        for a in latest_checkin.attributions:
            for metric in ["pain", "mood", "energy", "clarity", "appetite", "sleep"]:
                pct = getattr(a, f"{metric}_pct", 0.0) or 0.0
                last_attributions[metric] = last_attributions.get(metric, 0.0) + pct

    # Prepare product usage JSON for last 12 usages
    last_products = []
    usage_json = []

    if current_usage:
        # Last 12 usages
        for p in current_usage[-12:]:
            last_products.append({
                "product_id": p.product_id,
                "dosage_mg": getattr(p, "dosage_mg", None),
                "times_per_day": getattr(p, "times_per_day", None),
                "product_name": getattr(p.product, "name", "Unknown") if p.product else "Unknown",
                "url": url_for("products.product_detail", product_id=p.product_id),
            })
        # Usage aggregate for chart
        usage_json = [
            {"day": u.created_at.date().isoformat(), "count": getattr(u, "times_per_day", 1)}
            for u in current_usage
        ]

    # AI / slider logic placeholder: computed on front-end
    sliders, recommended_products, ai_feedback = [], [], ""

    return render_template(
        "patient/checkins_hub.html",
        sliders=sliders,
        recommended_products=recommended_products,
        ai_feedback=ai_feedback,
        last_checkin_at=getattr(latest_checkin, "checkin_date", None),
        latest_qol=getattr(latest_checkin, "overall_qol", None),
        wellness_history_json=[wc.to_dict() for wc in profile.wellness_checks],  # Optional
        comparisons=profile.comparisons,  # Aggregate averages already in model
        usage_json=usage_json,
        afflictions=profile.afflictions_constants,  # constants only
        affliction_grades=profile.affliction_grades_constants,
        last_afflictions=profile.last_afflictions,
        last_products=last_products,
        last_attributions=last_attributions,
        last_row=latest_checkin,
        disable_checkins=(latest_checkin is None),
        last_levels=latest_levels,
    )


# ---------- Route: Product Check-in (POST) ----------
@patient_bp.route("/checkin/products", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def product_checkin():
    """
    Expects JSON payload:
    {
        "wellness_check_id": int,
        "products_changed": bool,
        "cannabis_pct": float,  # 0..100
        "products": [
            {"product_id": int, "allocation_pct": float}
        ]
    }
    """
    data = request.get_json() or {}
    wellness_check_id = data.get("wellness_check_id")
    products_changed = data.get("products_changed", False)
    cannabis_pct = data.get("cannabis_pct", 0)
    products = data.get("products", [])

    # --- Validate wellness check belongs to current patient ---
    wellness_check: WellnessCheck = db.session.get(WellnessCheck, wellness_check_id)
    if not wellness_check or wellness_check.sid != current_user.sid:
        return jsonify({"error": "Invalid wellness check"}), 400

    # --- Validate allocations ---
    if products_changed and products:
        total_alloc_pct = sum(p.get("allocation_pct", 0) for p in products)
        if not 99.9 <= total_alloc_pct <= 100.1:
            return jsonify({"error": "Product allocations must total 100%"}), 400

    # --- Compute cannabis contribution from front-end QoL delta ---
    total_qol_delta = getattr(wellness_check, "overall_qol_delta", None)
    if total_qol_delta is None:
        return jsonify({"error": "Wellness check missing QoL delta"}), 400

    cannabis_contribution = total_qol_delta * (cannabis_pct / 100)

    # --- Clear existing attributions ---
    WellnessAttribution.query.filter_by(wellness_check_id=wellness_check.id).delete()

    # --- Insert new attributions ---
    if products_changed and products:
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
    return jsonify({"attributions": result}), 200

# ---------- Route: Submit Wellness Check + Product Usage ----------
@patient_bp.route("/checkins/hub/submit", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def submit_wellness_check():
    """
    Expects JSON payload:
    {
        "checkin_id": int (optional, if updating existing check-in),
        "sliders": {
            "pain_level": int,
            "mood_level": int,
            "energy_level": int,
            "clarity_level": int,
            "appetite_level": int,
            "sleep_level": int
        },
        "products_changed": bool,
        "cannabis_pct": float,  # 0..100
        "products": [
            {"product_id": int, "allocation_pct": float}
        ]
    }
    """

    data = request.get_json() or {}
    checkin_id = data.get("checkin_id")
    sliders = data.get("sliders", {})
    products_changed = data.get("products_changed", False)
    cannabis_pct = data.get("cannabis_pct", 0)
    products = data.get("products", [])

    profile: PatientProfile = current_user.patient_profile

    # --- Create or update WellnessCheck ---
    if checkin_id:
        checkin: WellnessCheck = db.session.get(WellnessCheck, checkin_id)
        if not checkin or checkin.sid != current_user.sid:
            return jsonify({"error": "Invalid wellness check"}), 400
    else:
        checkin = WellnessCheck(sid=current_user.sid)
        db.session.add(checkin)

    # --- Update slider values ---
    for field in ["pain_level", "mood_level", "energy_level", "clarity_level", "appetite_level", "sleep_level"]:
        if field in sliders:
            setattr(checkin, field, sliders[field])

    # --- Compute current overall QoL and pct change ---
    last_checkin: WellnessCheck = profile.last_wellness_check
    checkin.overall_qol = sum(sliders.values()) / len(sliders)
    if last_checkin:
        checkin.pct_change_qol = checkin.overall_qol - getattr(last_checkin, "overall_qol", 0.0)
    else:
        checkin.pct_change_qol = 0.0

    # --- Save checkin so that id exists for attributions ---
    db.session.flush()

    # --- Handle product attributions ---
    WellnessAttribution.query.filter_by(wellness_check_id=checkin.id).delete()

    total_qol_delta = getattr(checkin, "overall_qol_delta", checkin.pct_change_qol)  # fallback
    cannabis_contribution = total_qol_delta * (cannabis_pct / 100)

    if products_changed and products:
        total_alloc_pct = sum(p.get("allocation_pct", 0) for p in products)
        if not 99.9 <= total_alloc_pct <= 100.1:
            return jsonify({"error": "Product allocations must total 100%"}), 400

        for p in products:
            attribution = WellnessAttribution(
                wellness_check_id=checkin.id,
                product_id=p.get("product_id"),
                overall_pct=cannabis_contribution * (p.get("allocation_pct", 0) / 100)
            )
            db.session.add(attribution)

    db.session.commit()

    return jsonify({
        "success": True,
        "checkin_id": checkin.id,
        "overall_qol": checkin.overall_qol,
        "pct_change_qol": checkin.pct_change_qol,
        "cannabis_qol": cannabis_contribution
    }), 200

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
        return redirect(url_for("patient.patient_dashboard"))

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
        return request.values.get("next") or _safe("patient.")

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
        ("patient.checkins_hub" if "patient.checkins_hub" in current_app.view_functions else "patient.")
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
        return redirect(url_for("patient."))

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
    return redirect(url_for("patient.patientdashboard"))


# =============================
# Patient Record Tabs
# =============================
# ------------------
# Root tabbed page
# ------------------
@patient_bp.route("/patient_record", methods=["GET"], endpoint="patient_record")
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
# UNIFIED SUPPORT GROUP MODEL HELPERS (safe from circular imports)
# =============================================================================
def get_support_models():
    """
    Return both core models for support groups.
    Prevents circular import errors by importing inside the function.
    """
    from app.models import SupportGroup, GroupMember
    return SupportGroup, GroupMember


def get_support_post_model():
    """
    Return the model used for group bulletin posts.
    """
    from app.models import SupportGroupPost
    return SupportGroupPost


def get_support_link_model():
    """
    Return the model used for group resource links, if applicable.
    If not defined in your schema, returns None safely.
    """
    try:
        from app.models import GroupLink
        return GroupLink
    except ImportError:
        return None


# =============================================================================
# GENERIC UTILITY HELPERS (afflictions, membership, etc.)
# =============================================================================
def get_afflictions_master():
    """Return master list of afflictions."""
    try:
        from app.constants import AFFLICTIONS
        return [str(x).strip() for x in (AFFLICTIONS or []) if str(x).strip()]
    except Exception:
        return []


def aff_key(name: str) -> str:
    """Slugify an affliction name: 'Parkinson's Disease' -> 'parkinsons-disease'"""
    import re
    s = (name or "").lower()
    s = re.sub(r"[?'`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "group"


def aff_name_from_key(key: str) -> str:
    """Resolve affliction slug back to its display name."""
    key = (key or "").strip().lower()
    for a in get_afflictions_master():
        if aff_key(a) == key or a.lower() == key:
            return a
    return key or "Group"


def ensure_group_record(name: str, key: str):
    """
    Ensure a SupportGroup record exists for a given name/key.
    If not, create it. Safe for numeric or slug keys.
    """
    SupportGroup, _ = get_support_models()
    from datetime import datetime as _dt
    from app import db

    try:
        q = db.session.query(SupportGroup)
        row = None
        if hasattr(SupportGroup, "slug"):
            row = q.filter(getattr(SupportGroup, "slug") == key).first()
        if not row and hasattr(SupportGroup, "name"):
            row = q.filter(getattr(SupportGroup, "name") == name).first()

        if not row:
            row = SupportGroup(name=name)
            if hasattr(row, "slug"):
                row.slug = key
            for t in ("created_at", "timestamp"):
                if hasattr(row, t):
                    setattr(row, t, _dt.utcnow())
            db.session.add(row)
            db.session.commit()
        return row
    except Exception:
        db.session.rollback()
        return None


def is_member(sid, key, name):
    """Check if a user SID is a member of a given group."""
    _, GroupMember = get_support_models()
    from app import db

    if not GroupMember or not sid:
        return False

    try:
        q = db.session.query(GroupMember)
        cond = []
        if hasattr(GroupMember, "group_key"):
            cond.append(getattr(GroupMember, "group_key") == key)
        elif hasattr(GroupMember, "group_name"):
            cond.append(getattr(GroupMember, "group_name") == name)
        else:
            group = ensure_group_record(name, key)
            if group and hasattr(GroupMember, "group_id") and hasattr(group, "id"):
                cond.append(getattr(GroupMember, "group_id") == getattr(group, "id"))

        for u in ("sid", "user_sid", "patient_sid"):
            if hasattr(GroupMember, u):
                cond.append(getattr(GroupMember, u) == sid)

        return bool(q.filter(*cond).first()) if cond else False
    except Exception:
        return False


def member_count(key, name):
    """Return number of members in a given group."""
    _, GroupMember = get_support_models()
    from app import db

    if not GroupMember:
        return 0

    try:
        q = db.session.query(GroupMember)
        if hasattr(GroupMember, "group_key"):
            return q.filter(getattr(GroupMember, "group_key") == key).count()
        if hasattr(GroupMember, "group_name"):
            return q.filter(getattr(GroupMember, "group_name") == name).count()
        group = ensure_group_record(name, key)
        if group and hasattr(GroupMember, "group_id") and hasattr(group, "id"):
            return (
                db.session.query(GroupMember)
                .filter(getattr(GroupMember, "group_id") == getattr(group, "id"))
                .count()
            )
    except Exception:
        pass
    return 0

# -------------------- GROUPS LIST / INDEX --------------------
@patient_bp.route("/groups", methods=["GET"], endpoint="groups_index")
@login_required
@role_required(UserRoleEnum.PATIENT)
def groups_index():
    """Display a list of all support groups the patient can join."""
    try:
        G = _GroupModel() if "_GroupModel" in globals() else None
        groups = []
        if G:
            groups = db.session.query(G).order_by(
                getattr(G, "name", getattr(G, "group_name", None))
            ).limit(100).all()
        else:
            # Fallback: static default groups
            groups = [
                {"group_key": "anxiety", "name": "Anxiety Support"},
                {"group_key": "pain", "name": "Chronic Pain"},
                {"group_key": "sleep", "name": "Sleep Wellness"},
            ]
    except Exception:
        current_app.logger.exception("groups_index failed")
        groups = []
    return render_template("patient/groups_index.html", groups=groups)
    

# -------------------- DETAIL (bulletin + resources) --------------------
@patient_bp.route("/groups/<group_key>", methods=["GET"], endpoint="groups")
@login_required
@role_required(UserRoleEnum.PATIENT)
def groups (group_key):
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



# --------------------
# Utility functions
# --------------------
def _user_sid():
    """Return the current user sid."""
    return getattr(current_user, "sid", None) or getattr(current_user, "id", None)


def _aff_key(name: str) -> str:
    """Convert string to slug key: 'Parkinson's Disease' -> 'parkinsons-disease'"""
    s = (name or "").lower()
    s = re.sub(r"[?'`]", "", s)  # drop apostrophes
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "group"


def _aff_name_from_key(key: str) -> str:
    """Return canonical affliction/group name from a key."""
    key = (key or "").strip().lower()
    master = getattr(current_app.config, "AFFLICTIONS", []) or []
    for a in master:
        if _aff_key(a) == key or a.lower() == key:
            return a
    return key or "Group"


# --------------------
# PUBLIC PROFILE
# --------------------
@patient_bp.route("/public_profile/<int:user_id>")
@login_required
def public_profile(user_id):
    """Return public profile page filtered by user privacy settings."""
    user = User.query.get(user_id)
    profile = PatientProfile.query.filter_by(user_id=user_id).first()

    if not user or not profile:
        abort(404)

    # Determine viewer relationship
    viewer_is_owner = current_user.id == user_id
    viewer_is_friend = current_user.is_friend(user_id)

    # Display name respects preferred display + privacy
    display_name = user.display_name if viewer_is_owner or viewer_is_friend or user.is_discoverable_by_real_name() else None
    alias_name = user.alias_name if viewer_is_owner or user.is_discoverable_by_alias() else None

    # Build profile bundle using security helpers
    bundle = {
        "display_name": display_name,
        "alias": alias_name,
        "afflictions": [a.name for a in profile.afflictions] if profile.can_view_afflictions(viewer_is_owner, viewer_is_friend) else [],
        "favorite_dispensary": profile.favorite_dispensary.name if profile.show_favorite_dispensary(viewer_is_owner, viewer_is_friend) else None,
        "qol_scores": profile.qol_scores if profile.show_qol(viewer_is_owner, viewer_is_friend) else [],
        "voting_history": profile.voting_history if profile.show_voting(viewer_is_owner, viewer_is_friend) else [],
        "favorites": [f.name for f in profile.favorites] if profile.show_favorites(viewer_is_owner, viewer_is_friend) else [],
        "recommendations": profile.recommendations if profile.show_recommendations(viewer_is_owner, viewer_is_friend) else [],
        "afflictions_over_time": profile.afflictions_over_time if profile.show_afflictions_over_time(viewer_is_owner, viewer_is_friend) else [],
        "_viewer_is_owner": viewer_is_owner,
        "_viewer_is_friend": viewer_is_friend,
    }

    return render_template("patient/public_profile.html", bundle=bundle)


# --------------------
# FRIENDS PREVIEW / FULL PAGE
# --------------------
@patient_bp.get("/friends/preview", endpoint="friends_preview")
@login_required
@role_required(UserRoleEnum.PATIENT)
def friends_preview():
    """Top 3 friends preview JSON."""
    try:
        from app.models import Friends

        friends = (
            db.session.query(User)
            .join(Friends, Friends.friend_id == User.id)
            .filter(Friends.user_id == current_user.id)
            .order_by(User.id.desc())
            .limit(3)
            .all()
        )

        rows = [
            {
                "id": u.id,
                "name": u.display_name or u.full_name or f"User {u.id}",
                "status": getattr(u, "status", ""),
            }
            for u in friends
        ]
        return jsonify({"top": rows})
    except Exception:
        current_app.logger.exception("friends_preview failed")
        return jsonify({"top": []})


@patient_bp.get("/friends", endpoint="friends")
@login_required
@role_required(UserRoleEnum.PATIENT)
def friends_page():
    """Render full friends page."""
    try:
        from app.models import Friends

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
            Friends.friend_id == target_id,
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
            Friends.friend_id == target_id,
        ).delete()
        db.session.commit()
        flash("Friend removed.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("friends_remove failed")
        flash("Could not remove friend.", "danger")

    return redirect(url_for("patient.friends"))





