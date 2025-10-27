"""
app/constants.py
----------------

Canonical constants and enumerations used across the Kushwell application.

This module provides stable reference data such as afflictions, terpene lists,
application methods, and enumerations for user roles and product statuses.
It ensures consistency between the backend, templates, and forms.
"""

from enum import Enum
from typing import Dict, List, Optional

# =========================================================
# === USER ROLES / PRODUCT STATUS ENUMS ===================
# =========================================================

class UserRoleEnum(str, Enum):
    ADMIN = "ADMIN"
    ENTERPRISE = "ENTERPRISE"
    PATIENT = "PATIENT"
    PROVIDER = "PROVIDER"
    SUPPLIER = "SUPPLIER"
    DISPENSARY = "DISPENSARY"


class ProductStatus(str, Enum):
    ENTERPRISE_PENDING  = "enterprise_pending"
    ENTERPRISE_APPROVED = "enterprise_approved"
    ENTERPRISE_REJECTED = "enterprise_rejected"
    GRASSROOTS_PENDING  = "grassroots_pending"
    GRASSROOTS_APPROVED = "grassroots_approved"
    GRASSROOTS_REJECTED = "grassroots_rejected"


class ModerationReason(str, Enum):
    PRODUCT_UNAVAILABLE = "product_unavailable"
    DUPLICATE_ENTRY = "duplicate_entry"
    NO_EVIDENCE_OF_BENEFIT = "no_evidence_of_benefit"
    PHISHING_SPAM = "phishing_spam"
    BULLYING_OR_HARASSMENT = "bullying_or_harassment"
    VIOLATES_TERMS = "violates_terms"
    MISLEADING_CLAIMS = "misleading_claims"
    INAPPROPRIATE_CONTENT = "inappropriate_content"


class SubmissionType(str, Enum):
    ENTERPRISE = "enterprise"
    GRASSROOTS = "grassroots"


# =========================================================
# === AFFLICTION LISTS & UTILITIES ========================
# =========================================================

AFFLICTION_LIST: List[str] = [
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
    "Crohn's Disease",
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

AFFLICTION_LEVELS: List[str] = ["I", "II", "III", "IV", "V"]


def get_afflictions() -> List[str]:
    return AFFLICTION_LIST


def get_levels() -> List[str]:
    return AFFLICTION_LEVELS


def normalize_afflictions(selected: Optional[List[str]], *, allow_free_text: bool = False) -> List[str]:
    if not selected:
        return []
    cleaned = [s.strip() for s in selected if s and s.strip()]
    if not cleaned:
        return []
    deduped = list(dict.fromkeys(cleaned))
    if allow_free_text:
        return deduped
    allowed = set(AFFLICTION_LIST)
    return [a for a in deduped if a in allowed]


def serialize_afflictions(items: Optional[List[str]]) -> Optional[str]:
    return ", ".join(items) if items else None


def parse_afflictions(s: Optional[str]) -> List[str]:
    return [p.strip() for p in s.split(",")] if s else []


def is_valid_level(level: Optional[str]) -> bool:
    return bool(level) and level in AFFLICTION_LEVELS


def level_to_int(level: str) -> int:
    return {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}.get(level, 0)


def int_to_level(n: int) -> Optional[str]:
    return {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}.get(int(n))


# =========================================================
# === APPLICATION METHODS =================================
# =========================================================

APPLICATION_METHODS = [
    "Smoking",
    "Vaping",
    "Edible",
    "Capsule/Pill",
    "Sublingual (Tincture/Oil)",
    "Topical (Non-ingestible)",
    "Transdermal Patch",
    "Beverage",
    "Other",
]

APPLICATION_METHOD_CHOICES = [
    ("smoking", "Smoking"),
    ("vaping", "Vaping"),
    ("edible", "Edible"),
    ("capsule_pill", "Capsule/Pill"),
    ("sublingual", "Sublingual (Tincture/Oil)"),
    ("topical", "Topical (Non-ingestible)"),
    ("transdermal_patch", "Transdermal Patch"),
    ("beverage", "Beverage"),
    ("other", "Other"),
]

def application_method_choices() -> List[tuple[str, str]]:
    return APPLICATION_METHOD_CHOICES
C

# =========================================================
# === TERPENE LISTS & UTILITIES ===========================
# =========================================================

# ---------------------------------------------------------
# Canonical terpene list (short form)
# ---------------------------------------------------------
TERPENES: List[str] = [
    "Myrcene",
    "Limonene",
    "Beta-Caryophyllene",
    "Alpha-Pinene",
    "Pinene",
    "Beta-Pinene",
    "Linalool",
    "Humulene",
    "Terpinolene",
    "Ocimene",
    "Bisabolol",
    "Nerolidol",
    "Eucalyptol",
    "Camphene",
    "Borneol",
    "Terpineol",
    "Valencene",
    "Geraniol",
    "Fenchol",
    "Sabinene",
    "Caryophyllene",
    "Delta-3-Caryophyllene",
    "Delta-8-Caryophyllene",
    "Pulegol",
    "Transnerol",
    "Phellandrene",
]

# ---------------------------------------------------------
# Extended descriptive traits for each terpene
# ---------------------------------------------------------
TERPENE_TRAITS: Dict[str, str] = {
    "Myrcene": "Often described as relaxing/sedating; commonly found in 'couch-lock' strains.",
    "Limonene": "Citrusy aroma; frequently associated with elevated mood and focus.",
    "Beta-Caryophyllene": "Peppery/spicy; interacts with CB2, often cited for soothing qualities.",
    "Alpha-Pinene": "Piney aroma; may support alertness and counteract grogginess.",
    "Pinene": "Piney aroma; may support alertness and counteract grogginess.",
    "Beta-Pinene": "Piney aroma; may support alertness and counteract grogginess.",
    "Linalool": "Floral, lavender; commonly linked with calm and stress relief.",
    "Humulene": "Earthy/woodsy; historically associated with balance and appetite control.",
    "Terpinolene": "Fresh/herbal; some users report uplifting, creative effects.",
    "Ocimene": "Sweet/herbal; sometimes noted for bright or energizing qualities.",
    "Bisabolol": "Woody/floral; often mentioned in the context of relaxation and sleep.",
    "Nerolidol": "Woody/floral; often mentioned in the context of relaxation and sleep.",
    "Eucalyptol": "Sagey; antibacterial and antifungal; potential benefits in Alzheimer's.",
    "Camphene": "Sagey; may provide calming effects.",
    "Borneol": "Minty; used to reduce pain and inflammation and treat respiratory issues.",
    "Terpineol": "Shown to act as a depressant on the central nervous system; potential for anxiety treatment.",
    "Valencene": "Fruity; associated with positive mood and alertness.",
    "Geraniol": "Floral; often associated with relaxation and sleep.",
    "Fenchol": "Sagey; may provide calming effects.",
    "Sabinene": "Piney aroma; offers antioxidant properties.",
    "Caryophyllene": "Aromatic; may provide calming or soothing effects.",
    "Delta-3-Caryophyllene": "Aids in healing broken bones; may benefit Alzheimer's.",
    "Delta-8-Caryophyllene": "Aromatic; may provide calming effects.",
    "Pulegol": "May provide pain relief and reduce temperature; insect repellent.",
    "Transnerol": "Provides antiparasitic properties.",
    "Phellandrene": "Sagey; may provide calming effects.",
}

# ---------------------------------------------------------
# Searchable characteristic keywords (used for characteristics search)
# ---------------------------------------------------------
TERPENE_CHARACTERISTICS: Dict[str, List[str]] = {
    "Myrcene": ["relaxing", "sedative", "musky", "earthy", "calming"],
    "Limonene": ["uplifting", "energetic", "citrus", "anti-anxiety"],
    "Pinene": ["alertness", "focus", "pine", "respiratory", "anti-inflammatory"],
    "Linalool": ["relaxation", "stress relief", "floral", "sleep aid"],
    "Caryophyllene": ["peppery", "anti-inflammatory", "spicy", "pain relief"],
    "Humulene": ["earthy", "woody", "appetite suppressant", "focus"],
    "Terpinolene": ["fresh", "herbal", "creative", "mood boosting"],
    "Ocimene": ["sweet", "uplifting", "antiviral", "energizing"],
}

# ---------------------------------------------------------
# Utility accessors
# ---------------------------------------------------------
def get_terpenes() -> List[str]:
    """Return list of canonical terpene names."""
    return TERPENES


def get_terpene_traits() -> Dict[str, str]:
    """Return descriptive mapping for terpene traits."""
    return TERPENE_TRAITS


def get_terpene_trait(name: str) -> str:
    """Return descriptive trait for a given terpene name."""
    return TERPENE_TRAITS.get(name, "No description available.")


def get_terpene_characteristics(name: str) -> List[str]:
    """Return keyword-based characteristics for a terpene (used in xcharacteristics search)."""
    return TERPENE_CHARACTERISTICS.get(name, [])

# ============================================
# Kushwell Mission, Ethics, and Tagline Snippets
# Used for banners, footers, modals, and random display
# ============================================

KUSHWELL_SNIPPETS = [
    # --- Core Mission Statement ---
    "Kushwell is dedicated to empowering patients through independent, unbiased, and compassionate guidance on their journey toward improved wellness. We believe in education, not promotion — providing a safe, nurturing community where knowledge, data, and experience come together to demystify cannabis and support informed personal health decisions. Our commitment to privacy and security is unwavering, with systems built to exceed HIPAA standards and protect every patient’s trust.",

    # --- Ethics & Care Snippets ---
    "Kushwell Cares. Always has, always will.",
    "Think of Kushwell as your roadmap to better health.",                                                                                                                  
    "Kushwell Care: AI with empathy.",
    "We never accept payment for product placement, review, or promotion.",
    "Every recommendation comes from patient feedback, not dollars.",
    "Independent. Unbiased. Forever.",
    "Your wellness journey deserves truth, not marketing.",
    "Kushwell stands for transparency, trust, and truth in wellness.",
    "Data in, insight out — that’s the Kushwell promise.",
    "Patients dictate the products. Not advertisers.",
    "Our AI analyzes outcomes, not sales claims.",
    "Healthier decisions start with honest data.",
    "Kushwell exists to remove politics and marketing influence.",
    "Real data. Real people. Real results.",
    "Recommendations are built on science, not profit.",
    "You can operate anonymously via an alias at all times.",
    "Aliases and real identities are never linked without consent.",
    "No one using the platform can discover your real identity unless you choose.",
    "Your data is encrypted in transit and at rest.",
    "Our HIPAA compliance protects your health information to the highest standards.",
    "Kushwell Care: guidance, not marketing.",
    "Independence ensures unbiased insight.",
    "Trust is earned, one data point at a time.",
    "Compassion through computation.",
    "Your feedback shapes the results. Nothing else does.",
    "Evidence, not advertising. Always.",
    "Built for patients, by patients.",
    "Every insight is earned through data, not dollars.",
    "We do not sell products, nor are we affiliated with those who do.",
    "Our mission: empower informed, compassionate decisions.",
    "Science, math, and patient insight replace politics.",
    "Transparency is our foundation.",
    "Kushwell ensures confidentiality beyond many hospital systems.",
    "Our recommendations are continuously updated based on patient input.",
    "Patient votes determine product ranking.",
    "Grassroots contributions help maintain a robust product catalog.",
    "We will never accept payment for product suggestions.",
    "Healthier living starts with unbiased information.",
    "Our promise: zero bias, zero influence, total transparency.",
    "Independent insight, built on compassion.",
    "Kushwell: evidence over opinion, always.",
    "Guidance, not promotion.",
    "Our purpose is to help you make better, informed choices.",
    "Patient anonymity and confidentiality are preserved at all times.",
    "We take the politics out and put the math in.",

    # --- Micro Taglines (15 Total) ---
    "Independent insight. Compassionate care. Patient trust.",
    "Guiding your wellness journey with knowledge, not promotion.",
    "Unbiased data, compassionate purpose — that’s the Kushwell way.",
    "Empowering better health decisions through truth and transparency.",
    "Where education, privacy, and care come together.",
    "Kushwell — built on integrity, powered by compassion, protected by design.",
    "No ads. No bias. Just honest information.",
    "We protect your privacy as fiercely as your trust.",
    "Because better health begins with better understanding.",
    "Your data stays yours — always encrypted, always private.",
    "Compassion meets computation at Kushwell.",
    "For patients, by patients — never for profit.",
    "Where science replaces sales and insight replaces influence.",
    "Education. Integrity. Empowerment. The Kushwell foundation.",
    "Helping you navigate wellness with clarity, care, and confidence."
]
