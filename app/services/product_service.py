# FILE: app/services/product_service.py
from __future__ import annotations
from sqlalchemy import or_
from flask import current_app
from app.extensions import db
from app.models import Product


# ------------------------------------------------------------
# Product Search Service
# ------------------------------------------------------------
def search_products(query: str) -> list[dict]:
    """
    Performs a lightweight LIKE-based product search across common text fields.
    Returns up to 25 results for patient-facing UI.
    """
    if not query:
        return []

    try:
        like = f"%{query.strip()}%"
        filters = []
        # Check fields exist dynamically (schema-safe)
        for field_name in ("name", "product_name", "manufacturer", "brand", "category", "description"):
            if hasattr(Product, field_name):
                filters.append(getattr(Product, field_name).ilike(like))

        if not filters:
            return []

        results = (
            Product.query
            .filter(or_(*filters))
            .order_by(Product.name.asc() if hasattr(Product, "name") else Product.id.asc())
            .limit(25)
            .all()
        )

        def _serialize(p: Product) -> dict:
            return {
                "id": p.id,
                "name": getattr(p, "name", None) or getattr(p, "product_name", None),
                "category": getattr(p, "category", None),
                "manufacturer": getattr(p, "manufacturer", None) or getattr(p, "brand", None),
                "thc_content": getattr(p, "thc_content", None),
                "cbd_content": getattr(p, "cbd_content", None),
                "average_score": getattr(p, "average_score", None),
            }

        return [_serialize(p) for p in results]

    except Exception as e:
        current_app.logger.exception("[ProductService] search_products: %s", e)
        return []
