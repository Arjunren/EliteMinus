"""Application factory and entry point.

This process serves two audiences at once:

* the **admin panel** at ``/admin`` — server-rendered pages, session cookie auth
* the **JSON API** under ``/api`` — consumed by the static listener app hosted
  on Vercel, authenticated with a Bearer token

Deployed on PythonAnywhere via ``wsgi.py``.
"""
from flask import Flask, jsonify, redirect, request, url_for

from config import Config
from extensions import bcrypt, cors, db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # The Vercel front-end is on another origin, so the API needs CORS.
    # Bearer tokens (not cookies) carry the identity, so credentials are off.
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"] or "*"}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        max_age=86400,
    )

    # Models register the user_loader on import.
    import models  # noqa: F401
    from services import tokens

    @login_manager.request_loader
    def load_user_from_token(req):        # noqa: ARG001 - signature is fixed
        """Let ``Authorization: Bearer …`` stand in for a session cookie.

        With this in place every existing ``@login_required`` route and every
        ``current_user`` reference works for both the cookie-based admin panel
        and the token-based Vercel client, with no per-route changes.
        """
        return tokens.resolve(tokens.from_request())

    @login_manager.unauthorized_handler
    def unauthorized():
        # APIs get JSON 401; page requests get redirected to the login screen.
        if request.path.startswith("/api/"):
            return jsonify(error="authentication required"), 401
        return redirect(url_for("auth.login", next=request.path))

    # Blueprints
    from blueprints.admin import admin_bp
    from blueprints.api import api_bp
    from blueprints.auth import auth_bp
    from blueprints.main import main_bp
    from blueprints.spotify import spotify_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(spotify_bp, url_prefix="/api/spotify")
    app.register_blueprint(admin_bp)   # defines /admin and /api/admin/* itself

    @app.errorhandler(404)
    def not_found(_err):
        if request.path.startswith("/api/"):
            return jsonify(error="not found"), 404
        return redirect(url_for("main.index"))

    @app.errorhandler(500)
    def server_error(_err):
        db.session.rollback()
        if request.path.startswith("/api/"):
            return jsonify(error="server error"), 500
        return "Internal server error", 500

    @app.teardown_appcontext
    def remove_session(_exc=None):
        db.session.remove()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
