# app/constants/afflictions.py

AFFLICTION_LIST: list[str] = [
    "Parkinson's Disease",
    "Alzheimer's Disease",
    "Chronic Pain",
    "Epilepsy",
    "Multiple Sclerosis",
    "PTSD",
    "Depression",
    "Anxiety",
    "Insomnia",
    "Cancer-related symptoms",
    "Inflammation",
    "Glaucoma",
    "Crohn's Disease",  # <-- fix mojibake
    "Autism Spectrum Disorder",
    "Arthritis",
    "Appetite Loss",
    "Seizures",
    "Muscle Spasms",
    "Menstrual Pain",
    "Migraines",
    "Nausea",
    "Fibromyalgia",
    "TBI (Traumatic Brain Injury)",
    "Chemotherapy Side Effects",
    "IBS / IBD",
    "Lupus",
    "Autoimmune Disorders",
    "Chronic Fatigue Syndrome",
    "Asthma",
    "Chronic Kidney Disease",
    "Hypothyroidism",
    "COPD",
    "Heart Disease",
    "Diabetes",
    "Hypertension",
    "Thyroid Disease",
    "Cancer",
    "Psoriasis",
    "Eczema",
    "Cachexia",
    "HIV/AIDS",
    "Persistent Muscle Spasms",
    "Lou Gehrig's Disease (ALS)",
    "Chronic Traumatic Encephalopathy (CTE)",
    "Hepatitis C",
    "Sickle Cell Disease",
    "Tourette's Syndrome",
    "Ulcerative Colitis",
    "General Anxiety Disorder",
    "Obsessive-Compulsive Disorder (OCD)",
    "Huntington's Disease",
    "Intractable Spasticity",
    "Post-Surgical Pain",
    "Restless Leg Syndrome",
    "Opioid Use Disorder",
    "Neuropathy",
    "Neurodegeneration",
    "Cognitive Decline",
    "Sleep Apnea",
    "Chronic Sinusitis",
    "General Wellness",
    "Other Conditions",
]

AFFLICTION_LEVELS: list[str] = ["I", "II", "III", "IV", "V"]

def get_afflictions() -> list[str]:
    return AFFLICTION_LIST

def get_levels() -> list[str]:
    return AFFLICTION_LEVELS

def normalize_afflictions(selected: list[str] | None, *, allow_free_text: bool = False) -> list[str]:
    if not selected: return []
    cleaned = [s.strip() for s in selected if s and s.strip()]
    if not cleaned: return []
    deduped = list(dict.fromkeys(cleaned))
    if allow_free_text: return deduped
    allowed = set(AFFLICTION_LIST)
    return [a for a in deduped if a in allowed]

def serialize_afflictions(items: list[str] | None) -> str | None:
    return ", ".join(items) if items else None

def parse_afflictions(s: str | None) -> list[str]:
    return [p.strip() for p in s.split(",")] if s else []

def is_valid_level(level: str | None) -> bool:
    return bool(level) and level in AFFLICTION_LEVELS

def level_to_int(level: str) -> int:
    return {"I":1,"II":2,"III":3,"IV":4,"V":5}.get(level, 0)

def int_to_level(n: int) -> str | None:
    return {1:"I",2:"II",3:"III",4:"IV",5:"V"}.get(int(n))


