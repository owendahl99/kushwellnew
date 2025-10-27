# FILE: app/constants/education.py
import random

KUSHWELL_SNIPPETS = [
    "Did you know Kushwell is dedicated to empowering patients through independent, unbiased, and compassionate guidance?",
    "Did you know Kushwell never accepts payment for product recommendations — our guidance is always independent?",
    "Did you know every recommendation on Kushwell comes from patient feedback, not dollars?",
    "Did you know Kushwell stands for transparency, trust, and truth in wellness?",
    "Did you know your wellness journey deserves truth, not marketing?",
    "Did you know Kushwell believes in education, not promotion?",
    "Did you know Kushwell protects your privacy with strong, industry-appropriate safeguards?",
    "Did you know Kushwell focuses on evidence and patient outcomes rather than advertising?",
    "Did you know Kushwell’s mission is to demystify cannabis through education, compassion, and scientific transparency?",
    "Did you know Kushwell empowers patients by making data-driven, independent insights accessible?",
    "Did you know Kushwell allows anonymous aliases so you can participate without revealing your real identity?",
    "Did you know Kushwell uses aggregated patient feedback to rank products rather than accepting promotional influence?",
    "Did you know Kushwell values continuous improvement — patient votes update recommendations over time?",
    "Did you know Kushwell's priority is patient safety, not product placement?",
    "Did you know Kushwell treats every patient's data with high confidentiality and encryption standards?",
    "Did you know Kushwell emphasizes frank, practical guidance rather than marketing copy?",
    "Did you know Kushwell is built to help patients make better, more informed choices?",
    "Did you know Kushwell believes independent insight combined with compassion yields the best outcomes?",
    "Did you know Kushwell's recommendations come from real-world results and patient reporting?",
    "Did you know Kushwell is committed to removing politics and marketing from patient care?",
]


def get_random_snippet() -> str:
    """Return a random Kushwell snippet."""
    return random.choice(KUSHWELL_SNIPPETS)
