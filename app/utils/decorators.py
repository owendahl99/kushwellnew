from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user
from app.constants.enums import UserRoleEnum


def role_required(role):
    """Restrict access to users with a specific role."""

    def role_required_wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))
            if current_user.role != role:
                flash("You do not have access to this page.", "danger")
                return redirect(url_for("auth.login"))
            return f(*args, **kwargs)

        return wrapped

    return role_required_wrapper


def require_onboarding(min_completion=100):
    """Restrict access until onboarding completion percentage is met."""

    def onboarding_wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

            steps_completed = current_user.onboarding_steps_completed or 0
            total_steps = current_user.onboarding_total_steps or 5
            completion = (steps_completed / total_steps) * 100 if total_steps else 0

            if completion < min_completion:
                flash("Please complete onboarding to unlock this feature.", "warning")
                return redirect(url_for("patient.dashboard"))
            return f(*args, **kwargs)

        return wrapped

    return onboarding_wrapper


def patient_onboarding_required(min_completion=100):
    """
    Shortcut decorator for patient routes that require:
    - Patient role OR Admin role
    - Onboarding completion
    """

    def patient_onboarding_wrapper(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

            # Allow access if admin
            if current_user.role == UserRoleEnum.ADMIN:
                return f(*args, **kwargs)

            # Must be patient otherwise
            if current_user.role != UserRoleEnum.PATIENT:
                flash("You do not have access to this page.", "danger")
                return redirect(url_for("auth.login"))

            steps_completed = current_user.onboarding_steps_completed or 0
            total_steps = current_user.onboarding_total_steps or 5
            completion = (steps_completed / total_steps) * 100 if total_steps else 0

            if completion < min_completion:
                flash("Please complete onboarding to unlock this feature.", "warning")
                return redirect(url_for("patient.dashboard"))

            return f(*args, **kwargs)

        return wrapped

    return patient_onboarding_wrapper


