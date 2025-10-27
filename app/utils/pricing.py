from sqlalchemy import func
from app.models import InventoryEntry


def get_product_price_stats(product_id, db_session):
    stats = (
        db_session.query(
            func.avg(InventoryEntry.price).label("avg_price"),
            func.min(InventoryEntry.price).label("min_price"),
            func.max(InventoryEntry.price).label("max_price"),
        )
        .filter(InventoryEntry.product_id == product_id)
        .first()
    )

    return {
        "average": float(stats.avg_price or 0),
        "min": float(stats.min_price or 0),
        "max": float(stats.max_price or 0),
    }


