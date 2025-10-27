# app/utilities/geo.py
import pgeocode
from geopy.distance import geodesic

nomi = pgeocode.Nominatim("us")


def zip_to_coords(zipcode: str):
    """Convert a US zipcode into (lat, lon). Returns None if lookup fails."""
    if not zipcode:
        return None
    info = nomi.query_postal_code(zipcode)
    if info is None or info.latitude is None:
        return None
    return (info.latitude, info.longitude)


def get_entity_coords(entity):
    """
    Return (lat, lon) for an object that has latitude/longitude or zipcode.
    Works for Dispensary, PatientProfile, etc.
    """
    if getattr(entity, "latitude", None) and getattr(entity, "longitude", None):
        return (entity.latitude, entity.longitude)
    if hasattr(entity, "zip_code"):
        return zip_to_coords(entity.zip_code)
    return None


def distance_miles(a, b):
    """Return distance in miles between two (lat, lon) tuples."""
    if not a or not b:
        return None
    return geodesic(a, b).miles


