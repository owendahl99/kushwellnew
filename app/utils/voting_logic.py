# utils/voting_logic.py

from app.extensions import db
from app.models import Upvote


def cast_upvote(user_id: int, target_type: str, target_id: int):
    """
    Cast or remove an upvote endorsement by user on a target (product, provider, dispensary, etc).
    If user already upvoted, remove it (toggle behavior).
    """
    existing = Upvote.query.filter_by(
        user_id=user_id, target_type=target_type, target_id=target_id
    ).first()

    if existing:
        # Toggle off existing upvote
        db.session.delete(existing)
        db.session.commit()
        return {"message": "Upvote removed", "upvoted": False}
    else:
        # Add new upvote
        new_upvote = Upvote(
            user_id=user_id, target_type=target_type, target_id=target_id
        )
        db.session.add(new_upvote)
        db.session.commit()
        return {"message": "Upvote added", "upvoted": True}


def count_upvotes(target_type: str, target_id: int) -> int:
    """Count total upvotes for a given target."""
    return Upvote.query.filter_by(target_type=target_type, target_id=target_id).count()


