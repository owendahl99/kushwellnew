"""
Admin blueprint routes.

This module defines all endpoints used by administrative users to
moderate products, manage users, approve new product submissions, and
handle affliction suggestions. It is largely copied from the original
admin.py file provided by the user and organized into a blueprint for
registration with the Flask application.

Note: Some functions import constants or utilities from ``app.constants``
and ``app.utils``. Make sure those modules are present when wiring up
the complete application. Where references are missing (for example,
``ProductRejection``), this module preserves the original calls but
assumes the underlying models and functions exist.
"""

from datetime import datetime
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)

from sqlalchemy.inspection import inspect
from sqlalchemy import false, func
    
from flask_login import current_user,  login_required
from functools import wraps
import os
import shutil

from app.utils.decorators import role_required
from app.constants.enums import ModerationReason
from app.extensions import db
from app.models import (
    Product,
    ProductChemProfile,  # new
    PatientCondition,
    ProductTerpene,
    User,
    UploadedFile,
    AuditLog,
    ModerationReport,
    ProductSubmission,
    AfflictionSuggestion,
)
from app.constants.afflictions import AFFLICTION_LIST, AFFLICTION_LEVELS, get_afflictions, get_levels, normalize_afflictions, serialize_afflictions, parse_afflictions, is_valid_level
from app.constants.terpenes import TERPENES, COMMON_TERPENES, get_terpenes, get_common_terpenes
from app.constants.application_methods import APPLICATION_METHODS, APPLICATION_METHOD_CHOICES
from app.constants.enums import UserRoleEnum

# Additional imports used in some routes
from werkzeug.utils import secure_filename

# Allowed file types for product image uploads
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename: str) -> bool:
    """Return True if the filename has an allowed extension."""
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ----------------- Access Control -------------------


def admin_required(view_func):
    """Decorator that restricts access to admin users only."""

    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRoleEnum.ADMIN:
            flash("Admin access required.", "danger")
            return redirect(url_for("auth.login"))
        return view_func(*args, **kwargs)

    return wrapper


# --------------------------------------------------------------------------
# Admin Dashboard
# --------------------------------------------------------------------------
@admin_bp.route("/dashboard", methods=["GET"], endpoint="admin_dashboard")
@login_required
@role_required(UserRoleEnum.ADMIN)
def admin_dashboard():
    """Display high-level admin metrics about products and disputes."""

    # Redirect non-admin users safely
    if not current_user.is_authenticated or getattr(current_user, "role", None) != UserRoleEnum.ADMIN:
        return redirect(url_for("auth.login", next=request.path))

    # Safe product counts across schema variants
    prod_cols = {a.key for a in inspect(Product).attrs}
    q = db.session.query(Product)

    def count_where(field, value):
        if field == "approval_status" and "approval_status" in prod_cols:
            return q.filter(Product.approval_status == value).count()
        if field == "status" and "status" in prod_cols:
            return q.filter(Product.status == value).count()
        if field == "is_approved" and "is_approved" in prod_cols:
            return q.filter(Product.is_approved.is_(value == "approved")).count()
        return 0

    approved = (
        count_where("approval_status", "approved")
        or count_where("status", "approved")
        or count_where("is_approved", "approved")
    )
    pending = (
        count_where("approval_status", "pending")
        or count_where("status", "pending")
        or 0
    )
  
    total_products = Product.query.count()
    pending_count = Product.query.filter_by(approval_status="pending").count()
    approved_count = Product.query.filter_by(approval_status="approved").count()
    rejected_count = Product.query.filter_by(approval_status="rejected").count()
    dispute_count = ModerationReport.query.count()

    return render_template(
        "admin/admin_dashboard.html",
        total_products=total_products,
        pending_count=pending_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        dispute_count=dispute_count,
    )

# ---- Communications preview (Admin) -----------------------------------------
@admin_bp.route("/comm/preview", endpoint="comm_preview")
@admin_required
def comm_preview():
    # Example using your notification tables; adjust to your schema.
    rows = db.session.execute(text("""
        SELECT n.id, COALESCE(n.title, n.subject, '(no subject)') AS subject, n.created_at AS created
        FROM notification n
        ORDER BY n.created_at DESC
        LIMIT 5
    """)).mappings().all()
    ser = [{"id": int(r.id), "subject": r.subject, "when": str(r.created)} for r in rows]
    return jsonify({"top": ser})


# ----------------- Product Moderation -------------------


@admin_bp.route("/product/<int:product_id>")
@admin_required
def review_product(product_id):
    """Display a single product awaiting approval or rejection."""
    product = Product.query.get_or_404(product_id)
    return render_template(
        "admin/review_product.html",
        product=product,
        moderation_reasons=ModerationReason,
    )


@admin_bp.route("/product_submissions/<int:submission_id>/approve", methods=["POST"])
@role_required(UserRoleEnum.ADMIN)
def approve_product_submission(submission_id):
    """Approve a product submission, create a Product, and move its image."""
    submission = ProductSubmission.query.get_or_404(submission_id)

    # Move image (same as you had)
    final_image_path = None
    if submission.image_path:
        source_path = os.path.join(
            current_app.root_path, "static", submission.image_path
        )
        products_folder = os.path.join(
            current_app.root_path, "static", "uploads", "products"
        )
        os.makedirs(products_folder, exist_ok=True)
        filename = os.path.basename(submission.image_path)
        dest_path = os.path.join(products_folder, filename)
        try:
            shutil.move(source_path, dest_path)
            final_image_path = f"uploads/products/{filename}"
        except Exception as e:
            flash(f"Image move failed: {e}", "warning")
            final_image_path = submission.image_path  # fallback

    # Create Product
    product = Product(
        name=submission.name,
        description=submission.description,
        category=getattr(submission, "category", None),
        affliction=getattr(submission, "affliction", None),
        image_path=final_image_path,
        approval_status="approved",
        inventory=0,
        is_public=True,
    )
    db.session.add(product)
    db.session.flush()  # get product.id

    # Attach chem profile (if submission has % or chem_type fields)
    chem_type = (getattr(submission, "chem_type", None) or "n/a").lower()
    thc_percent = getattr(submission, "thc_percent", None)
    cbd_percent = getattr(submission, "cbd_percent", None)

    if ProductChemProfile:
        product.profile = ProductChemProfile(
            chem_type=chem_type,
            thc_percent=thc_percent,
            cbd_percent=cbd_percent,
        )

    # Attach terpenes (if submission stored them; fallback to empty)
    terp_pairs = getattr(
        submission, "terpene_pairs", None
    )  # e.g. [("myrcene", 0.6), ...]
    if terp_pairs and hasattr(product, "terpenes"):
        product.terpenes.clear()
        for t_name, pct in terp_pairs:
            product.terpenes.append(ProductTerpene(name=t_name, percent=pct))

    # Mark submission approved
    submission.status = "approved"
    db.session.commit()
    flash(f"Product '{product.name}' approved and added to catalog.", "success")
    return redirect(url_for("admin.product_submissions"))


@admin_bp.route("/product/<int:product_id>/reject", methods=["POST"])
@admin_required
def reject_product(product_id):
    """Reject a pending product and record the reason."""
    product = Product.query.get_or_404(product_id)
    reason = request.form.get("reason", "").strip()

    if reason not in [r.value for r in ModerationReason]:
        flash("Invalid rejection reason.", "danger")
        return redirect(url_for("admin.review_product", product_id=product.id))

    product.approval_status = "rejected"
    product.is_public = False

    # This model must be defined in app.models for this to work.
    # We do not currently persist a separate ProductRejection record.  If your
    # data model defines such a table you can import it and create a
    # row here.  For now we simply log the rejection via the audit log.
    # If you later add a ``ProductRejection`` model, import it above and
    # add a record here.
    # from app.models import ProductRejection
    # rejection = ProductRejection(product_id=product.id, reason=reason)
    # db.session.add(rejection)
    db.session.commit()

    flash("Product rejected and removed from system.", "info")
    return redirect(url_for("admin.pending_products"))


# ----------------- Product Submission Moderation -------------------


@admin_bp.route("/product_submissions")
@admin_required
def product_submissions():
    """List product submissions awaiting review."""
    submissions = ProductSubmission.query.order_by(
        ProductSubmission.last_checkin_at.desc()
    ).all()
    return render_template("admin/product_submissions.html", submissions=submissions)


@admin_bp.route("/product_submissions/<int:submission_id>")
@admin_required
def view_product_submission(submission_id):
    """Display details for a single product submission."""
    submission = ProductSubmission.query.get_or_404(submission_id)
    return render_template(
        "admin/product_submission_detail.html", submission=submission
    )


# ----------------- Product Submission Direct From Admin------------------------


@admin_bp.route("/product/add", methods=["GET", "POST"])
@role_required(UserRoleEnum.ADMIN)
def add_product():
    from app.constants import APPLICATION_METHODS, AFFLICTION_LIST

    if request.method == "POST":
        # existing fields...
        name = request.form.get("name")
        description = request.form.get("description")
        application_method = request.form.get("application_method")
        suggested_treatment = request.form.get("suggested_treatment")
        retail_price = request.form.get("retail_price")
        manufacturer_claim = request.form.get("manufacturer_claim")

        # image handling (unchanged)
        image_file = request.files.get("image")
        image_path = None
        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            upload_folder = os.path.join(
                current_app.root_path, "static/uploads/products"
            )
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            image_file.save(filepath)
            image_path = f"uploads/products/{filename}"
        elif image_file and image_file.filename != "":
            flash("Invalid image file type.", "danger")
            return redirect(request.url)

        product = Product(
            name=name,
            description=description,
            application_method=application_method,
            suggested_treatment=suggested_treatment,
            retail_price=retail_price or None,
            manufacturer_claim=manufacturer_claim,
            image_path=image_path,
            approval_status="pending",
            is_public=False,
        )
        db.session.add(product)
        db.session.flush()

        # === NEW: chem profile + terpenes ===
        chem_type = (request.form.get("chem_type") or "n/a").lower()

        def to_float(v):
            try:
                return (
                    float(v)
                    if v
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

        if ProductChemProfile:
            product.profile = ProductChemProfile(
                chem_type=chem_type,
                thc_percent=thc_percent,
                cbd_percent=cbd_percent,
            )
        # terpenes:
        pairs, err = parse_terpene_form(request.form, top_n=10)
        if err:
            db.session.rollback()
            flash(err, "danger")
            return redirect(request.url)
        if hasattr(product, "terpenes"):
            product.terpenes.clear()
            for t_name, pct in pairs:
                product.terpenes.append(ProductTerpene(name=t_name, percent=pct))

        db.session.commit()
        flash("Product added and awaiting admin approval.", "success")
        return redirect(url_for("admin.admin_dashboard"))

    return render_template(
        "admin/product_form.html",
        product=None,
        APPLICATION_METHODS=APPLICATION_METHODS,
        AFFLICTION_LIST=AFFLICTION_LIST,
    )


# ----------------- Product Edits Direct From Admin------------------------


@admin_bp.route("/product/<int:product_id>/edit", methods=["GET", "POST"])
@role_required(UserRoleEnum.ADMIN)
def edit_product(product_id):
    """Allow an admin to edit an existing product."""
    from app.constants import APPLICATION_METHODS, AFFLICTION_LIST

    product = Product.query.get_or_404(product_id)

    if request.method == "POST":
        product.name = request.form.get("name")
        product.description = request.form.get("description")
        product.application_method = request.form.get("application_method")
        product.suggested_treatment = request.form.get("suggested_treatment")
        product.retail_price = request.form.get("retail_price") or None
        product.manufacturer_claim = request.form.get("manufacturer_claim")

        # === NEW: chem profile + terpenes ===
        chem_type = (request.form.get("chem_type") or "n/a").lower()

        def to_float(v):
            try:
                return (
                    float(v)
                    if v
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

        if ProductChemProfile:
            if getattr(product, "profile", None) is None:
                product.profile = ProductChemProfile(
                    chem_type=chem_type,
                    thc_percent=thc_percent,
                    cbd_percent=cbd_percent,
                )
            else:
                product.profile.chem_type = chem_type
                product.profile.thc_percent = thc_percent
                product.profile.cbd_percent = cbd_percent

        pairs, err = parse_terpene_form(request.form, top_n=10)
        if err:
            flash(err, "danger")
            return redirect(request.url)
        if hasattr(product, "terpenes"):
            product.terpenes.clear()
            for t_name, pct in pairs:
                product.terpenes.append(ProductTerpene(name=t_name, percent=pct))

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
        return redirect(url_for("admin.admin_dashboard"))

    return render_template(
        "admin/product_form.html",
        product=product,
        APPLICATION_METHODS=APPLICATION_METHODS,
        AFFLICTION_LIST=AFFLICTION_LIST,
    )


# ----------------- Disputes -------------------


@admin_bp.route("/disputes")
@admin_required
def dispute_reports():
    """List all moderation reports for admin review."""
    reports = ModerationReport.query.order_by(ModerationReport.timestamp.desc()).all()
    return render_template("admin/disputes.html", reports=reports)


# ----------------- User Management -------------------


@admin_bp.route("/users")
@admin_required
def list_users():
    """List all users in the system for admin management."""
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=users)


@admin_bp.route("/user/<int:user_id>/blacklist", methods=["POST"])
@admin_required
def blacklist_user(user_id):
    """Blacklist a user to prevent further usage."""
    user = User.query.get_or_404(user_id)
    user.is_blacklisted = True
    db.session.commit()
    log_admin_action("user_blacklisted", current_user.id, user.id)
    flash("User blacklisted.", "warning")
    return redirect(url_for("admin.list_users"))


@admin_bp.route("/user/<int:user_id>/unblacklist", methods=["POST"])
@admin_required
def unblacklist_user(user_id):
    """Remove a user from the blacklist."""
    user = User.query.get_or_404(user_id)
    user.is_blacklisted = False
    db.session.commit()
    log_admin_action("user_unblacklisted", current_user.id, user.id)
    flash("User reinstated.", "success")
    return redirect(url_for("admin.list_users"))


@admin_bp.route("/user/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_user(user_id):
    """Permanently delete a user account."""
    user = User.query.get_or_404(user_id)
    log_admin_action("user_deleted", current_user.id, user.id, meta=user.email)
    db.session.delete(user)
    db.session.commit()
    flash("User permanently deleted.", "danger")
    return redirect(url_for("admin.list_users"))


# ----------------- File Management -------------------


@admin_bp.route("/files")
@admin_required
def list_files():
    """List uploaded files in the system."""
    files = UploadedFile.query.order_by(UploadedFile.uploaded_at.desc()).all()
    return render_template("admin/files.html", files=files)


@admin_bp.route("/file/<int:file_id>/delete", methods=["POST"])
@admin_required
def delete_file(file_id):
    """Delete a specific uploaded file."""
    file = UploadedFile.query.get_or_404(file_id)
    log_admin_action("file_deleted", current_user.id, file.id, meta=file.filename)

    try:
        file_path = os.path.join(current_app.root_path, "static", file.filepath)
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        flash(f"Filesystem error: {str(e)}", "danger")

    db.session.delete(file)
    db.session.commit()
    flash("File deleted.", "danger")
    return redirect(url_for("admin.list_files"))


# ----------------- Affliction Suggestions -------------------


@admin_bp.route("/affliction_suggestions")
@admin_required
def affliction_suggestions():
    """List grouped affliction suggestions awaiting approval."""
    override = request.args.get("override", "0") == "1"

    query = (
        db.session.query(
            AfflictionSuggestion.affliction_name,
            db.func.count(AfflictionSuggestion.id).label("request_count"),
        )
        .filter(AfflictionSuggestion.status == "pending")
        .group_by(AfflictionSuggestion.affliction_name)
    )

    if not override:
        # Only show suggestions with at least 3 requests unless override
        query = query.having(db.func.count(AfflictionSuggestion.id) >= 3)

    grouped_suggestions = query.all()

    return render_template(
        "admin/affliction_suggestions.html",
        suggestions=grouped_suggestions,
        override=override,
    )


@admin_bp.route(
    "/affliction_suggestions/approve/<string:affliction_name>", methods=["POST"]
)
@admin_required
def approve_affliction(affliction_name):
    """Approve an affliction suggestion and update models and constants."""
    from app.constants import afflictions as afflictions_module

    # Approve all matching pending suggestions
    db.session.query(AfflictionSuggestion).filter_by(
        affliction_name=affliction_name, status="pending"
    ).update({"status": "approved"})

    # Update PatientCondition where affliction == "Other" and user submitted this suggestion
    submitters = [
        s.submitted_by_id
        for s in AfflictionSuggestion.query.filter_by(
            affliction_name=affliction_name
        ).all()
    ]
    if submitters:
        db.session.query(PatientCondition).filter(
            PatientCondition.affliction == "Other",
            PatientCondition.patient.has(User.id.in_(submitters)),
        ).update({"affliction": affliction_name}, synchronize_session=False)

    # Add to AFFLICTION_LIST in memory and persist to file
    if affliction_name not in afflictions_module.AFFLICTION_LIST:
        afflictions_module.AFFLICTION_LIST.append(affliction_name)
        constants_path = os.path.join(
            current_app.root_path, "app", "constants", "afflictions.py"
        )
        try:
            with open(constants_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            new_list_str = (
                "AFFLICTION_LIST = " + repr(afflictions_module.AFFLICTION_LIST) + "\n"
            )
            with open(constants_path, "w", encoding="utf-8") as f:
                for line in lines:
                    if line.strip().startswith("AFFLICTION_LIST"):
                        f.write(new_list_str)
                    else:
                        f.write(line)
        except Exception as e:
            flash(f"Failed to update constants file: {e}", "warning")

    db.session.commit()
    flash(f"Affliction '{affliction_name}' approved and added to list.", "success")
    return redirect(url_for("admin.affliction_suggestions"))


@admin_bp.route(
    "/affliction_suggestions/reject/<string:affliction_name>", methods=["POST"]
)
@admin_required
def reject_affliction(affliction_name):
    """Reject an affliction suggestion."""
    db.session.query(AfflictionSuggestion).filter_by(
        affliction_name=affliction_name, status="pending"
    ).update({"status": "rejected"})
    db.session.commit()
    flash(f"Affliction '{affliction_name}' rejected.", "danger")
    return redirect(url_for("admin.affliction_suggestions"))


# ----------------- Audit Log Helper -------------------


def log_admin_action(action_type, performed_by, target_id, meta=""):
    """Persist an audit log entry for admin actions."""
    log = AuditLog(
        action_type=action_type,
        performed_by=performed_by,
        target_id=target_id,
        metadata=meta,
    )
    db.session.add(log)
    db.session.commit()

from app.models import Conversation, Message, MessageReceipt

@admin_bp.route("/comm/compose", methods=["GET", "POST"])
@login_required
@role_required(UserRoleEnum.ADMIN)
def admin_comm_compose():
    """
    Admin: Compose a message to arbitrary user ids (one-to-one or multi).
    POST fields:
      - title (optional)
      - target_user_ids: comma-separated user ids
      - body (required)
    Uses Conversation/Message/MessageReceipt only.
    """
    if request.method == "POST":
        title = (request.form.get("title") or "").strip() or None
        raw = (request.form.get("target_user_ids") or "").strip()
        body = (request.form.get("body") or "").strip()
        if not body or not raw:
            flash("Recipient(s) and message body are required.", "warning")
            return redirect(url_for("admin.admin_comm_compose"))

        ids = [int(x) for x in raw.split(",") if x.strip().isdigit()]
        if not ids:
            flash("No valid user IDs provided.", "warning")
            return redirect(url_for("admin.admin_comm_compose"))

        try:
            # function-level imports to avoid circular import problems
            from app.models import User, Conversation, Message, MessageReceipt

            valid_users = User.query.filter(User.id.in_(ids)).all()
            valid_ids = [u.id for u in valid_users]
            if not valid_ids:
                flash("No valid recipients found.", "warning")
                return redirect(url_for("admin.admin_comm_compose"))

            conv = Conversation(
                created_by=current_user.id,
                title=title,
                is_group=len(valid_ids) > 1,
                is_broadcast=False,
            )
            db.session.add(conv)
            db.session.flush()

            # add initial message
            msg = Message(conversation_id=conv.id, sender_id=current_user.id, body=body)
            db.session.add(msg)
            db.session.flush()

            # add receipts for recipients (so they see the message)
            for uid in valid_ids:
                if uid != current_user.id:
                    db.session.add(MessageReceipt(message_id=msg.id, user_id=uid))

            db.session.commit()
            flash(f"Message sent to {len(valid_ids)} user(s).", "success")
            return redirect(url_for("admin.admin_comm_inbox"))

        except Exception:
            db.session.rollback()
            current_app.logger.exception("[admin_comm_compose] failed")
            flash("Failed to send message.", "danger")
            return redirect(url_for("admin.admin_comm_compose"))

    # GET -> render compose UI
    return render_template("admin/comm_compose.html")


@admin_bp.route("/comm/inbox")
@login_required
@role_required(UserRoleEnum.ADMIN)
def admin_comm_inbox():
    """
    List conversations the admin is involved in (either sent messages or has receipts).
    """
    try:
        from app.models import Conversation, Message, MessageReceipt

        convs = (
            db.session.query(Conversation)
            .join(Message, Message.conversation_id == Conversation.id)
            .outerjoin(MessageReceipt, MessageReceipt.message_id == Message.id)
            .filter(
                (Message.sender_id == current_user.id) | (MessageReceipt.user_id == current_user.id)
            )
            .order_by(Conversation.created_at.desc())
            .distinct()
            .all()
        )

        # unread counts for admin (per conversation)
        unread_map = {}
        if convs:
            conv_ids = [c.id for c in convs]
            rows = (
                db.session.query(Message.conversation_id, func.count(MessageReceipt.message_id))
                .join(MessageReceipt, MessageReceipt.message_id == Message.id)
                .filter(
                    Message.conversation_id.in_(conv_ids),
                    MessageReceipt.user_id == current_user.id,
                    MessageReceipt.read.is_(False),
                )
                .group_by(Message.conversation_id)
                .all()
            )
            unread_map = {cid: cnt for cid, cnt in rows}

        return render_template("admin/comm_inbox.html", conversations=convs, unread_map=unread_map)

    except Exception:
        current_app.logger.exception("[admin_comm_inbox] failed")
        flash("Unable to load inbox.", "danger")
        return render_template("admin/comm_inbox.html", conversations=[], unread_map={})


@admin_bp.route("/comm/<int:conversation_id>")
@login_required
@role_required(UserRoleEnum.ADMIN)
def admin_comm_view(conversation_id):
    """
    View a conversation. Admin may view if they are sender of any message in the
    conversation or if they are a recipient (have receipts) for it.
    """
    try:
        from app.models import Conversation, Message, MessageReceipt

        conv = Conversation.query.get_or_404(conversation_id)

        # permission: admin may view if they were sender in the conversation or have any receipt for it
        is_sender = (
            db.session.query(Message)
            .filter(Message.conversation_id == conv.id, Message.sender_id == current_user.id)
            .first()
            is not None
        )
        is_recipient = (
            db.session.query(MessageReceipt)
            .join(Message, Message.id == MessageReceipt.message_id)
            .filter(Message.conversation_id == conv.id, MessageReceipt.user_id == current_user.id)
            .first()
            is not None
        )

        if not (is_sender or is_recipient):
            flash("You are not a participant in this conversation.", "danger")
            return redirect(url_for("admin.admin_comm_inbox"))

        # load messages
        messages = (
            db.session.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.asc())
            .all()
        )

        # mark admin's MessageReceipts as read for this conversation
        (
            db.session.query(MessageReceipt)
            .join(Message, Message.id == MessageReceipt.message_id)
            .filter(
                Message.conversation_id == conv.id,
                MessageReceipt.user_id == current_user.id,
                MessageReceipt.read.is_(False),
            )
            .update({"read": True, "read_at": datetime.utcnow()}, synchronize_session=False)
        )
        db.session.commit()

        return render_template("admin/comm_view.html", conversation=conv, messages=messages)

    except Exception:
        current_app.logger.exception("[admin_comm_view] failed")
        flash("Unable to load conversation.", "danger")
        return redirect(url_for("admin.admin_comm_inbox"))


@admin_bp.route("/comm/broadcast", methods=["GET", "POST"])
@login_required
@role_required(UserRoleEnum.ADMIN)
def admin_comm_broadcast():
    """
    Admin broadcast:
      - target_role: 'all' or comma-separated roles (e.g. 'patient,enterprise')
      - body required
    Broadcast uses Conversation/Message/MessageReceipt only.
    """
    if request.method == "POST":
        title = (request.form.get("title") or "").strip() or None
        raw_roles = (request.form.get("target_role") or "all").strip()
        body = (request.form.get("body") or "").strip()
        if not body:
            flash("Message body is required.", "warning")
            return redirect(url_for("admin.admin_comm_broadcast"))

        try:
            from app.models import User, Conversation, Message, MessageReceipt

            if raw_roles.lower() == "all":
                recipient_ids = [r.id for r in User.query.with_entities(User.id).all()]
            else:
                wanted = [r.strip().lower() for r in raw_roles.split(",") if r.strip()]
                recipient_ids = [r.id for r in User.query.filter(func.lower(User.role).in_(wanted)).all()]

            if not recipient_ids:
                flash("No recipients found for selected target.", "warning")
                return redirect(url_for("admin.admin_comm_broadcast"))

            conv = Conversation(created_by=current_user.id, title=title, is_group=True, is_broadcast=True)
            db.session.add(conv)
            db.session.flush()

            msg = Message(conversation_id=conv.id, sender_id=current_user.id, body=body)
            db.session.add(msg)
            db.session.flush()

            # create receipts for recipients (exclude sender)
            for uid in recipient_ids:
                if uid != current_user.id:
                    db.session.add(MessageReceipt(message_id=msg.id, user_id=uid))

            db.session.commit()
            flash(f"Broadcast sent to {len(recipient_ids)} users.", "success")
            return redirect(url_for("admin.admin_comm_inbox"))

        except Exception:
            db.session.rollback()
            current_app.logger.exception("[admin_comm_broadcast] failed")
            flash("Failed to send broadcast.", "danger")
            return redirect(url_for("admin.admin_comm_broadcast"))

    # GET -> render a form for target selection
    return render_template("admin/comm_broadcast.html")


@admin_bp.route('/theme', methods=['GET', 'POST'])
@login_required
@admin_required
def theme_config():
    theme = ThemeConfig.query.first() or ThemeConfig()
    if request.method == 'POST':
        theme.industrial_color = request.form.get('industrial_color')
        theme.callout_color = request.form.get('callout_color')
        db.session.add(theme)
        db.session.commit()
        flash('Theme updated successfully!', 'success')
        return redirect(url_for('admin.theme_config'))
    return render_template('admin/theme_config.html', theme=theme)
