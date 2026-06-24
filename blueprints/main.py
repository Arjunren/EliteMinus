"""Page routes: serves the single-page application shell."""
from flask import Blueprint, render_template
from flask_login import current_user, login_required

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    """The app shell. All in-app navigation happens client-side so the
    audio player can keep playing while the user moves between views."""
    return render_template("app.html", user=current_user)
