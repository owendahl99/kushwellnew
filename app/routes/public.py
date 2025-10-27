# app/routes/public.py
from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, current_app
from flask_login import current_user
from app.constants.enums import UserRoleEnum

# routes/public.py
from flask import Blueprint, redirect, url_for

public_bp = Blueprint("public", __name__)

@public_bp.get("/patient", endpoint="patient")
def patient_legacy():
    # send visitors to the patient registration funnel (or login if register is absent)
    if "auth.register" in current_app.view_functions:
        return redirect(url_for("auth.register", role="patient"))
    if "auth.login" in current_app.view_functions:
        return redirect(url_for("auth.login"))
    return redirect(url_for("public.landing"))


@public_bp.get("/our-story", endpoint="our_story")
def our_story():
    # Render page if you have a template, otherwise fall back gracefully
    try:
        return render_template("public/our_story.html")
    except TemplateNotFound:
        if "public.start" in current_app.view_functions:
            return redirect(url_for("public.start"))
        if "public.landing" in current_app.view_functions:
            return redirect(url_for("public.landing"))
        return redirect("/")

# routes/public.py  (add near the top if not present)
from jinja2 import TemplateNotFound
from flask import current_app, redirect, render_template, url_for

def _has_endpoint(name: str) -> bool:
    return name in current_app.view_functions

@public_bp.app_template_global("choose_url")
def choose_url(*candidates: str) -> str:
    """
    Return the first available endpoint's URL from the candidates list.
    Falls back to '/' if none exist. Use in templates to avoid BuildError.
    """
    for ep in candidates:
        if _has_endpoint(ep):
            try:
                return url_for(ep)
            except Exception:
                pass
    # fallbacks
    for ep in ("public.start", "public.landing"):
        if _has_endpoint(ep):
            return url_for(ep)
    return "/"

# --- Legacy shims (so old template links keep working) ---

def _has_endpoint(name: str) -> bool:
    return name in current_app.view_functions

def _safe_redirect(ep: str, **values):
    if _has_endpoint(ep):
        try:
            return redirect(url_for(ep, **values))
        except Exception:
            pass
    # last-resort fallback: render landing
    return render_template("public/landing.html")

def _role_home():
    """Pick a post-login home based on role & what exists."""
    role = getattr(current_user, "role", None)
    try:
        role = UserRoleEnum(role) if not isinstance(role, UserRoleEnum) else role
    except Exception:
        role = None

    if role == UserRoleEnum.ADMIN:
        for ep in ("admin.dashboard",):
            if _has_endpoint(ep):
                return url_for(ep)

    if role == UserRoleEnum.ENTERPRISE:
        for ep in ("enterprise.enterprise_dashboard", "enterprise.dashboard", "enterprise.home"):
            if _has_endpoint(ep):
                return url_for(ep)

    if role == UserRoleEnum.PATIENT:
        for ep in ("patient.dashboard", "patient.home"):
            if _has_endpoint(ep):
                return url_for(ep)

    # Supplier/provider/dispensary—treat like enterprise when available
    for ep in ("enterprise.enterprise_dashboard", "enterprise.dashboard"):
        if _has_endpoint(ep):
            return url_for(ep)

    # Fallback: login
    return url_for("auth.login") if _has_endpoint("auth.login") else "/auth/login"

@public_bp.get("/", endpoint="landing")
def landing():
    """
    Guests: render public landing.
    Authenticated: send to role-appropriate home (NEVER redirect to "/").
    """
    if current_user.is_authenticated:
        return redirect(_role_home())
    return render_template("public/landing.html")

# Optional helper to deep-link guests to login or users to home.
@public_bp.get("/start", endpoint="start")
def start():
    if current_user.is_authenticated:
        return redirect(_role_home())
    return redirect(url_for("auth.login"))

# Keep any additional public pages you already use:
@public_bp.get("/enterprise", endpoint="enterprise")
def enterprise_page():
    return render_template("public/enterprise.html")

@public_bp.get("/profile", endpoint="profile")
def profile_page():
    return render_template("public/profile.html")

@public_bp.get("/__color_test")
def color_test():
    return """<!doctype html><meta charset="utf-8">
<div style="background:#0b1c14;color:#f5d547;padding:24px;font:700 22px/1.2 system-ui;">
  If this is not dark green with gold text, styles are being blocked by CSP or forced-colors.
</div>"""


