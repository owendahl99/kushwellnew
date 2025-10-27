
from __future__ import annotations
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user

from app.services.public_profile_service import build_public_profile

public_profiles_bp = Blueprint("public_profiles", __name__, url_prefix="/patients")

@public_profiles_bp.get("/<alias_slug>", endpoint="public_profile")
def public_profile(alias_slug: str):
    """
    Public, read-only patient profile (privacy-aware).
    Renders HTML for browsers and returns JSON if ?format=json is provided.
    """
    viewer = current_user if getattr(current_user, "is_authenticated", False) else None
    data, status = build_public_profile(viewer, alias_slug)
    if (request.args.get("format") or "").lower() == "json":
        return jsonify(data), status
    if status != 200:
        return render_template("public_profile.html", error=data.get("error","Not found"), payload=None), status
    return render_template("public_profile.html", error=None, payload=data)
