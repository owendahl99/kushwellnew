# app/utils/flow.py
"""
Centralized “what’s next?” flow logic.
Return endpoint strings (e.g., 'patient.identity_setup') for the app to redirect to,
or None when the user is ready for their dashboard.

Usage:
    nxt = next_route_for(user)
    if nxt:
        return redirect(url_for(nxt))
    return redirect(url_for(default_dashboard_for(user)))
"""

from __future__ import annotations
from typing import Optional
from app.constants.enums import \


# ---- Patient sequencing ------------------------------------------------------

# app/utils/flow.py
from flask import url_for
from flask_login import current_user

def next_step_for_patient(user=None):
    """Return the next route for a patient onboarding/progression flow."""
    u = user or current_user
    # Replace these checks with your real logic as you build it out.
    profile = getattr(u, "patient_profile", None)
    if not profile:
        return url_for("patient.onboarding_form")
    # If wellness needed:
    if getattr(u, "needs_wellness_check", False):
        return url_for("patient.wellness_checkin")
    # Default dashboard:
    return url_for("patient.dashboard")


# ---- Enterprise sequencing ---------------------------------------------------

def next_step_for_enterprise(user) -> Optional[str]:
    """
    Ordered steps for enterprise accounts; all checks guarded.
    """
    if not bool(getattr(user, "has_completed_onboarding", False)):
        # your existing onboarding route
        return "enterprise.onboarding"

    if hasattr(user, "has_completed_profile") and not bool(getattr(user, "has_completed_profile", False)):
        return "enterprise.profile_setup"

    if hasattr(user, "has_completed_verification") and not bool(getattr(user, "has_completed_verification", False)):
        return "enterprise.verify_org"

    return None


def default_dashboard_for_enterprise() -> str:
    # matches your main.py redirect endpoint
    return "enterprise.enterprise_dashboard"


# ---- Admin (simple) ---------------------------------------------------------

def next_step_for_admin(user) -> Optional[str]:
    # usually no pre-dashboard steps; customize if needed
    return None


def default_dashboard_for_admin() -> str:
    return "admin.dashboard"


# ---- Router helpers ----------------------------------------------------------

def next_route_for(user) -> Optional[str]:
    """
    Return the next endpoint this user should visit BEFORE their dashboard,
    or None if they’re fully set up.
    """
    role = getattr(user, "role", None)

    # Handle enum vs. raw string
    if isinstance(role, UserRoleEnum):
        role_enum = role
    else:
        try:
            role_enum = UserRoleEnum(role)
        except Exception:
            role_enum = None

    if role_enum == UserRoleEnum.PATIENT:
        return next_step_for_patient(user)

    if role_enum == UserRoleEnum.ENTERPRISE:
        return next_step_for_enterprise(user)

    if role_enum == UserRoleEnum.ADMIN:
        return next_step_for_admin(user)

    # Unknown role → no gating here
    return None


def default_dashboard_for(user) -> str:
    """
    Return the final dashboard endpoint for the given user’s role.
    """
    role = getattr(user, "role", None)

    if isinstance(role, UserRoleEnum):
        role_enum = role
    else:
        try:
            role_enum = UserRoleEnum(role)
        except Exception:
            role_enum = None

    if role_enum == UserRoleEnum.PATIENT:
        return default_dashboard_for_patient()

    if role_enum == UserRoleEnum.ENTERPRISE:
        return default_dashboard_for_enterprise()

    if role_enum == UserRoleEnum.ADMIN:
        return default_dashboard_for_admin()

    # Sensible fallback
    return "auth.logout"


