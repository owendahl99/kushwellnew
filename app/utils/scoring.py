# FILE: utilities/scoring.py

from __future__ import annotations
from typing import Any, Dict, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.extensions import db
from app.models import WellnessAttribution, Upvote, ProductAggregateScore

   

# -------------------------------------------------------------------
# Core helpers
# -------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _normalize_1_10(val: Any) -> Optional[int]:
    if val is None or (isinstance(val, str) and val.strip() == ""):
        return None
    if isinstance(val, bool):
        return 10 if val else 1
    try:
        v = float(val)
        if 0.0 <= v <= 1.0:
            v = 1.0 + v * 9.0
        return int(round(_clamp(v, 1.0, 10.0)))
    except Exception:
        return None

def allocate_attributions(checkin, prev_checkin, product_effectiveness: list[dict[str, Any]]):
    """
    Allocate QoL improvements across products based on effectiveness scores (0-10)

    :param checkin: current WellnessCheck object
    :param prev_checkin: previous WellnessCheck object (or None)
    :param product_effectiveness: list of {"product_id": int, "score": int (0-10)}
    """
    from app.models import WellnessAttribution
    from app.extensions import db

    # Protect against divide by zero
    total_score = sum(p["score"] for p in product_effectiveness if p["score"] > 0) or 1.0

    # Compute per-metric deltas
    deltas = {
        "pain": (prev_checkin.pain_level - checkin.pain_level) if prev_checkin else 0,
        "mood": (checkin.mood_level - prev_checkin.mood_level) if prev_checkin else 0,
        "energy": (checkin.energy_level - prev_checkin.energy_level) if prev_checkin else 0,
        "clarity": (checkin.clarity_level - prev_checkin.clarity_level) if prev_checkin else 0,
        "appetite": (checkin.appetite_level - prev_checkin.appetite_level) if prev_checkin else 0,
    }

    # For each product, assign weighted share of each delta
    for prod in product_effectiveness:
        weight = prod["score"] / total_score
        wa = WellnessAttribution(
            wellness_check_id=checkin.id,
            product_id=prod["product_id"],
            pain_pct=deltas["pain"] * weight,
            mood_pct=deltas["mood"] * weight,
            energy_pct=deltas["energy"] * weight,
            clarity_pct=deltas["clarity"] * weight,
            appetite_pct=deltas["appetite"] * weight,
        )
        # Derived overall contribution = sum of all attributes
        wa.derived_qol = sum([
            wa.pain_pct or 0,
            wa.mood_pct or 0,
            wa.energy_pct or 0,
            wa.clarity_pct or 0,
            wa.appetite_pct or 0,
        ])
        db.session.add(wa)

    db.session.commit()


# -------------------------------------------------------------------
# Weighted QoL per patient per product
# -------------------------------------------------------------------

def calculate_patient_product_qol(patient_id: int, product_id: int) -> float:
    """
    Calculates a weighted QoL contribution for a single patient on a single product.
    Uses WellnessAttribution records.
    """
    attribs = (
        WellnessAttribution.query
        .join('wellness_check')
        .filter(
            WellnessAttribution.product_id == product_id,
            WellnessAttribution.wellness_check.has(user_id=patient_id)
        )
        .all()
    )

    if not attribs:
        return 0.0

    total_qol = 0.0
    for a in attribs:
        # Sum of effectiveness contributions across all attributes
        effect_sum = sum([
            a.pain_pct or 0,
            a.mood_pct or 0,
            a.energy_pct or 0,
            a.clarity_pct or 0,
            a.appetite_pct or 0,
            a.sleep_pct or 0,
        ])
        if effect_sum <= 0:
            continue

        # Weighted contribution per attribute
        contrib = 0.0
        for pct in [a.pain_pct, a.mood_pct, a.energy_pct, a.clarity_pct, a.appetite_pct, a.sleep_pct]:
            if pct and pct > 0:
                contrib += pct / effect_sum * (a.overall_pct or 0)

        total_qol += contrib

    return total_qol

# -------------------------------------------------------------------
# Upvote / ProductAggregateScore helpers
# -------------------------------------------------------------------

def upsert_patient_product_vote(patient_id: int, product_id: int):
    """
    Insert or update the patient's single upvote for the product
    based on the weighted QoL.
    """
    weighted_qol = calculate_patient_product_qol(patient_id, product_id)
    if weighted_qol <= 0:
        return None  # Only positive QoL counts as an upvote

    upvote = Upvote.query.filter_by(
        user_id=patient_id,
        target_type="product",
        target_id=product_id
    ).first()

    if not upvote:
        upvote = Upvote(
            user_id=patient_id,
            target_type="product",
            target_id=product_id,
            qol_improvement=weighted_qol
        )
    else:
        upvote.qol_improvement = weighted_qol

    db.session.add(upvote)
    db.session.commit()

    # Update aggregate after each upsert
    return update_product_aggregate(product_id)

def update_product_aggregate(product_id: int) -> Optional[ProductAggregateScore]:
    """
    Updates ProductAggregateScore with current upvotes (QoL > 0).
    """
    stats = (
        db.session.query(
            func.count(Upvote.id),
            func.avg(Upvote.qol_improvement),
            func.min(Upvote.qol_improvement),
            func.max(Upvote.qol_improvement),
        )
        .filter(
            Upvote.target_type == "product",
            Upvote.target_id == product_id,
            Upvote.qol_improvement > 0
        )
        .first()
    )

    if not stats:
        return None

    total_votes, avg_qol, min_qol, max_qol = stats

    agg = ProductAggregateScore.query.filter_by(product_id=product_id).first()
    if not agg:
        agg = ProductAggregateScore(product_id=product_id)

    agg.total_votes = total_votes or 0
    agg.avg_qol = float(avg_qol) if avg_qol is not None else 0.0
    agg.min_qol = float(min_qol) if min_qol is not None else 0.0
    agg.max_qol = float(max_qol) if max_qol is not None else 0.0

    db.session.add(agg)
    db.session.commit()

    return agg

def get_product_score(product_id: int) -> Optional[ProductAggregateScore]:
    """
    Fetch aggregate score (refresh if missing).
    """
    agg = ProductAggregateScore.query.filter_by(product_id=product_id).first()
    if not agg:
        agg = update_product_aggregate(product_id)
    return agg

def get_product_vote_summary(product_id: int) -> Dict[str, float | int]:
    """
    Returns total votes and average QoL improvement (only positive).
    """
    agg = get_product_score(product_id)
    return {
        "total": agg.total_votes if agg else 0,
        "avg_qol": agg.avg_qol if agg else 0.0
    }


def calculate_qol_stats_for_product(session: Session, product_id: int) -> Optional[dict]:
    """
    Calculate aggregate QoL stats for a product from WellnessAttribution.
    Includes min, max, avg, weighted avg, counts.
    """

    attributions = (
        session.query(WellnessAttribution)
        .filter(WellnessAttribution.product_id == product_id)
        .all()
    )

    if not attributions:
        return None

    values = [a.overall_pct for a in attributions if a.overall_pct is not None]

    if not values:
        return None

    min_val = min(values)
    max_val = max(values)
    avg_val = sum(values) / len(values)

    # Weighted avg (by intensity)
    weighted_sum = sum(v * abs(v) for v in values)
    total_weight = sum(abs(v) for v in values)
    weighted_avg = weighted_sum / total_weight if total_weight > 0 else None

    # Counts
    total_votes = len(values)
    positive_votes = sum(1 for v in values if v > 0)
    negative_votes = sum(1 for v in values if v < 0)

    return {
        "min": min_val,
        "max": max_val,
        "avg": avg_val,
        "weighted_avg": weighted_avg,
        "total_votes": total_votes,
        "positive_votes": positive_votes,
        "negative_votes": negative_votes,
    }


