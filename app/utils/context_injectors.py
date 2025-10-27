# FILE: app/utilities/context_injectors.py
# ---------------------------------------------------------
# Centralized context injector with caching for Flask templates.
# Exposes constants, enums, product data, factoids, and Kushwell snippets globally.
# ==========================================================
import os
import re
import json
import random
from datetime import datetime, timedelta
from flask import current_app
from app.models import Product, GrassrootsProduct

# -------------------------------
# Explicit imports from constants
# -------------------------------
from app.constants.education import KUSHWELL_SNIPPETS, get_random_snippet
from app.constants.general_menus import (
    AFFLICTION_LIST,
    AFFLICTION_LEVELS,
    SUPPORT_GROUPS,
    UserRoleEnum,
)
from app.constants.product_constants import (
    APPLICATION_METHODS,
    TERPENES,
    TERPENE_TRAITS,
    TERPENE_CHARACTERISTICS,
    STRAINS,
)

# ------------------------------
# IMPORT FALLBACK LIBRARIES
# -------------------------------
def _load_products_brands_js():
    """Read the JS library file and parse brands/products."""
    js_path = os.path.join(os.path.dirname(__file__), "..", "static", "js", "products_brands.js")
    try:
        with open(js_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Extract JSON-like object
        match = re.search(r"const PRODUCT_BRAND_LIBRARY\s*=\s*(\{.*\});", content, re.DOTALL)
        if not match:
            return [], []
        data_str = match.group(1)
        # Replace single-line comments and trailing commas (if any)
        data_str = re.sub(r"//.*", "", data_str)
        data_str = re.sub(r",\s*]", "]", data_str)
        data_str = re.sub(r",\s*}", "}", data_str)
        data = json.loads(data_str)
        return data.get("brands", []), data.get("products", [])
    except Exception:
        return [], []
    
# -------------------------------
# Cache setup
# -------------------------------
_cache = {
    "last_updated": None,
    "products": [],
    "all_products": [],
    "factoids": [],
    "constants": {},
}
_CACHE_TTL = timedelta(minutes=5)

# Full strain data (for analytics, rich cards, etc.)
_cache["strains"] = STRAINS

# Name-only list (for dropdowns, typeaheads, form fields)
_cache["strain_names"] = [s["name"] for s in STRAINS]

# -------------------------------
# Load factoids from JSON
# -------------------------------
FACTOIDS_JSON_PATH = "app/static/data/factoids.json"


def _load_factoids():
    if _cache["factoids"]:
        return _cache["factoids"]
    try:
        with open(FACTOIDS_JSON_PATH, "r", encoding="utf-8") as f:
            factoids = json.load(f)
        _cache["factoids"] = factoids
        return factoids
    except Exception as e:
        current_app.logger.warning(f"[context_injectors] Could not load factoids: {e}")
        return []


def choose_random_factoid():
    """Return a random factoid from loaded factoids."""
    factoids = _load_factoids()
    if not factoids:
        return None
    return random.choice(factoids)


# -------------------------------
# Master injector function
# -------------------------------
def inject_master_globals():
    """Injects master constants + product references + factoids into templates."""
    now = datetime.utcnow()

    # Cached version check
    if _cache["last_updated"] and now - _cache["last_updated"] < _CACHE_TTL:
        return {
            **_cache["constants"],
            "PRODUCTS": _cache["products"],
            "ALL_PRODUCTS": _cache["all_products"],
            "ALL_BRANDS": _cache["all_brands"],
            "ALL_PRODUCTS_NAMES": _cache["all_products_names"],
            "KUSHWELL_SNIPPET": get_random_snippet(),
            "FACTOID": choose_random_factoid(),
        }

    # ---------------------------------------------------------
    # Load all products from DB
    # ---------------------------------------------------------
    PRODUCTS, ALL_PRODUCTS = [], []
    try:
        ep = Product.query.all() if hasattr(Product, "query") else []
        gp = GrassrootsProduct.query.all() if hasattr(GrassrootsProduct, "query") else []
        ALL_PRODUCTS = list(ep) + list(gp)

        for p in ALL_PRODUCTS:
            PRODUCTS.append({
                "id": getattr(p, "id", None),
                "name": getattr(p, "product_name", ""),   # ✅ FIXED FIELD NAME
                "brand": getattr(p, "brand", ""),         # ✅ INCLUDE BRAND FIELD
                "manufacturer": getattr(p, "manufacturer", ""),  # ✅ INCLUDE MANUFACTURER
                "category": getattr(p, "category", ""),
                "image_path": getattr(p, "image_path", ""),
                "submission_type": getattr(p, "submission_type", "grassroots")
                    if hasattr(p, "submission_type")
                    else ("grassroots" if "grassroot" in p.__class__.__name__.lower() else "enterprise"),
            })
    except Exception as e:
        current_app.logger.warning(f"[context_injectors] Could not load products: {e}")
        PRODUCTS, ALL_PRODUCTS = [], []

    # ---------------------------------------------------------
    # Load JS fallback & merge
    # ---------------------------------------------------------
    js_brands, js_products = _load_products_brands_js()

    try:
        db_brands = sorted({p["brand"] for p in PRODUCTS if p["brand"]})
        db_products = sorted({p["name"] for p in PRODUCTS if p["name"]})
    except Exception:
        db_brands, db_products = [], []

    # Merge DB first, then JS fallback
    merged_brands = sorted(set(db_brands + [b for b in js_brands if b not in db_brands]))
    merged_products = sorted(set(db_products + [p for p in js_products if p not in db_products]))

    # ---------------------------------------------------------
    # Update cache cleanly
    # ---------------------------------------------------------
    _cache.update({
        "last_updated": now,
        "products": PRODUCTS,
        "all_products": ALL_PRODUCTS,
        "all_brands": merged_brands,
        "all_products_names": merged_products,
        "constants": {
            "AFFLICTION_LIST": AFFLICTION_LIST,
            "AFFLICTION_LEVELS": AFFLICTION_LEVELS,
            "AFFLICTIONS": AFFLICTION_LIST,
            "ROMAN_SCALE": AFFLICTION_LEVELS,
            "SUPPORT_GROUPS": SUPPORT_GROUPS,
            "APPLICATION_METHODS": APPLICATION_METHODS,
            "TERPENES": TERPENES,
            "TERPENE_TRAITS": TERPENE_TRAITS,
            "TERPENE_CHARACTERISTICS": TERPENE_CHARACTERISTICS,
            "STRAINS": STRAINS,
            "STRAIN_NAMES": [s["name"] for s in STRAINS],
            "UserRoleEnum": UserRoleEnum,
        },
    })

    # ---------------------------------------------------------
    # Return global context
    # ---------------------------------------------------------
    return {
        **_cache["constants"],
        "PRODUCTS": PRODUCTS,
        "ALL_PRODUCTS": ALL_PRODUCTS,
        "ALL_BRANDS": merged_brands,
        "ALL_PRODUCTS_NAMES": merged_products,
        "KUSHWELL_SNIPPET": get_random_snippet(),
        "FACTOID": choose_random_factoid(),
    }
