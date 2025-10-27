# FILE: app/routes/auth.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse, urljoin

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func
from flask_mail import Message

from app.extensions import db, mail
from app.models import User
from app.constants.general_menus import UserRoleEnum
from app.utils.tokens import generate_reset_token, verify_reset_token

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ----------------------------- helpers ---------------------------------------

def _has_endpoint(name: str) -> bool:
    return name in current_app.view_functions


def _is_safe_redirect_target(target: str) -> bool:
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return (test.scheme in ("http", "https")) and (ref.netloc == test.netloc)


def _to_enum(role_value) -> Optional[UserRoleEnum]:
    """Force role values to proper Enum uppercase mapping."""
    if role_value is None:
        return None
    if isinstance(role_value, UserRoleEnum):
        return role_value
    try:
        return UserRoleEnum[str(role_value).upper()]
    except Exception:
        return None


def _set_password(user: User, password: str) -> None:
    """Set hashed password safely."""
    if hasattr(user, "set_password") and callable(user.set_password):
        user.set_password(password)
    else:
        user.password_hash = generate_password_hash(password)


def _role_home_endpoint(user: User) -> str:
    """Redirect user to the correct dashboard based on role (fallback to login)."""
    role = _to_enum(getattr(user, "role", None))

    if role == UserRoleEnum.ADMIN:
        return "admin.admin_dashboard" if _has_endpoint("admin.admin_dashboard") else "auth.login"
    elif role == UserRoleEnum.ENTERPRISE:
        for ep in ("enterprise.enterprise_dashboard", "enterprise.enterprise_dashboard"):
            if _has_endpoint(ep):
                return ep
    elif role == UserRoleEnum.PATIENT:
        for ep in ("patient.patient_dashboard", "patient.home"):
            if _has_endpoint(ep):
                return ep
    return "auth.login"


def _post_auth_redirect(user: User):
    """Redirect user safely after login or registration."""
    nxt = request.args.get("next") or request.form.get("next")
    if nxt and _is_safe_redirect_target(nxt):
        return redirect(nxt)
    return redirect(url_for(_role_home_endpoint(user)))


# ----------------------------- routes ----------------------------------------

@auth_bp.route("/whoami", methods=["GET"], endpoint="whoami")
def whoami():
    if not current_user.is_authenticated:
        return {"authenticated": False}
    role = getattr(current_user, "role", None)
    return {
        "authenticated": True,
        "id": getattr(current_user, "id", None),
        "email": getattr(current_user, "email", None),
        "role": str(role),
    }


@auth_bp.route("/login", methods=["GET", "POST"], endpoint="login")
def login():
    if current_user.is_authenticated and request.args.get("relogin"):
        logout_user()

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()

        user = User.query.filter(func.lower(User.email) == email).first()
        if not user or not getattr(user, "password_hash", None) or not check_password_hash(user.password_hash, password):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", email=email, next=request.args.get("next", "")), 401

        login_user(user, remember=bool(request.form.get("remember")))
        flash("Logged in successfully.", "success")
        return _post_auth_redirect(user)

    return render_template("auth/login.html", next=request.args.get("next", ""))


@auth_bp.route("/post_login")
@login_required
def post_login():
    """Post-login routing: patients go to baseline if incomplete."""
    from app.models import PatientProfile  # local import to avoid circular import

    role = _to_enum(getattr(current_user, "role", None))

    if role == UserRoleEnum.PATIENT:
        patient = PatientProfile.query.filter_by(user_sid=current_user.sid).first()
        if not patient:
            return redirect(url_for("public.index"))

        if not patient.onboarding_complete:
            return redirect(url_for("patient.baseline_checkin"))

        return redirect(url_for("patient.patient_dashboard"))

    # Non-patients
    return redirect(url_for(_role_home_endpoint(current_user)))


@auth_bp.get("/logout", endpoint="logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("public.landing") if _has_endpoint("public.landing") else "/")


@auth_bp.route("/register", methods=["GET", "POST"], endpoint="register")
def register():
    """Register a new user (patient or enterprise)."""
    from app.models import PatientProfile  # local import for circular safety

    if current_user.is_authenticated:
        return _post_auth_redirect(current_user)

    preset_role = (request.args.get("role") or "").strip().upper()
    if preset_role not in {"PATIENT", "ENTERPRISE"}:
        preset_role = ""

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = (request.form.get("password") or "").strip()
        role = (request.form.get("role") or preset_role or "").strip().upper()

        full_name = (request.form.get("full_name") or "").strip()
        alias_name = (request.form.get("alias_name") or "").strip()
        birthdate_str = (request.form.get("birthdate") or "").strip()
        zip_code = (request.form.get("zip_code") or "").strip()

        # --- Validation ---
        if not email or not password or role not in {"PATIENT", "ENTERPRISE"}:
            flash("Please provide email, password, and a valid account type.", "danger")
            return render_template("auth/register.html", preset_role=preset_role)

        if role == "PATIENT" and not all([full_name, alias_name, birthdate_str, zip_code]):
            flash("Please fill out all required patient fields.", "danger")
            return render_template("auth/register.html", preset_role=preset_role)

        if User.query.filter(func.lower(User.email) == email).first():
            flash("Email is already registered.", "warning")
            return redirect(url_for("auth.login"))

        # --- Parse birthdate safely ---
        birthdate = None
        if birthdate_str:
            try:
                birthdate = datetime.strptime(birthdate_str, "%Y-%m-%d").date()
            except ValueError:
                flash("Please enter a valid date (YYYY-MM-DD).", "warning")
                return render_template("auth/register.html", preset_role=preset_role)

        # --- Enum handling ---
        role_enum = _to_enum(role)
        if role_enum is None:
            flash("Invalid account type.", "danger")
            return render_template("auth/register.html", preset_role=preset_role)

        # --- Create user ---
        user = User(email=email, role=role_enum)
        _set_password(user, password)

        if role_enum == UserRoleEnum.PATIENT:
            user.full_name = full_name
            user.alias_name = alias_name
            user.birthdate = birthdate
            user.zip_code = zip_code

        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Registration successful.", "success")

        # --- Ensure PatientProfile exists ---
        if role_enum == UserRoleEnum.PATIENT:
            patient_profile = PatientProfile.query.filter_by(user_sid=user.sid).first()
            if not patient_profile:
                patient_profile = PatientProfile(user_sid=user.sid)
                db.session.add(patient_profile)
                db.session.commit()

            # Redirect based on onboarding
            if not patient_profile.onboarding_complete:
                try:
                    return redirect(url_for("patient.baseline_checkin"))
                except BuildError:
                    return redirect("/patient/checkin")

            return redirect(url_for("patient.patient_dashboard"))

        # Non-patient users
        return redirect(url_for(_role_home_endpoint(user)))

    return render_template("auth/register.html", preset_role=preset_role)


@auth_bp.route("/forgot-password", methods=["GET", "POST"], endpoint="forgot_password")
def forgot_password():
    """Send password reset email if user exists."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        user = User.query.filter(func.lower(User.email) == email).first()

        if user:
            try:
                token = generate_reset_token(user.email)
                reset_url = url_for("auth.reset_password", token=token, _external=True)
                msg = Message(
                    subject="Kushwell Password Reset",
                    recipients=[user.email],
                    body=f"Reset your password using this link: {reset_url}"
                )
                mail.send(msg)
            except Exception:
                # Fail silently
                pass

        flash("If an account exists, a reset link has been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset/<token>", methods=["GET", "POST"], endpoint="reset_password")
def reset_password(token: str):
    """Reset password via secure token."""
    email = verify_reset_token(token)
    if not email:
        flash("Invalid or expired reset link.", "danger")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.filter(func.lower(User.email) == email.lower()).first()
    if not user:
        flash("No user found for this link.", "danger")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        new_password = (request.form.get("password") or "").strip()
        if not new_password:
            flash("Password cannot be empty.", "warning")
        else:
            _set_password(user, new_password)
            db.session.commit()
            flash("Password updated. Please log in.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")
