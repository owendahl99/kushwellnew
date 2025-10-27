# FILE: app/utils/wellness_feedback.py

def generate_feedback(current_sliders: dict, last_sliders: dict) -> dict:
    """
    Generate overall QOL score, percentage changes, 
    and empathetic paragraph based on current vs last sliders.

    current_sliders & last_sliders: {'sleep':6, 'energy':5, 'appetite':4, ...}
    """
    feedback = {}
    total_current = sum([v for v in current_sliders.values() if v is not None])
    total_last = sum([v for v in last_sliders.values() if v is not None])

    feedback['overall_change'] = None
    if total_last:
        feedback['overall_change'] = round((total_current - total_last) / total_last * 100, 1)
    else:
        feedback['overall_change'] = 0

    # Build individual slider comparisons
    slider_diff = {}
    for key in current_sliders:
        curr = current_sliders.get(key)
        prev = last_sliders.get(key)
        if prev is not None and curr is not None:
            pct_change = (curr - prev) / prev * 100 if prev else 0
            slider_diff[key] = round(pct_change, 1)
        else:
            slider_diff[key] = None
    feedback['slider_diff'] = slider_diff

    # Build empathetic paragraph
    paragraphs = []

    if feedback['overall_change'] > 0:
        paragraphs.append(f"Great job! Your overall QOL has improved by {feedback['overall_change']}% since your last check-in.")
    elif feedback['overall_change'] < 0:
        paragraphs.append(f"We're sorry to see your overall QOL has decreased by {abs(feedback['overall_change'])}%. Let's see what can help you improve.")
    else:
        paragraphs.append("Your overall QOL looks stable compared to your last check-in. Keep monitoring your trends!")

    # Highlight significant slider changes (>5% change)
    highlights = []
    for k, v in slider_diff.items():
        if v is not None:
            if v > 5:
                highlights.append(f"{k.capitalize()} has improved by {v}%")
            elif v < -5:
                highlights.append(f"{k.capitalize()} has decreased by {abs(v)}%")
    if highlights:
        paragraphs.append("Highlights: " + "; ".join(highlights) + ".")

    # Optional product recommendations placeholder
    paragraphs.append("Based on your changes, here are some product recommendations to consider:")

    feedback['paragraph'] = " ".join(paragraphs)
    return feedback


