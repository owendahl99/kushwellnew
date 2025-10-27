# app/utils/redirects.py

from flask import redirect, url_for


def redirect_post_login(user):
    role = user.role.name.lower()

    if role == "patient":
        return redirect(url_for("patient.dashboard"))
    elif role == "admin":
        return redirect(url_for("admin.dashboard"))
    elif role == "dispensary":
        return redirect(url_for("enterprise.dashboard"))
    else:
        return redirect(url_for("main.home"))  # fallback


