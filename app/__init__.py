    # FILE: app/__  __.py
""" 
    Kushwell application factory.
    Constructs the Flask application, registers extensions and blueprints,
    and sets up core configuration.
    """

from __future__ import annotations

import os
import logging
from logging.handlers import RotatingFileHandler
import time
from datetime import datetime, date
from typing import Any, Dict

from flask import Flask, send_from_directory, current_app, url_for, render_template
from flask_login import current_user
from werkzeug.routing import BuildError

# extensions
from app.extensions import db, login_manager, mail, migrate, csrf
from app.services.security import effective_display_name, can_view
from app.config import INSTANCE_DIR  # set in config.py

    

# NEW: needed for {{ csrf_token() }}
from flask_wtf.csrf import generate_csrf


def _init_logging(app: Flask) -> None:
    """Minimal, Windows-safe logging init. No prints, no crashes if console detaches."""
    if getattr(app, "_logging_initialized", False):
        return

    import sys
    app.logger.setLevel(logging.INFO)
    # Don�t let logging raise in dev on Windows
    logging.raiseExceptions = False
    app.logger.propagate = False

    # Remove any handlers the reloader might have added
    for h in list(app.logger.handlers):
        try:
            app.logger.removeHandler(h)
        except Exception:
            pass

    # File handler (rotating)
    logs_dir = os.path.join(app.root_path, "..", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    file_path = os.path.abspath(os.path.join(logs_dir, "kushwell.log"))
    fh = RotatingFileHandler(file_path, maxBytes=2_000_000, backupCount=5)
    fh.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    fh.setFormatter(fmt)
    app.logger.addHandler(fh)

    # Console handler only if a real TTY; swallow handler errors (pipe closed, etc.)
    try:
        if getattr(sys, "stderr", None) and hasattr(sys.stderr, "isatty") and sys.stderr.isatty():
            ch = logging.StreamHandler(stream=sys.stderr)
            ch.setLevel(logging.INFO)
            ch.setFormatter(fmt)
            ch.handleError = lambda *a, **k: None  # type: ignore
            app.logger.addHandler(ch)
    except Exception:
        pass

    app._logging_initialized = True



def create_app(config_object: Any | None = None) -> Flask:
    """
    Application factory for the Kushwell Flask app.
    Uses FLASK_CONFIG env var (e.g., "config.DevelopmentConfig") unless
    an explicit config class/path is passed via `config_object`.
    """
    app = Flask(
        __name__,
        instance_path=str(INSTANCE_DIR),
        instance_relative_config=True,
        static_folder="static",
        template_folder="templates",
    )
    
    app.jinja_env.globals.update(getattr=getattr)

    # ---------- Core config ----------
    cfg = config_object or os.getenv("FLASK_CONFIG", "config.DevelopmentConfig")
    app.config.from_object(cfg)

    # Defaults that are safe to set if not already configured
    app.config.setdefault("WTF_CSRF_HEADERS", ["X-CSRFToken", "X-CSRF-Token"])
    app.config.setdefault("SERVER_NAME", None)          # important: key must exist
    app.config.setdefault("PREFERRED_URL_SCHEME", "http")

    # Dev convenience: auto-reload templates
    if app.config.get("DEBUG"):
        app.config["TEMPLATES_AUTO_RELOAD"] = True

    # Ensure instance dir exists
    os.makedirs(app.instance_path, exist_ok=True)

    # ---------- Init extensions ----------
    csrf.init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)

    # ---------- Jinja helpers (safe endpoint checks) ----------
    @app.context_processor
    def _jinja_helpers():
        def has_endpoint(name: str) -> bool:
            try:
                return bool(name) and (name in current_app.view_functions)
            except Exception:
                return False

        def url_for_if(name: str, **kwargs):
            """Return url_for(name) if endpoint exists; else None."""
            if not has_endpoint(name):
                return None
            try:
                return url_for(name, **kwargs)
            except Exception:
                return None

        def safe_url_for(name: str, **kwargs) -> str:
            """url_for that never raises inside templates; returns '#' if missing."""
            if not has_endpoint(name):
                return "#"
            try:
                return url_for(name, **kwargs)
            except (BuildError, Exception):
                return "#"

        # <<< NEW HELPER >>> safe attribute accessor
        def safe_attr(obj, name, default=None):
            """Safely get an attribute from an object; returns default if missing."""
            try:
                return getattr(obj, name, default)
            except Exception:
                return default

        return dict(
            has_endpoint=has_endpoint,
            url_for_if=url_for_if,
            safe_url_for=safe_url_for,
            safe_attr=safe_attr,  # <--- globally available in Jinja
        )


    # fmt_date filter (used by wellness templates)
    def fmt_date(value, fmt: str = "%b %d, %Y") -> str:
        """
        Format a date/datetime (or ISO-like string) to a friendly string.
        Returns "" if value is falsy or unparseable.
        """
        if not value:
            return ""
        try:
            if isinstance(value, (datetime, date)):
                dt = value
            else:
                s = str(value)
                try:
                    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:
                    return s
            return dt.strftime(fmt)
        except Exception:
            return ""

    app.add_template_filter(fmt_date, name="fmt_date")

    # ---------- Onboarding (steps + pct) injected globally ----------
    @app.context_processor
    def onboarding_context():
        """
        Provides onboarding progress to templates without relying on utils/wellness.py.
        Uses patient._calc_onboarding_steps_and_pct to keep logic in one place.
        """
        steps: Dict[str, bool] = {}
        pct = 0
        try:
            # lazy import to avoid init-time circulars
            from app.routes.patient import _calc_onboarding_steps_and_pct  # type: ignore
            steps, pct = _calc_onboarding_steps_and_pct(current_user.id)
        except Exception:
            # Safe fallback so templates don't blow up
            try:
                alias_ok = bool(
                    (getattr(current_user, "alias", "") or getattr(current_user, "alias_name", "")).strip()
                )
                fullname_ok = bool((getattr(current_user, "full_name", "") or "").strip())
                steps = {
                    "registration": True,
                    "alias": alias_ok,
                    "fullname": fullname_ok,
                    "dob": False,
                    "zip": False,
                    "checkin": False,
                }
                pct = int(round(sum(1 for v in steps.values() if v) / len(steps) * 100))
            except Exception:
                steps, pct = {}, 0

        # Return both legacy and new keys to avoid template churn
        return {
            "steps": steps,
            "pct": pct,
            "onboarding_steps": steps,
            "onboarding_pct": pct,
        }
    # ---------- More Jinja helpers: safe attribute access ----------
    def first_attr(obj, names, default=None):
        try:
            for n in names:
                if hasattr(obj, n):
                    v = getattr(obj, n)
                    if v is not None:
                        return v
        except Exception:
            pass
        return default

    def getattr_or(obj, name, default=None):
        try:
            return getattr(obj, name)
        except Exception:
            return default

    def has_attr(obj, name):
        try:
            return hasattr(obj, name)
        except Exception:
            return False

    app.jinja_env.globals["first_attr"] = first_attr
    app.jinja_env.filters["getattr"] = getattr_or
    app.jinja_env.tests["has_attr"] = has_attr

    # ---------- Enterprise public URL helper ----------
    @app.context_processor
    def enterprise_helpers():
        def enterprise_public_url(e) -> str:
            def _has(ep: str) -> bool:
                try:
                    return ep in current_app.view_functions
                except Exception:
                    return False

            # Accept dict or model-like object
            if isinstance(e, dict):
                eid = e.get("id")
                kind = (e.get("kind") or "").lower()
            else:
                eid = getattr(e, "id", None)
                kind = (getattr(e, "kind", "") or "").lower()

            if not eid or not kind:
                return "#"

            if kind == "provider":
                for ep in ("enterprise.provider_public", "enterprise.provider"):
                    if _has(ep):
                        for kw in ({"provider_id": eid}, {"id": eid}):
                            try:
                                return url_for(ep, **kw)
                            except Exception:
                                pass
            elif kind == "supplier":
                for ep in ("enterprise.supplier_public", "enterprise.supplier"):
                    if _has(ep):
                        for kw in ({"supplier_id": eid}, {"id": eid}):
                            try:
                                return url_for(ep, **kw)
                            except Exception:
                                pass
            elif kind == "dispensary":
                for ep in ("enterprise.dispensary_public", "enterprise.dispensary"):
                    if _has(ep):
                        for kw in ({"dispensary_id": eid}, {"id": eid}):
                            try:
                                return url_for(ep, **kw)
                            except Exception:
                                pass

            return "#"

        return {"enterprise_public_url": enterprise_public_url}

    # ---------- Global template context ----------
    @app.context_processor
    def kushwell_template_context():
        def display_name(user, viewer_id: int | None = None) -> str:
            try:
                vid = viewer_id if viewer_id is not None else (
                    current_user.id if current_user.is_authenticated else None
                )
            except Exception:
                vid = None
            return effective_display_name(user, vid)

        # Expose csrf_token() callable for templates
        def csrf_token():
            try:
                return generate_csrf()
            except Exception:
                return ""

        return {
            "csrf_token": csrf_token,  # use {{ csrf_token() }}
            "current_year": date.today().year,
            "display_name": display_name,
            "can_view": can_view,
            "ASSET_VER": int(time.time()),
        }

    # ---------- CSP (single, consolidated) ----------@app.after_request
    def set_csp(resp):
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com data:; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.jsdelivr.net/npm/chart.js https://cdnjs.cloudflare.com; "
            "connect-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "img-src 'self' data: blob:; "
            "frame-ancestors 'self'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        return resp



    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html", message="Page not found."), 404

    # --- Static: favicon ---
    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.root_path, "static"),
            "favicon.ico",
            mimetype="image/vnd.microsoft.icon",
        )
    
    from app.utils.context_injectors import inject_master_globals
    app.context_processor(inject_master_globals)


    # --- Import models so SQLAlchemy registers them ---
    from . import models as _models  # noqa: F401

    from app.routes.public import public_bp
    from app.routes.auth import auth_bp           # must come before patient
    from app.routes.typeahead import typeahead_bp
    from app.routes.admin import admin_bp
    from app.routes.enterprise import enterprise_bp
    from app.routes.patient import patient_bp     # depends on auth + db models
    from app.routes.products import products_bp
    from app.routes.analytics import analytics_bp
    from app.routes.comm import comm_bp
    from app.routes.search import search_bp

    # ---------- Register ----------
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)               # 1️⃣ ensures login/session
    app.register_blueprint(admin_bp)
    app.register_blueprint(enterprise_bp)
    app.register_blueprint(patient_bp)            # 2️⃣ safe to use current_user
    app.register_blueprint(products_bp)
    app.register_blueprint(analytics_bp)
    app.register_blueprint(comm_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(typeahead_bp, url_prefix="/typeahead")

    print("[Kushwell] ✅ Blueprints registered successfully.")
    print("[Kushwell] 🚀 App initialization complete.")

  
    # ---------- Login manager ----------
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return User.query.get(int(user_id)) if user_id else None
        except Exception:
            return None

    login_manager.login_view = "auth.login"

    # ---------- Logging + redirect hook (last) ----------
    _init_logging(app)
    app.after_request(_log_redirects)

    return app

def _log_redirects(resp):
    try:
        if 300 <= int(resp.status_code) < 400:
            loc = resp.headers.get("Location")
            if loc:
                current_app.logger.info("[REDIRECT] %s -> %s", resp.status_code, loc)
    except Exception:
        pass
    return resp
                


