# FILE: app/utilities/factoid_loader.py
# Utility to load Kushwell factoids JSON (safe, cached, tolerant).

import json
import os
import random
from flask import current_app

DEFAULT_PATHS = [
    os.path.join("static", "data", "factoids.json"),
    os.path.join("static", "data", "kushwell_factoids_001-040.json"),
    os.path.join("static", "data", "research_facts.json"),
]

def _resolve_path():
    """Return the first existing path (relative to current_app.root_path) or None."""
    for p in DEFAULT_PATHS:
        full = os.path.join(current_app.root_path, p)
        if os.path.exists(full):
            return full
    return None

def load_factoids():
    """
    Loads factoids from JSON. Returns list of dicts.
    Falls back to [] and logs a warning if file missing or unreadable.
    """
    try:
        path = _resolve_path()
        if not path:
            current_app.logger.warning("[factoid_loader] no factoids file found in static/data/")
            return []
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            # Basic validation / normalization
            out = []
            for i, item in enumerate(data or []):
                # ensure keys exist and set defaults
                it = {
                    "id": item.get("id") or f"fact{(i+1):03}",
                    "name": item.get("name") or "",
                    "text": item.get("text") or item.get("fact") or "",
                    "source": item.get("source") or item.get("source_url") or "",
                    "popup": bool(item.get("popup", True)),
                    "category": item.get("category") or "Uncategorized",
                    "raw": item,  # keep original in case
                }
                out.append(it)
            return out
    except Exception as e:
        current_app.logger.exception(f"[factoid_loader] failed to load factoids: {e}")
        return []

def choose_random(factoids):
    """Return a random factoid dict or None."""
    if not factoids:
        return None
    return random.choice(factoids)
