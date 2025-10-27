"""
Enterprise user routes.

This blueprint handles enterprise dashboards, onboarding flows, inventory
management, product submissions, voting on suppliers/providers/dispensaries,
and public profile pages. The code is based on the user's original
``enterprise.py``, adapted into a blueprint under ``app/routes`` and with
cleaned imports and helper functions. Some functionality such as voting
utilities may need additional modules (e.g. :mod:`app.utils.voting_logic`).
"""

import os
from datetime import datetime

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    current_app,
    abort,
)

from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, desc, or_, text
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    Provider,
    SupplierProfile,
    Dispensary,
    Product,
    ProductTerpene,
    ProductSubmission,
    ModerationReport,
    FavoriteEnterprise,
    InventoryReport,
    Upvote,
)

from app.utils.uploads import save_dev_static
from app.utils.decorators import role_required
from app.constants.afflictions import AFFLICTION_LIST, AFFLICTION_LEVELS, get_afflictions, get_levels, normalize_afflictions, serialize_afflictions, parse_afflictions, is_valid_level
from app.constants.terpenes import TERPENES, COMMON_TERPENES, get_terpenes, get_common_terpenes
from app.constants.application_methods import APPLICATION_METHODS, APPLICATION_METHOD_CHOICES
from app.constants.enums import UserRoleEnum    


enterprise_bp = Blueprint("enterprise", __name__, url_prefix="/enterprise")

# Allowed file extensions for logos and product images
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename: str) -> bool:
    """Return True if the filename has an allowed extension."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def enterprise_required(view_func):
    """Decorator that ensures current user is an enterprise."""

    @login_required
    def wrapped_view(*args, **kwargs):
        if current_user.role != UserRoleEnum.ENTERPRISE:
            flash("Access denied.", "error")
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)

    wrapped_view.__name__ = view_func.__name__
    return wrapped_view


@enterprise_bp.route("/dashboard", methods=["GET"], endpoint="enterprise_dashboard")
@login_required
def enterprise_dashboard():
    """Render the enterprise dashboard with inventory and other metrics."""
    if current_user.role != UserRoleEnum.ENTERPRISE:
        flash("Enterprise access required.", "danger")
        return redirect(url_for("auth.login"))

    # Get all products owned by this enterprise
    inventory = Product.query.filter_by(owner_id=current_user.id).all()

    # The following variables (watching, top_affliction, inventory_snapshot, promotions,
    # qr_codes, traffic) are placeholders for more advanced analytics. Currently they
    # default to empty or None, but can be populated by additional utility functions.
    watching = []
    top_affliction = None
    inventory_snapshot = None
    promotions = []
    qr_codes = []
    traffic = []

    return render_template(
        "enterprise/enterprise_dashboard.html",
        inventory=inventory,
        watching=watching,
        top_affliction=top_affliction,
        inventory_snapshot=inventory_snapshot,
        promotions=promotions,
        qr_codes=qr_codes,
        traffic=traffic,
    )


def get_top_products_per_affliction_for_enterprise(enterprise_id: int, limit: int = 3):
    """Placeholder for retrieving top products per affliction for an enterprise."""
    return {
        "Pain Management": Product.query.filter_by(owner_id=enterprise_id)
        .limit(limit)
        .all(),
        "Anxiety": Product.query.filter_by(owner_id=enterprise_id).limit(limit).all(),
    }


@enterprise_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
@role_required(UserRoleEnum.ENTERPRISE)
def onboarding():
    if request.method == "GET":
        return render_template("enterprise/onboarding.html")

    role_type = (request.form.get("role_type") or "").strip().lower()
    company_name = (request.form.get("company_name") or "").strip()
    contact_email = (request.form.get("contact_email") or "").strip()
    website = (request.form.get("website") or "").strip()
    logo_file = request.files.get("logo")

    if role_type not in {"dispensary", "provider", "supplier", "research"}:
        flash("Invalid role type selected.", "danger")
        return redirect(url_for("enterprise.onboarding"))

    # 1) Create the correct entity
    entity = None
    if role_type == "dispensary":
        entity = Dispensary(
            user_id=current_user.id,
            name=company_name,
            contact_email=contact_email,
            website=website,
            address=request.form.get("address"),
            contact_phone=request.form.get("phone"),
        )
    elif role_type == "supplier":
        entity = SupplierProfile(
            user_id=current_user.id,
            company_name=company_name,
            contact_email=contact_email,
            website=website,
            product_categories=request.form.get("product_categories"),
        )
    else:  # provider or research -> Provider model
        entity = Provider(
            user_id=current_user.id,
            name=company_name,
            email=contact_email,
            clinic_name=request.form.get("clinic_name"),
        )
        entity.education = request.form.get("education")
        entity.years_experience = request.form.get("years_experience")

    db.session.add(entity)
    db.session.flush()  # ensure entity.id exists for FK

    # 2) Save logo and link via UploadedFile FK (store relative path under /static)
    if logo_file and logo_file.filename:
        try:
            # store under app/static/output/<filename>  (dev/test path)
            uf = save_dev_static(logo_file, subdir="output", uploaded_by_id=current_user.id)
            # set FK on the entity created above
            if hasattr(entity, "logo_file_id"):
                entity.logo_file_id = uf.id
        except ValueError as ve:
            db.session.rollback()
            flash(str(ve), "danger")
            return redirect(url_for("enterprise.onboarding"))

    # 3) Finalize onboarding
    current_user.has_completed_onboarding = True
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Database error while saving enterprise profile.", "danger")
        return redirect(url_for("enterprise.onboarding"))

    flash("Onboarding complete. Your public profile has been created.", "success")
    return redirect(url_for("enterprise.enterprise_dashboard"))


@enterprise_bp.route("/inventory", methods=["GET", "POST"])
@enterprise_required
def manage_inventory():
    """Allow an enterprise to report current inventory levels."""
    all_products = Product.query.filter_by(approval_status="approved").all()
    previous_week = None  # Can be implemented later

    if request.method == "POST":
        quantities = request.form.getlist("quantities")
        product_ids = request.form.getlist("product_ids")
        for pid, qty in zip(product_ids, quantities):
            db.session.add(
                InventoryReport(
                    enterprise_id=current_user.id,
                    product_id=pid,
                    quantity=int(qty),
                    date_reported=datetime.utcnow().date(),
                )
            )
        db.session.commit()
        flash("Inventory submitted.", "success")
        return redirect(url_for("enterprise.manage_inventory"))

    return render_template(
        "enterprise/inventory.html",
        all_products=all_products,
        previous_week=previous_week,
    )


@enterprise_bp.route("/product/submit", methods=["GET", "POST"])
@role_required(UserRoleEnum.ENTERPRISE)
def submit_product():
    """Submit a new product for admin approval."""
    if request.method != "POST":
        return render_template(
            "enterprise/product_form.html",
            product=None,
            APPLICATION_METHODS=APPLICATION_METHODS,
            AFFLICTION_LIST=AFFLICTION_LIST,
        )

    # -------- gather form --------
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    application_method = request.form.get("application_method") or None
    suggested_treatment = request.form.get("suggested_treatment") or None
    retail_price = request.form.get("retail_price") or None
    manufacturer_claim = request.form.get("manufacturer_claim") or None

    chem_type = (
        (request.form.get("chem_type") or "n/a").strip().lower()
    )  # 'indica' | 'sativa' | 'hybrid' | 'n/a'

    def to_float(val):
        try:
            return (
                float(val)
                if val
                not in (
                    None,
                    "",
                )
                else None
            )
        except ValueError:
            return None

    thc_percent = to_float(request.form.get("thc_percent"))
    cbd_percent = to_float(request.form.get("cbd_percent"))
    manufacturer_description = (
        request.form.get("manufacturer_description") or ""
    ).strip() or None

    if not name:
        flash("Product name is required.", "danger")
        return redirect(url_for("enterprise.submit_product"))

    # -------- image upload --------
    image_path = None
    image_file = request.files.get("image")
    if image_file and image_file.filename:
        if not allowed_file(image_file.filename):
            flash("Invalid image file type.", "danger")
            return redirect(request.url)
        filename = secure_filename(image_file.filename)
        upload_folder = os.path.join(
            current_app.root_path, "static", "uploads", "products"
        )
        os.makedirs(upload_folder, exist_ok=True)
        filepath = os.path.join(upload_folder, filename)
        image_file.save(filepath)
        image_path = f"uploads/products/{filename}"

    # -------- create product --------
    product = Product(
        owner_id=current_user.id,
        name=name,
        description=description,
        application_method=application_method,
        suggested_treatment=suggested_treatment,
        retail_price=retail_price or None,
        image_path=image_path,
        approval_status="pending",
        is_public=False,
        # keep whichever naming your Product model actually has:
        chem_type=chem_type if hasattr(Product, "chem_type") else None,
        thc_percent=thc_percent if hasattr(Product, "thc_percent") else None,
        cbd_percent=cbd_percent if hasattr(Product, "cbd_percent") else None,
        manufacturer_description=(
            manufacturer_description
            if hasattr(Product, "manufacturer_description")
            else None
        ),
        manufacturer_claim=manufacturer_claim,
    )
    db.session.add(product)
    db.session.flush()  # get product.id without committing yet

    # -------- terpenes --------
    pairs, err = parse_terpene_form(request.form, top_n=10)
    if err:
        db.session.rollback()
        flash(err, "danger")
        return redirect(request.url)

    if hasattr(product, "terpenes"):  # relationship to ProductTerpene
        # start clean (if any default)
        product.terpenes.clear()
        for name, pct in pairs:
            product.terpenes.append(ProductTerpene(name=name, percent=pct))

    # -------- finalize --------
    db.session.commit()
    flash("Product submitted and awaiting approval.", "success")
    return redirect(url_for("enterprise.enterprise_dashboard"))


@enterprise_bp.route("/product/<int:product_id>/edit", methods=["GET", "POST"])
@role_required(UserRoleEnum.ENTERPRISE)
def edit_product(product_id):
    """Allow an enterprise user to edit their own product submissions."""
    from app.constants import APPLICATION_METHODS, AFFLICTION_LIST

    product = Product.query.get_or_404(product_id)
    if product.owner_id != current_user.id:
        flash("Unauthorized access to edit product.", "danger")
        return redirect(url_for("enterprise.enterprise_dashboard"))

    if request.method == "POST":
        product.name = request.form.get("name")
        product.description = request.form.get("description")
        product.application_method = request.form.get("application_method")
        product.suggested_treatment = request.form.get("suggested_treatment")
        product.retail_price = request.form.get("retail_price") or None
        product.thc_content = request.form.get("thc_content") or None
        product.cbd_content = request.form.get("cbd_content") or None
        product.manufacturer_claim = request.form.get("manufacturer_claim")

        image_file = request.files.get("image")
        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            upload_folder = os.path.join(
                current_app.root_path, "static/uploads/products"
            )
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            image_file.save(filepath)
            product.image_path = f"uploads/products/{filename}"
        elif image_file and image_file.filename != "":
            flash("Invalid image file type.", "danger")
            return redirect(request.url)

        db.session.commit()
        flash("Product updated.", "success")
        return redirect(url_for("enterprise.enterprise_dashboard"))

    return render_template(
        "enterprise/product_form.html",
        product=product,
        APPLICATION_METHODS=APPLICATION_METHODS,
        AFFLICTION_LIST=AFFLICTION_LIST,
    )


@enterprise_bp.route("/report", methods=["GET", "POST"])
@enterprise_required
def report_behavior():
    """Allow an enterprise user to report behavior for moderation."""
    if request.method == "POST":
        db.session.add(
            ModerationReport(
                reporter_id=current_user.id,
                reporter_role=UserRoleEnum.ENTERPRISE,
                target_type=request.form.get("target_type"),
                target_id=request.form.get("target_id"),
                reason=request.form.get("reason"),
                details=request.form.get("details"),
            )
        )
        db.session.commit()
        flash("Report submitted", "success")
        return redirect(url_for("enterprise.enterprise_dashboard"))

    return render_template("enterprise/report_behavior.html")


@enterprise_bp.route("/support")
@enterprise_required
def support():
    """Placeholder support page for enterprise users."""
    return render_template("enterprise/support_placeholder.html")


@enterprise_bp.route("/marketing")
@enterprise_required
def marketing():
    """Placeholder marketing page for enterprise users."""
    return render_template("enterprise/marketing_placeholder.html")


@enterprise_bp.route("/top-products")
@role_required(UserRoleEnum.ENTERPRISE)
def top_products():
    """Return top 10 products by average quality-of-life score."""
    results = (
        db.session.query(
            Product.id,
            Product.name,
            func.avg(Upvote.qol_improvement).label("avg_qol"),
        )
        .join(
            Upvote,
            (Upvote.target_id == Product.id) & (Upvote.target_type == "product"),
        )
        .group_by(Product.id, Product.name)
        .order_by(desc("avg_qol"))
        .limit(10)
        .all()
    )

    return jsonify(
        [
            {
                "product_id": r.id,
                "product_name": r.name,
                "average_qol": round(r.avg_qol, 2) if r.avg_qol is not None else None,
            }
            for r in results
        ]
    )


@enterprise_bp.route("/vote/<string:entity_type>/<int:entity_id>/status", methods=["GET"])
@role_required(UserRoleEnum.ENTERPRISE)
def check_vote_status(entity_type: str, entity_id: int):
    """
    Return vote status for an entity.

    - For products: includes average QoL and total votes.
    - For enterprises (provider/supplier/dispensary): returns upvote count only (no QoL).
    """
    valid_types = {"product", "provider", "supplier", "dispensary"}
    if entity_type not in valid_types:
        return jsonify({"error": "Invalid entity type"}), 400

    # Total upvotes (applies to all types)
    total_upvotes = (
        db.session.query(func.count(Upvote.id))
        .filter(Upvote.target_type == entity_type, Upvote.target_id == entity_id)
        .scalar()
    )

    if entity_type == "product":
        # Average QoL only for products
        avg_qol = (
            db.session.query(func.avg(Upvote.qol_improvement))
            .filter(
                Upvote.target_type == "product",
                Upvote.target_id == entity_id,
                Upvote.qol_improvement.isnot(None),
            )
            .scalar()
        )
        return jsonify(
            {
                "has_votes": total_upvotes > 0,
                "average_qol": round(avg_qol, 2) if avg_qol is not None else None,
                "total_votes": total_upvotes,
            }
        ), 200

    # Enterprises: no QoL, just count
    return jsonify(
        {
            "has_votes": total_upvotes > 0,
            "total_votes": total_upvotes,
            "average_qol": None,  # explicit: enterprises don't have QoL scores
        }
    ), 200

@enterprise_bp.route("/profile")
@enterprise_required
def profile():
    """Render the enterprise user's profile including provider/supplier/dispensary info."""
    return render_template(
        "enterprise/profile.html",
        user=current_user,
        provider=Provider.query.filter_by(user_id=current_user.id).first(),
        supplier=SupplierProfile.query.filter_by(user_id=current_user.id).first(),
        dispensary=Dispensary.query.filter_by(user_id=current_user.id).first(),
    )


@enterprise_bp.route("/settings")
@enterprise_required
def settings():
    """Placeholder settings page for enterprise users."""
    return render_template("enterprise/settings_placeholder.html")


@enterprise_bp.route("/submissions")
@enterprise_required
def submission_history():
    """List product submissions and reports from the current enterprise user."""
    products = (
        Product.query.filter_by(owner_id=current_user.id)
        .order_by(Product.created_at.desc())
        .all()
    )
    submissions = (
        ProductSubmission.query.filter_by(submitted_by_id=current_user.id)
        .order_by(ProductSubmission.last_checkin_at.desc())
        .all()
    )
    reports = (
        ModerationReport.query.filter_by(reporter_id=current_user.id)
        .order_by(ModerationReport.created_at.desc())
        .all()
    )
    return render_template(
        "enterprise/submissions.html",
        products=products,
        submissions=submissions,
        reports=reports,
    )

@enterprise_bp.route("/product/<int:product_id>")
def product_detail(product_id: int):
    """Public product detail page for enterprise section."""
    product = Product.query.get_or_404(product_id)
    # Import helper from scoring
    from app.utils.scoring import get_average_qol_score

    avg_qol = get_average_qol_score(product.id)
    return render_template(
        "enterprise/product_detail.html", product=product, avg_qol=avg_qol
    )

# -------- Helpers --------
def _is_following(enterprise_user_id: int, user_id: int) -> bool:
    return db.session.query(FavoriteEnterprise.id).filter_by(
        enterprise_id=enterprise_user_id, user_id=user_id
    ).first() is not None

def _followers_count(enterprise_user_id: int) -> int:
    return FavoriteEnterprise.query.filter_by(enterprise_id=enterprise_user_id).count()

# -------- Follow / Unfollow --------
@enterprise_bp.route("/follow/<int:enterprise_user_id>", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def follow_enterprise(enterprise_user_id: int):
    """Patient follows an enterprise (enterprise_user_id = User.id of enterprise)."""
    # Do not allow following self (edge-case if roles overlap)
    if current_user.id == enterprise_user_id:
        return jsonify({"error": "You cannot follow yourself."}), 400

    # Ensure the target is an enterprise user
    enterprise_user = User.query.get_or_404(enterprise_user_id)
    try:
        ent_role = enterprise_user.role
        if isinstance(ent_role, str):
            ent_role = UserRoleEnum(ent_role)
    except Exception:
        return jsonify({"error": "Invalid target user role."}), 400

    if ent_role != UserRoleEnum.ENTERPRISE:
        return jsonify({"error": "Target user is not an enterprise."}), 400

    if _is_following(enterprise_user_id, current_user.id):
        # Already following; idempotent
        return jsonify({"message": "Already following"}), 200

    fav = FavoriteEnterprise(user_id=current_user.id, enterprise_id=enterprise_user_id)
    db.session.add(fav)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Could not follow at this time."}), 500

    return jsonify({"message": "Following", "followers": _followers_count(enterprise_user_id)}), 200


@enterprise_bp.route("/unfollow/<int:enterprise_user_id>", methods=["POST", "DELETE"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def unfollow_enterprise(enterprise_user_id: int):
    """Patient unfollows an enterprise."""
    fav = FavoriteEnterprise.query.filter_by(
        enterprise_id=enterprise_user_id, user_id=current_user.id
    ).first()
    if not fav:
        return jsonify({"message": "Not following"}), 200

    db.session.delete(fav)
    db.session.commit()
    return jsonify({"message": "Unfollowed", "followers": _followers_count(enterprise_user_id)}), 200


# app/routes/enterprise.py  (place near the public routes)
def get_vote_counts_only(target_type: str, target_id: int) -> dict:
    """Return simple totals for Upvote-only schema."""
    total = (
        db.session.query(Upvote.id)
        .filter(Upvote.target_type == target_type, Upvote.target_id == target_id)
        .count()
    )
    return {"total": total}


# app/routes/enterprise.py

@enterprise_bp.route("/supplier/<int:supplier_id>")
def public_supplier_profile(supplier_id: int):
    supplier = SupplierProfile.query.get_or_404(supplier_id)
    enterprise_user_id = supplier.user_id
    is_following = current_user.is_authenticated and _is_following(enterprise_user_id, current_user.id)
    followers = _followers_count(enterprise_user_id)
    return render_template(
        "enterprise/supplier_public.html",
        supplier=supplier,
        enterprise_user_id=enterprise_user_id,
        is_following=is_following,
        followers=followers,
    )

@enterprise_bp.route("/provider/<int:provider_id>")
def public_provider_profile(provider_id: int):
    provider = Provider.query.get_or_404(provider_id)
    enterprise_user_id = provider.user_id
    is_following = current_user.is_authenticated and _is_following(enterprise_user_id, current_user.id)
    followers = _followers_count(enterprise_user_id)
    return render_template(
        "enterprise/provider_public.html",
        provider=provider,
        enterprise_user_id=enterprise_user_id,
        is_following=is_following,
        followers=followers,
    )

@enterprise_bp.route("/dispensary/<int:dispensary_id>")
def public_dispensary_profile(dispensary_id: int):
    dispensary = Dispensary.query.get_or_404(dispensary_id)
    enterprise_user_id = dispensary.user_id
    is_following = current_user.is_authenticated and _is_following(enterprise_user_id, current_user.id)
    followers = _followers_count(enterprise_user_id)
    return render_template(
        "enterprise/dispensary_public.html",
        dispensary=dispensary,
        enterprise_user_id=enterprise_user_id,
        is_following=is_following,
        followers=followers,
    )


@enterprise_bp.route("/vote/<string:target_type>/<int:target_id>", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def enterprise_vote(target_type: str, target_id: int):
    """
    Allow patients to upvote enterprises: supplier, provider, dispensary.
    Target type must be one of the allowed enterprise types.
    """

    valid_targets = {"supplier", "provider", "dispensary"}
    if target_type not in valid_targets:
        abort(400, description=f"Invalid target_type '{target_type}'.")

    # Check if already upvoted by this user
    existing = Upvote.query.filter_by(
        user_id=current_user.id,
        target_type=target_type,
        target_id=target_id
    ).first()

    if existing:
        return jsonify({"message": "Already upvoted"}), 200

    # Create new upvote
    new_upvote = Upvote(
        user_id=current_user.id,
        target_type=target_type,
        target_id=target_id,
        qol_improvement=None  # Only products store QoL
    )
    db.session.add(new_upvote)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(500, description="Database error while saving upvote.")

    return jsonify({
        "message": "Upvote recorded",
        "target_type": target_type,
        "target_id": target_id
    }), 201


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _fanout_message_receipts(msg, recipient_ids):
    """
    Create MessageReceipt rows for recipient_ids (skip sender if present).
    Uses function-level import to avoid circular import at module import time.
    """
    try:
        from app.models import MessageReceipt
    except Exception:
        # if model import fails, propagate to caller
        raise
    for uid in recipient_ids:
        if uid == getattr(msg, "sender_id", None):
            continue
        db.session.add(MessageReceipt(message_id=msg.id, user_id=uid))


# ------------------------------------------------------------------
# Previews & listing (enterprise-facing)
# ------------------------------------------------------------------
@enterprise_bp.get("/comm/preview", endpoint="comm_preview")
@login_required
@role_required(UserRoleEnum.ENTERPRISE)
def comm_preview():
    """
    Return JSON preview used by the communications card for enterprise users.
    Shows recent conversations created by this enterprise (broadcasts and others).
    """
    try:
        from app.models import Conversation, Message

        q = (
            db.session.query(Conversation)
            .filter(Conversation.created_by == current_user.id)
            .order_by(Conversation.created_at.desc())
            .limit(8)
        )

        rows = []
        for conv in q.all():
            # Attempt to derive a "when" from the most recent message or conversation created_at
            last_msg = (
                db.session.query(Message)
                .filter(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc())
                .limit(1)
                .first()
            )
            when = (
                (last_msg.created_at.strftime("%b %d, %Y %I:%M %p") if last_msg and getattr(last_msg, "created_at", None) else None)
                or (getattr(conv, "created_at", None) and conv.created_at.strftime("%b %d, %Y %I:%M %p"))
                or ""
            )
            rows.append({
                "id": conv.id,
                "title": conv.title or ("Broadcast" if conv.is_broadcast else ("Group" if conv.is_group else "Conversation")),
                "is_broadcast": bool(conv.is_broadcast),
                "is_group": bool(conv.is_group),
                "when": when,
                "href": url_for("enterprise.view_conversation", conversation_id=conv.id) if has_endpoint("enterprise.view_conversation") else ""
            })

        return jsonify({"top": rows})
    except Exception:
        current_app.logger.exception("[enterprise.comm_preview] failed")
        return jsonify({"top": []})


@enterprise_bp.get("/comm", endpoint="communications")
@login_required
@role_required(UserRoleEnum.ENTERPRISE)
def communications():
    """
    Full communications page for the enterprise: list of conversations created by this enterprise.
    """
    try:
        from app.models import Conversation

        convs = (
            db.session.query(Conversation)
            .filter(Conversation.created_by == current_user.id)
            .order_by(Conversation.created_at.desc())
            .limit(200)
            .all()
        )
    except Exception:
        current_app.logger.exception("[enterprise.communications] load failed")
        convs = []

    return render_template("enterprise/comm_full.html", conversations=convs)


@enterprise_bp.get("/comm/<int:conversation_id>", endpoint="view_conversation")
@login_required
@role_required(UserRoleEnum.ENTERPRISE)
def view_conversation(conversation_id):
    """
    View conversation details. Enterprise may view only conversations they created.
    Marks MessageReceipt rows for the enterprise user as read if any exist.
    """
    try:
        from app.models import Conversation, Message, MessageReceipt

        conv = Conversation.query.get_or_404(conversation_id)
        if conv.created_by != current_user.id:
            flash("You do not have permission to view this conversation.", "danger")
            return redirect(url_for("enterprise.communications"))

        messages = (
            db.session.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc())
            .all()
        )

        # Mark any receipts for this enterprise user as read
        (
            db.session.query(MessageReceipt)
            .join(Message, Message.id == MessageReceipt.message_id)
            .filter(
                Message.conversation_id == conv.id,
                MessageReceipt.user_id == current_user.id,
                MessageReceipt.is_read.is_(False),
            )
            .update({"is_read": True, "read_at": datetime.utcnow()}, synchronize_session=False)
        )
        db.session.commit()

        return render_template("enterprise/conversation.html", conversation=conv, messages=messages)
    except Exception:
        current_app.logger.exception("[enterprise.view_conversation] failed")
        flash("Unable to load conversation.", "danger")
        return redirect(url_for("enterprise.communications"))


# ------------------------------------------------------------------
# Compose: broadcasts to followers (FavoriteEnterprise) or target user IDs
# ------------------------------------------------------------------
@enterprise_bp.route("/notifications/compose", methods=["GET", "POST"], endpoint="notifications_compose")
@login_required
@role_required(UserRoleEnum.ENTERPRISE)
def notifications_compose():
    """
    Compose notifications (broadcast) for enterprise:
      - If 'target_user_ids' form field provided (comma-separated) send to those users.
      - Otherwise, send to followers from FavoriteEnterprise.
    Implementation uses Conversation -> Message -> MessageReceipt (fan-out receipts).
    """
    if request.method == "POST":
        title = (request.form.get("title") or "").strip() or None
        body = (request.form.get("body") or "").strip()
        raw_targets = (request.form.get("target_user_ids") or "").strip()

        if not body:
            flash("Message body is required.", "danger")
            return redirect(url_for("enterprise.notifications_compose"))

        # resolve recipients
        recipient_ids = []
        try:
            if raw_targets:
                # explicit recipients
                candidate_ids = [int(x) for x in raw_targets.split(",") if x.strip().isdigit()]
                from app.models import User
                valid = User.query.filter(User.id.in_(candidate_ids)).with_entities(User.id).all()
                recipient_ids = [r.id for r in valid]
            else:
                # followers via FavoriteEnterprise
                from app.models import FavoriteEnterprise
                follower_rows = FavoriteEnterprise.query.filter_by(enterprise_id=current_user.id).all()
                recipient_ids = [r.user_id for r in follower_rows]
        except Exception:
            current_app.logger.exception("[enterprise.notifications_compose] resolving recipients failed")
            recipient_ids = []

        if not recipient_ids:
            flash("No recipients found to send this notification to.", "warning")
            return redirect(url_for("enterprise.notifications_compose"))

        try:
            from app.models import Conversation, Message

            # create conversation (broadcast)
            conv = Conversation(created_by=current_user.id, title=title, is_group=True, is_broadcast=True)
            db.session.add(conv)
            db.session.flush()  # get conv.id

            # create message
            msg = Message(conversation_id=conv.id, sender_id=current_user.id, content=body)
            db.session.add(msg)
            db.session.flush()

            # fanout receipts
            _fanout_message_receipts(msg, recipient_ids)

            db.session.commit()
            flash(f"Sent to {len(recipient_ids)} recipient(s).", "success")
            return redirect(url_for("enterprise.communications"))

        except Exception:
            db.session.rollback()
            current_app.logger.exception("[enterprise.notifications_compose] send failed")
            flash("Failed to send notification.", "danger")
            return redirect(url_for("enterprise.notifications_compose"))

    # GET => render compose page
    return render_template("enterprise/notifications_compose.html")


# ------------------------------------------------------------------
# Followers previews & list
# ------------------------------------------------------------------
@enterprise_bp.get("/followers/preview", endpoint="followers_preview")
@login_required
@role_required(UserRoleEnum.ENTERPRISE)
def followers_preview():
    """
    Return JSON preview of followers for use in small dashboard cards.
    """
    try:
        from app.models import FavoriteEnterprise, User

        q = (
            db.session.query(User)
            .join(FavoriteEnterprise, FavoriteEnterprise.user_id == User.id)
            .filter(FavoriteEnterprise.enterprise_id == current_user.id)
            .order_by(User.id.desc())
            .limit(5)
        )
        rows = [{"id": u.id, "name": getattr(u, "name", "") or getattr(u, "email", "") or f"User {u.id}"} for u in q.all()]
        return jsonify({"top": rows})
    except Exception:
        current_app.logger.exception("[enterprise.followers_preview] failed")
        return jsonify({"top": []})


@enterprise_bp.get("/followers", endpoint="followers")
@login_required
@role_required(UserRoleEnum.ENTERPRISE)
def followers_page():
    """
    Full followers list page.
    """
    try:
        from app.models import FavoriteEnterprise, User

        q = (
            db.session.query(User)
            .join(FavoriteEnterprise, FavoriteEnterprise.user_id == User.id)
            .filter(FavoriteEnterprise.enterprise_id == current_user.id)
            .order_by(User.id.desc())
            .all()
        )
        followers = q
    except Exception:
        current_app.logger.exception("[enterprise.followers] failed")
        followers = []

    return render_template("enterprise/followers_full.html", followers=followers)


@enterprise_bp.route("/search")
@login_required
@role_required(UserRoleEnum.PATIENT)
def enterprise_search():
    """
    Example enterprise lookup. Replace with your real enterprise user table / catalog.
    Expected params: q (string)
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])

    rows = db.session.execute(text("""
        SELECT id, COALESCE(name, email) AS label
        FROM "user"
        WHERE is_enterprise = 1
          AND (name ILIKE :q OR email ILIKE :q)
        ORDER BY name NULLS LAST, email
        LIMIT 25
    """), {"q": f"%{q}%"}).mappings().all()

    return jsonify([{"id": int(r.id), "name": r.label} for r in rows])


@enterprise_bp.route("/favorites")
@login_required
@role_required(UserRoleEnum.PATIENT)
def favorites_list():
    rows = db.session.execute(text("""
        SELECT fe.enterprise_id AS id,
               COALESCE(u.name, u.email) AS name
        FROM favorite_enterprise fe
        JOIN "user" u ON u.id = fe.enterprise_id
        WHERE fe.user_id = :me
        ORDER BY name
    """), {"me": current_user.id}).mappings().all()
    return jsonify([{"id": int(r.id), "name": r.name} for r in rows])


@enterprise_bp.route("/favorite/<int:enterprise_user_id>", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def favorite_toggle(enterprise_user_id: int):
    if enterprise_user_id == current_user.id:
        flash("You cannot favorite yourself.", "warning")
        return redirect(url_for("patient.patient_dashboard"))

    exists = FavoriteEnterprise.query.get((current_user.id, enterprise_user_id))
    if exists:
        db.session.delete(exists)
        db.session.commit()
        flash("Removed from favorites.", "info")
    else:
        db.session.add(FavoriteEnterprise(user_id=current_user.id, enterprise_id=enterprise_user_id))
        db.session.commit()
        flash("Added to favorites.", "success")
    return redirect(request.referrer or url_for("patient.patient_dashboard"))



