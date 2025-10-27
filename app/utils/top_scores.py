from typing import List, Dict
from sqlalchemy import func, desc
from app.models import Product, Upvote


def top_scores(affliction_or_list, limit=3) -> Dict[str, List[Product]]:
    """
    Returns top products by average QoL score for the given affliction(s).

    Always returns a dictionary mapping:
        { affliction_name: [Product, Product, ...] }

    If affliction_or_list is empty or None:
        Returns {"Overall": [Product, Product, ...]}.

    Args:
        affliction_or_list (str or list of str or None): One or more affliction names.
            If None or empty, returns top products overall.
        limit (int): Number of top products per affliction to return.
    """

    def query_top_for_single_affliction(affliction_name: str) -> List[Product]:
        query = (
            Product.query.join(
                Upvote,
                (Upvote.target_id == Product.id) & (Upvote.target_type == "product"),
            )
            .filter(Product.affliction == affliction_name)
            .with_entities(Product, func.avg(Upvote.qol_improvement).label("avg_qol"))
            .group_by(Product.id)
            .order_by(desc("avg_qol"))
            .limit(limit)
        )
        results = query.all()
        return [r[0] for r in results]

    # No affliction → overall top products
    if not affliction_or_list:
        query = (
            Product.query.join(
                Upvote,
                (Upvote.target_id == Product.id) & (Upvote.target_type == "product"),
            )
            .with_entities(Product, func.avg(Upvote.qol_improvement).label("avg_qol"))
            .group_by(Product.id)
            .order_by(desc("avg_qol"))
            .limit(limit)
        )
        results = query.all()
        return {"Overall": [r[0] for r in results]}

    # Single affliction
    if isinstance(affliction_or_list, str):
        return {affliction_or_list: query_top_for_single_affliction(affliction_or_list)}

    # List / tuple of afflictions
    if isinstance(affliction_or_list, (list, tuple)):
        result: Dict[str, List[Product]] = {}
        for aff in affliction_or_list:
            result[aff] = query_top_for_single_affliction(aff)
        return result

    raise ValueError("Invalid affliction_or_list argument")


