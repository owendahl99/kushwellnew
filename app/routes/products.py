# app/routes/products.py
"""
Product-related endpoints for all users.

This blueprint handles generic product views and voting APIs that are not
specific to patient or enterprise dashboards.
"""

from __future__ import annotations

from flask import Blueprint, request, jsonify, render_template
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, or_

from app.extensions import db
from app.models import Product, Upvote
from app.utils.decorators import role_required
from app.constants.enums import UserRoleEnum  # ensure enums come from the canonical module

products_bp = Blueprint("products", __name__, url_prefix="/products")




# -------------------------
# Helpers (internal only)
# -------------------------
def _count_product_upvotes(product_id: int) -> int:
    """Return total upvotes for a product (non-negative by design)."""
    return (
        db.session.query(func.count(Upvote.id))
        .filter(Upvote.target_type == "product", Upvote.target_id == product_id)
        .scalar()
        or 0
    )


def _get_user_product_vote(user_id: int, product_id: int) -> Upvote | None:
    """Fetch current user's upvote for a product, if any."""
    return Upvote.query.filter_by(
        user_id=user_id, target_type="product", target_id=product_id
    ).first()


# -------------------------
# Pages
# -------------------------
@products_bp.route("/detail/<int:product_id>")
def product_detail(product_id: int):
    """Generic product detail page."""
    product = Product.query.get_or_404(product_id)

    # Average QoL uses your existing helper (kept as-is)
    from app.utils.scoring import get_average_qol_score
    avg_qol = get_average_qol_score(product_id)

    total_votes = _count_product_upvotes(product_id)

    return render_template(
        "products/detail.html",
        product=product,
        avg_qol=avg_qol,
        votes={"total": total_votes, "down": 0},  # no downvotes tracked
    )


# -------------------------
# Voting APIs (JSON)
# -------------------------

@products_bp.route("/vote/<int:product_id>", methods=["POST"])
@login_required
@role_required(UserRoleEnum.PATIENT)
def vote_product(product_id: int):
    """
    Patient submits or updates their QoL upvote for a product.
    - One upvote per (user, product) enforced by model unique constraint.
    - QoL must be integer in [0, 10].
    """
    # Ensure product exists
    Product.query.get_or_404(product_id)

    # Accept JSON or form; prefer JSON if present
    data = request.get_json(silent=True) or request.form or {}

    if "qol_improvement" not in data:
        return jsonify({"error": "Missing 'qol_improvement'"}), 400

    try:
        qol_score = int(data["qol_improvement"])
        if not (0 <= qol_score <= 10):
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "qol_improvement must be an integer between 0 and 10"}), 400

    vote = _get_user_product_vote(current_user.id, product_id)  
    if vote:
        vote.qol_improvement = qol_score
    else:
        db.session.add(
            Upvote(
                user_id=current_user.id,
                target_type="product",
                target_id=product_id,
                qol_improvement=qol_score,
            )
        )

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
    

@products_bp.route("/search")
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    rows = (
        Product.query
        .filter(Product.name.ilike(f"%{q}%"))
        .order_by(Product.name.asc())
        .limit(25)
        .all()
    )
    return jsonify([{
        "id": p.id,
        "name": p.name,
        "image": getattr(p, "image_path", None) or getattr(p, "image_url", None),
        "avg_qol": getattr(p, "avg_qol", 0) or 0,
        "class": getattr(p, "chem_class", None),
        "thc": getattr(p, "thc_percent", None) or 0,
        "cbd": getattr(p, "cbd_percent", None) or 0,
    } for p in rows])


@products_bp.route("/search_enterprise")
def search_enterprise():
    """
    Thin wrapper so the dashboard JS can hit /products/search_enterprise.
    If you have enterprise catalog search in enterprise_bp, call into it here.
    For now, return [] to keep the UI happy.
    """
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify([])
    # TODO: integrate enterprise catalog search; for now, no-op:
    return jsonify([])


@products_bp.route("/<int:product_id>")
def detail(product_id: int):
    p = Product.query.get_or_404(product_id)
    return render_template("products/detail.html", product=p)


