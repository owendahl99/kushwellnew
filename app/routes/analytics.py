"""
Analytics and search routes blueprint.

This blueprint exposes endpoints for searching products, aggregating product scores
for analytics, and returning a current user's vote history. It wraps the
functionality of the original ``analytics.py`` provided by the user and removes
duplicate definitions present in that file.

Search results render an HTML template while score endpoints return JSON data.
"""

from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user

from app.constants.enums import UserRoleEnum
from app.utils.decorators import role_required

# Import scoring helpers from analytics module if available
try:
    from analytics.scoring import (
        get_aggregate_product_scores,
        get_patient_product_scores,
    )
except ImportError:
    # Define placeholders so the blueprint can be imported without failing;
    # in a real deployment, install or implement these functions.
    def get_aggregate_product_scores():
        return []

    def get_patient_product_scores(user_id):
        return []


analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/search", methods=["GET"])
def product_search():
    """Simple product search that returns a rendered template."""
    query = request.args.get("q", "").strip()
    products = []

    if query:
        products = (
            Product.query.filter(Product.name.ilike(f"%{query}%"))
            .order_by(Product.name.asc())
            .all()
        )

    return render_template(
        "analytics/search_results.html", query=query, products=products
    )


@analytics_bp.route("/products")
@login_required
def aggregate_scores():
    """Return aggregate quality-of-life scores for all products as JSON."""
    scores = get_aggregate_product_scores()
    return jsonify(scores)


@analytics_bp.route("/my_votes")
@role_required(UserRoleEnum.PATIENT)
def my_product_scores():
    """Return the current patient's votes on products as JSON."""
    votes = get_patient_product_scores(current_user.id)
    return jsonify(
        [
            {
                "product_id": v.target_id,
                "qol_improvement": v.qol_improvement,
            }
            for v in votes
        ]
    )


