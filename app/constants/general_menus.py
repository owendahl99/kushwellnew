# FILE: app/constants/general_menus.py
from enum import Enum
from typing import List, Optional

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
# === AFFLICTION LISTS & SUPPORT GROUPS ===================
# =========================================================

AFFLICTION_LIST: List[str] = [
    "Parkinson's Disease", "Alzheimer's Disease", "Chronic Pain", "Epilepsy",
    "Multiple Sclerosis", "PTSD", "Depression", "Anxiety", "Insomnia",
    "Cancer-related symptoms", "Inflammation", "Glaucoma", "Crohn's Disease",
    "Autism Spectrum Disorder", "Arthritis", "Appetite Loss", "Seizures",
    "Muscle Spasms", "Menstrual Pain", "Migraines", "Nausea", "Fibromyalgia",
    "TBI (Traumatic Brain Injury)", "Chemotherapy Side Effects", "IBS / IBD",
    "Lupus", "Autoimmune Disorders", "Chronic Fatigue Syndrome", "Asthma",
    "Chronic Kidney Disease", "Hypothyroidism", "COPD", "Heart Disease",
    "Diabetes", "Hypertension", "Thyroid Disease", "Cancer", "Psoriasis",
    "Eczema", "Cachexia", "HIV/AIDS", "Persistent Muscle Spasms",
    "Lou Gehrig's Disease (ALS)", "CTE", "Hepatitis C", "Sickle Cell Disease",
    "Tourette's Syndrome", "Ulcerative Colitis", "OCD", "Huntington's Disease",
    "Intractable Spasticity", "Post-Surgical Pain", "Restless Leg Syndrome",
    "Opioid Use Disorder", "Neuropathy", "Neurodegeneration", "Cognitive Decline",
    "Sleep Apnea", "Chronic Sinusitis", "General Wellness", "Other Conditions"
]

AFFLICTION_LEVELS: List[str] = ["I", "II", "III", "IV", "V"]

SUPPORT_GROUPS = [
    "Neurological Disorders",
    "Chronic Pain & Inflammation",
    "Mental Health & PTSD",
    "Autoimmune & Inflammatory",
    "Sleep & Fatigue",
    "Cancer & Oncology Support",
    "Women’s Health",
    "General Wellness",
]
