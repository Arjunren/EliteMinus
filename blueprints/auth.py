"""Authentication: register, login, logout."""
from flask import (Blueprint, flash, redirect, render_template, request,
                   url_for)
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db
from models import Playlist, User

auth_bp = Blueprint("auth", __name__)


def _safe_next(target):
    """Only allow same-site relative redirects (avoid open redirect)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.index")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = request.form.get("password") or ""
        user = (User.query.filter(
            (User.username == identifier) | (User.email == identifier)
        ).first())

        if user and user.check_password(password):
            login_user(user, remember=bool(request.form.get("remember")))
            return redirect(_safe_next(request.args.get("next")))
        flash("Invalid username/email or password.", "error")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""

        errors = []
        if len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        if "@" not in email or "." not in email:
            errors.append("Please enter a valid email address.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if User.query.filter_by(username=username).first():
            errors.append("That username is already taken.")
        if User.query.filter_by(email=email).first():
            errors.append("An account with that email already exists.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html",
                                   username=username, email=email)

        user = User(username=username, email=email, display_name=username)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # get user.id

        # Give every new account a starter playlist with a few songs.
        starter = Playlist(owner_id=user.id, name="My First Playlist",
                           description="Songs I love", cover_seed="My First Playlist")
        db.session.add(starter)
        db.session.commit()

        login_user(user)
        flash("Welcome to your library! 🎵", "success")
        return redirect(url_for("main.index"))

    return render_template("register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
