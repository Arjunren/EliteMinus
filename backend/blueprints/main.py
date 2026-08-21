"""Root routes and a health check.

In production the listener app is a static site on Vercel and this process only
serves the API and the admin panel.  For convenience during local development
``/app`` also serves the ``frontend/`` folder straight off disk, so you can run
the whole system with a single ``python app.py``.
"""
import os

from flask import (Blueprint, current_app, jsonify, redirect,
                   send_from_directory, url_for)
from flask_login import current_user

from extensions import db
from models import Song, User

main_bp = Blueprint("main", __name__)

FRONTEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    os.pardir, "frontend")


@main_bp.route("/")
def index():
    """Admins land on the panel; everyone else goes to the listener app."""
    if current_user.is_authenticated and current_user.can_admin:
        return redirect(url_for("admin.dashboard_page"))
    if os.path.isdir(FRONTEND_DIR):
        return redirect("/app/")
    return redirect(current_app.config["FRONTEND_URL"])


@main_bp.route("/health")
def health():
    """Cheap liveness probe that also proves the database is reachable."""
    try:
        db.session.execute(db.text("SELECT 1"))
        database = "ok"
    except Exception as exc:                        # noqa: BLE001
        current_app.logger.error("health check failed: %s", exc)
        database = "unreachable"

    return jsonify({
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "users": User.query.count() if database == "ok" else None,
        "songs": Song.query.count() if database == "ok" else None,
        "spotify": bool(current_app.config["SPOTIFY_CLIENT_ID"]),
        "mail": not current_app.config["MAIL_SUPPRESS_SEND"],
    }), (200 if database == "ok" else 503)


# --------------------------------------------------------------------------
# Local-development convenience: serve ../frontend at /app
# --------------------------------------------------------------------------
@main_bp.route("/app/")
@main_bp.route("/app/<path:filename>")
def frontend(filename="index.html"):
    if not os.path.isdir(FRONTEND_DIR):
        return redirect(current_app.config["FRONTEND_URL"])
    target = os.path.join(FRONTEND_DIR, filename)
    if not os.path.isfile(target):
        filename = "index.html"
    return send_from_directory(FRONTEND_DIR, filename)
