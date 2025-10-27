# FILE: app/routes/typeahead.py
from flask import Blueprint, request, jsonify, current_app
from app.models import Product, GrassrootsProduct, Dispensary
from app.constants.general_menus import AFFLICTION_LIST
from app.constants.product_constants import STRAINS, TERPENE_CHARACTERISTICS, TERPENES
from sqlalchemy import or_

typeahead_bp = Blueprint("typeahead", __name__, template_folder="../templates")

# In-memory cache for repeated queries
CACHE = {}

@typeahead_bp.route("/search", methods=["GET"])
def search():
    """
    Typeahead search endpoint.
    Query params:
      - q: search string
      - type: "product" | "brand" | "affliction" | "terpene" | "characteristics" | "dispensary" | "strain"
    """
    q = (request.args.get("q") or "").strip()
    search_type = (request.args.get("type") or "product").lower()

    if not q:
        return jsonify({"results": []})

    cache_key = f"{search_type}:{q.lower()}"
    if cache_key in CACHE:
        return jsonify({"results": CACHE[cache_key]})

    results = []

    # ----------------------
    # PRODUCT SEARCH
    # ----------------------
    if search_type == "product":
        products = Product.query.filter(Product.name.ilike(f"%{q}%")).limit(10).all()
        grassroots = GrassrootsProduct.query.filter(GrassrootsProduct.name.ilike(f"%{q}%")).limit(10).all()
        seen = set()
        for p in products + grassroots:
            name = getattr(p, "name", "")
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            results.append({
                "id": getattr(p, "id", None),
                "name": name,
                "category": getattr(p, "category", ""),
                "type": "enterprise" if "Product" in p.__class__.__name__ else "grassroots",
            })

    # ----------------------
    # BRAND SEARCH
    # ----------------------
    elif search_type == "brand":
        db_brands = [p.brand_name for p in Product.query.with_entities(Product.brand_name).distinct() if p.brand_name]
        grassroots_brands = [g.brand_name for g in GrassrootsProduct.query.with_entities(GrassrootsProduct.brand_name).distinct() if g.brand_name]
        dict_brands = current_app.config.get("DICT_BRANDS", [])

        combined_brands = list(dict.fromkeys(db_brands + grassroots_brands + dict_brands))
        results = [{"name": b} for b in combined_brands if q.lower() in b.lower()][:15]

    # ----------------------
    # AFFLICTION SEARCH
    # ----------------------
    elif search_type == "affliction":
        results = [{"name": a} for a in AFFLICTION_LIST if q.lower() in a.lower()][:15]

    # ----------------------
    # STRAIN SEARCH
    # ----------------------
    elif search_type == "strain":
        results = [{"name": s["name"]} for s in STRAINS if q.lower() in s["name"].lower()][:10]

    # ----------------------
    # TERPENE SEARCH
    # ----------------------
    elif search_type == "terpene":
        results = [{"name": t} for t in TERPENES.keys() if q.lower() in t.lower()][:10]

    # ----------------------
    # CHARACTERISTICS SEARCH
    # ----------------------
    elif search_type == "characteristics":
        matched_terpenes = {}
        for terpene, traits in TERPENE_CHARACTERISTICS.items():
            for trait in traits:
                if q.lower() in trait.lower():
                    matched_terpenes[terpene] = TERPENES.get(terpene, "")
                    break
        if matched_terpenes:
            matched_products = Product.query.filter(
                or_(*[Product.terpenes.ilike(f"%{t}%") for t in matched_terpenes])
            ).limit(20).all()
            for p in matched_products:
                product_terpenes = getattr(p, "terpenes", "").split(",")
                product_matched = {t: trait for t, trait in matched_terpenes.items() if t in product_terpenes}
                results.append({
                    "id": getattr(p, "id", None),
                    "name": getattr(p, "name", ""),
                    "category": getattr(p, "category", ""),
                    "terpenes": getattr(p, "terpenes", ""),
                    "matched_terpenes": product_matched,
                })

    # ----------------------
    # DISPENSARY SEARCH
    # ----------------------
    elif search_type == "dispensary":
        dispensaries = Dispensary.query.filter(Dispensary.name.ilike(f"%{q}%")).limit(10).all()
        for d in dispensaries:
            results.append({
                "id": getattr(d, "id", None),
                "name": getattr(d, "name", ""),
                "location": getattr(d, "location", ""),
            })

    # ----------------------
    # CACHE & RETURN
    # ----------------------
    CACHE[cache_key] = results
    return jsonify({"results": results})
