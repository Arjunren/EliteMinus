"""Application factory and entry point for the Spotify-style app."""
from flask import Flask, jsonify, redirect, request, url_for

from config import Config
from extensions import bcrypt, db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # Models register the user_loader on import.
    import models  # noqa: F401

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

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp)   # defines /admin and /api/admin/* itself

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, port=5000)
