# FILE: app/utils/ai_wellness.py
from typing import List, Dict, Optional, Tuple
from uuid import UUID

def calculate_percentage_change(current, previous) -> Optional[float]:
    """Safe percentage change calculation for numeric values only."""
    try:
        if previous is None or current is None:
            return None
        # Only calculate for numeric types
        if isinstance(current, (int, float)) and isinstance(previous, (int, float)):
            if previous == 0:
                return None
            return ((current - previous) / previous) * 100
        return None
    except Exception:
        return None

def compare_sliders(current_checkin: Dict, last_checkin: Optional[Dict]) -> List[Dict]:
    """Compare sliders between two check-ins."""
    slider_keys = ["sleep", "energy", "appetite", "pain", "mood", "clarity"]
    comparisons = []

    for key in slider_keys:
        curr_val = getattr(current_checkin, key, None) if not isinstance(current_checkin, dict) else current_checkin.get(key)
        prev_val = getattr(last_checkin, key, None) if last_checkin and not isinstance(last_checkin, dict) else (last_checkin.get(key) if last_checkin else None)
        pct_change = calculate_percentage_change(curr_val, prev_val)
        comparisons.append({
            "slider": key,
            "current": curr_val,
            "previous": prev_val,
            "pct_change": pct_change
        })
    return comparisons

# FILE: app/utils/ai_wellness.py

def allocate_product_attribution(sliders_comparison, product_usage):
    """
    Allocate attribution scores to products based on positive changes in sliders.
    
    Args:
        sliders_comparison (list[dict]): Each dict should have a "pct_change" key.
        product_usage (list[dict]): Products the patient is using.
    
    Returns:
        list[dict]: Products with attribution scores.
    """
    recommendations = []

    # Calculate a total "improvement score" from sliders
    total_score = 0
    for s in sliders_comparison:
        val = s.get("pct_change")
        if val is None:
            val = 0
        try:
            val = float(val)  # ensure it's numeric
        except (TypeError, ValueError):
            val = 0
        if val > 0:
            total_score += val

    # Assign proportional attribution to each product
    for p in product_usage:
        # Example: distribute evenly if total_score is 0
        attribution = (total_score / len(product_usage)) if total_score > 0 else 0
        recommendations.append({
            "product": p,
            "attribution_score": attribution
        })

    return recommendations


def generate_ai_feedback(sliders_comparison: List[Dict], product_recommendations: List[Dict]) -> str:
    """
    Generate context-based AI-style encouragement and analysis.
    This is the paragraph that can be displayed in the patient dashboard.
    """
    messages = []
    for s in sliders_comparison:
        pct = s.get("pct_change")
        if pct is None:
            continue
        if pct > 5:
            messages.append(f"Your {s['slider']} has improved by {pct:.1f}% — nice progress!")
        elif pct < -5:
            messages.append(f"Your {s['slider']} has decreased by {abs(pct):.1f}%. Consider reviewing your routine.")
    # Add top product recommendation
    if product_recommendations:
        top_product = product_recommendations[0]
        messages.append(f"Try incorporating {top_product['name']} — it might help with your wellness goals.")
    return " ".join(messages) or "Keep tracking your wellness — every check-in counts!"

def get_ai_wellness_report(current_checkin, last_checkin, product_usage: List[Dict], all_checkins: List = []) -> Tuple[List[Dict], List[Dict], str]:
    """
    Full AI-enhanced wellness report.
    
    Returns:
        sliders_comparison, recommended_products, ai_feedback
    """
    sliders_comparison = compare_sliders(current_checkin, last_checkin)
    recommended_products = allocate_product_attribution(sliders_comparison, product_usage)
    ai_feedback = generate_ai_feedback(sliders_comparison, recommended_products)

    return sliders_comparison, recommended_products, ai_feedback


