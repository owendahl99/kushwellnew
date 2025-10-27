# FILE: utilities/strain_utils.py
from app.constants.strains import STRAINS

def get_strain_data(strain_name: str):
    """Lookup strain info by name (case-insensitive)."""
    if not strain_name:
        return None
    strain_name = strain_name.strip().lower()
    for s in STRAINS:
        if s["name"].lower() == strain_name:
            return s
    return None
