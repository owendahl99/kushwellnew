# config.py (project root)
import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent
INSTANCE_DIR = PROJECT_ROOT / "instance"          # <repo>/instance
UPLOAD_DIR   = PROJECT_ROOT / "app" / "static" / "uploads"

class Config:
    # --- Security / CSRF ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    WTF_CSRF_ENABLED = True
    # In prod we’ll use a real window; Dev overrides to None
    WTF_CSRF_TIME_LIMIT = 60 * 60  # 1 hour

    # --- SQLAlchemy ---
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + str((INSTANCE_DIR / "kushwell.db").resolve()).replace("\\", "/")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Uploads ---
    UPLOAD_FOLDER = str(UPLOAD_DIR)

    # --- Mail (supply real creds via env vars) ---
    MAIL_SERVER = "smtp.gmail.com"
    MAIL_PORT = 587
    MAIL_USE_TLS = True
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "your-email@example.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD", "your-email-password")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "your-email@example.com")
    MAIL_MAX_EMAILS = None

    # --- Cookies (secure defaults tuned per environment) ---
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # Optional: don’t set SERVER_NAME here.
    # In dev we’ll leave it unset so cookies work on localhost.
    # In prod, configure SERVER_NAME via env if you need absolute URLs:
    # SERVER_NAME = os.environ.get("SERVER_NAME")  # e.g., "app.example.com"

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    # On http://localhost, keep these False so the session cookie is sent
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_SECURE = False
    # No CSRF expiry during dev
    WTF_CSRF_TIME_LIMIT = None
    # Explicitly avoid forcing a SERVER_NAME in dev
    # (Flask will behave fine without it)
    # SERVER_NAME = None

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    # Only send cookies over HTTPS in prod
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    # e.g., 8 hours CSRF lifetime in prod
    WTF_CSRF_TIME_LIMIT = 60 * 60 * 8
    # Optionally set SERVER_NAME via env (don’t hardcode)
    SERVER_NAME = os.environ.get("SERVER_NAME")  # e.g., "app.example.com"


