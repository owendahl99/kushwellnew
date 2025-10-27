# app/routes/profiles.py
profiles_bp = Blueprint("profiles", __name__, url_prefix="/p")

@profiles_bp.get("/<int:user_id>", endpoint="view")
def view_profile(user_id: int):
    # Use the bundle-builder you already have (can_view/effective_display_name)
    return profile_view(user_id)  # reuse logic we wrote earlier


