"""Authentication.

Sign-up is a two-step flow:

    POST /api/auth/register   -> account created as unverified, OTP e-mailed
    POST /api/auth/verify     -> code checked, account activated, token issued

The same logic backs the server-rendered ``/login``, ``/register`` and
``/verify`` pages, which exist so an admin can reach the panel on
PythonAnywhere without the Vercel front-end.

There is deliberately no self-service password reset: a user who forgets their
password contacts the developer, who resets it from the staff panel.
"""
import re
import time
from datetime import date

from flask import (Blueprint, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db
from models import Playlist, User, utcnow
from services import audit, mailer, otp, tokens

auth_bp = Blueprint("auth", __name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
MIN_PASSWORD = 8

# Very small in-process throttle: {key: [count, first_attempt_ts]}.
_attempts = {}
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW = 300          # seconds


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() if forwarded
            else request.remote_addr or "")


def _throttled(key):
    """True when ``key`` has failed too often lately."""
    now = time.time()
    count, started = _attempts.get(key, (0, now))
    if now - started > ATTEMPT_WINDOW:
        _attempts.pop(key, None)
        return False
    return count >= MAX_ATTEMPTS


def _record_failure(key):
    now = time.time()
    count, started = _attempts.get(key, (0, now))
    if now - started > ATTEMPT_WINDOW:
        count, started = 0, now
    _attempts[key] = (count + 1, started)


def _clear_failures(key):
    _attempts.pop(key, None)


def _safe_next(target):
    """Only allow same-site relative redirects (avoid open redirect)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("main.index")


def validate_registration(username, email, password, confirm):
    """Return a list of human-readable problems (empty means all good)."""
    errors = []
    if not (3 <= len(username) <= 50):
        errors.append("Username must be 3–50 characters.")
    elif not re.match(r"^[A-Za-z0-9._-]+$", username):
        errors.append("Username can only contain letters, numbers, dot, "
                      "underscore and hyphen.")
    if not EMAIL_RE.match(email):
        errors.append("Please enter a valid e-mail address.")
    if len(password) < MIN_PASSWORD:
        errors.append(f"Password must be at least {MIN_PASSWORD} characters.")
    elif password.isdigit() or password.isalpha():
        errors.append("Password must mix letters and numbers.")
    if password != confirm:
        errors.append("Passwords do not match.")
    return errors


def _finish_login(user, remember=False):
    """Shared post-authentication bookkeeping."""
    user.last_login_at = utcnow()
    user.last_login_ip = _client_ip()[:45]
    user.login_count = (user.login_count or 0) + 1
    db.session.commit()
    login_user(user, remember=remember)


def _create_starter_playlist(user):
    starter = Playlist(owner_id=user.id, name="My First Playlist",
                       description="Songs I love", cover_seed="My First Playlist")
    db.session.add(starter)


def developer_contact():
    cfg = current_app.config
    return {
        "name": cfg["DEVELOPER_NAME"],
        "email": cfg["DEVELOPER_EMAIL"],
        "phone": cfg["DEVELOPER_PHONE"],
    }


# --------------------------------------------------------------------------
# Shared registration / verification logic
# --------------------------------------------------------------------------
def _register(username, email, password, confirm):
    """Create (or refresh) an unverified account and e-mail a code.

    Returns ``(user, None)`` on success or ``(None, [errors])``.
    """
    username = (username or "").strip()
    email = (email or "").strip().lower()
    password = password or ""
    confirm = confirm or ""

    errors = validate_registration(username, email, password, confirm)
    if errors:
        return None, errors

    by_email = User.query.filter_by(email=email).first()
    by_username = User.query.filter_by(username=username).first()

    if by_email and by_email.is_verified:
        return None, ["An account with that e-mail already exists. Log in instead."]
    if by_username and by_username is not by_email:
        return None, ["That username is already taken."]

    # An unverified signup can be replayed — people close the tab, mistype the
    # code, or come back the next day. Update the pending row in place.
    user = by_email
    if user is None:
        user = User(email=email)
        db.session.add(user)

    user.username = username
    user.display_name = user.display_name or username
    user.set_password(password)
    user.is_verified = False
    user.status = "pending"
    user.role = user.role or "staff"
    db.session.flush()
    user.assign_staff_code()
    db.session.commit()

    try:
        otp.issue(email, purpose="register")
    except otp.OTPError as exc:
        return None, [exc.message]

    return user, None


def _verify(email, code):
    """Consume the code and activate the account.

    Returns ``(user, None)`` or ``(None, error_message)``.
    """
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        return None, "No sign-up found for that e-mail. Please register again."
    if user.is_verified:
        return None, "That e-mail is already verified. You can log in."

    try:
        otp.verify(email, code, purpose="register")
    except otp.OTPError as exc:
        return None, exc.message

    user.is_verified = True
    user.verified_at = utcnow()
    user.status = ("pending" if current_app.config["REQUIRE_ADMIN_APPROVAL"]
                   else "active")
    if not user.hire_date:
        user.hire_date = date.today()
    _create_starter_playlist(user)
    db.session.commit()

    audit.record("account.verified", target=user.username,
                 detail=f"self sign-up ({user.email})")
    mailer.send_welcome(user.email, user.display_name or user.username)
    return user, None


# ==========================================================================
# JSON API — used by the Vercel front-end
# ==========================================================================
@auth_bp.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(silent=True) or {}
    user, errors = _register(data.get("username"), data.get("email"),
                             data.get("password"), data.get("confirm"))
    if errors:
        return jsonify(error=errors[0], errors=errors), 400
    return jsonify({
        "status": "otp_sent",
        "email": user.email,
        "expires_in_minutes": current_app.config["OTP_TTL_MINUTES"],
        "resend_after_seconds": current_app.config["OTP_RESEND_SECONDS"],
        "message": f"We sent a {current_app.config['OTP_LENGTH']}-digit code to "
                   f"{user.email}.",
    }), 201


@auth_bp.route("/api/auth/verify", methods=["POST"])
def api_verify():
    data = request.get_json(silent=True) or {}
    user, error = _verify(data.get("email"), data.get("code"))
    if error:
        return jsonify(error=error), 400

    if user.status != "active":
        return jsonify({
            "status": "awaiting_approval",
            "message": "Your e-mail is verified. An administrator still needs "
                       "to approve your account before you can sign in.",
        }), 202

    return jsonify({
        "status": "verified",
        "token": tokens.issue(user),
        "user": user.to_dict(),
    })


@auth_bp.route("/api/auth/resend", methods=["POST"])
def api_resend():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    # Don't confirm or deny that an address exists.
    if not user or user.is_verified:
        return jsonify(status="otp_sent",
                       message="If that address needs verifying, a new code is "
                               "on its way.")
    try:
        otp.issue(email, purpose="register")
    except otp.OTPError as exc:
        return jsonify(error=exc.message, retry_after=exc.retry_after), 429
    return jsonify(status="otp_sent", message=f"A new code is on its way to {email}.")


@auth_bp.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    identifier = (data.get("identifier") or "").strip()
    password = data.get("password") or ""

    key = f"login:{_client_ip()}"
    if _throttled(key):
        return jsonify(error="Too many failed attempts. Try again in a few "
                             "minutes."), 429

    user = User.query.filter(
        (User.username == identifier) | (User.email == identifier.lower())
    ).first()

    if not user or not user.check_password(password):
        _record_failure(key)
        return jsonify(error="Invalid username/e-mail or password."), 401

    if not user.is_verified:
        try:
            otp.issue(user.email, purpose="register")
            sent = True
        except otp.OTPError:
            sent = False
        return jsonify({
            "error": "Your e-mail isn't verified yet.",
            "code": "unverified",
            "email": user.email,
            "otp_sent": sent,
        }), 403

    if user.status == "suspended":
        return jsonify(error="This account is suspended. Contact the developer.",
                       code="suspended", developer=developer_contact()), 403
    if user.status != "active":
        return jsonify(error="Your account is waiting for administrator "
                             "approval.", code="pending"), 403

    _clear_failures(key)
    user.last_login_at = utcnow()
    user.last_login_ip = _client_ip()[:45]
    user.login_count = (user.login_count or 0) + 1
    db.session.commit()

    return jsonify({
        "token": tokens.issue(user),
        "user": user.to_dict(),
        "expires_in": current_app.config["API_TOKEN_MAX_AGE"],
    })


@auth_bp.route("/api/auth/me")
@login_required
def api_me():
    return jsonify(current_user.to_dict())


@auth_bp.route("/api/auth/logout", methods=["POST"])
def api_logout():
    # Bearer tokens are stateless: the client drops it. Clear any cookie too.
    logout_user()
    return jsonify(ok=True)


@auth_bp.route("/api/auth/developer")
def api_developer():
    """Contact details shown on the 'forgot password' screen."""
    return jsonify(developer_contact())


@auth_bp.route("/api/auth/password-help", methods=["POST"])
def api_password_help():
    """Forward a password-reset request to the developer by e-mail."""
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    message = (data.get("message") or "").strip()[:1000]

    if not EMAIL_RE.match(email):
        return jsonify(error="Please enter a valid e-mail address."), 400

    key = f"help:{_client_ip()}"
    if _throttled(key):
        return jsonify(error="Too many requests. Try again later."), 429
    _record_failure(key)

    user = User.query.filter_by(email=email).first()
    dev_email = current_app.config["DEVELOPER_EMAIL"]
    if user and dev_email:
        mailer.send_password_help_request(
            dev_email, email, user.username, message, _client_ip())

    # Same answer either way, so the form can't be used to probe for accounts.
    return jsonify(ok=True, developer=developer_contact(),
                   message="Your request has been sent to the developer. "
                           "They'll contact you at this address.")


# ==========================================================================
# Server-rendered pages — the admin's way in on PythonAnywhere
# ==========================================================================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(_safe_next(request.args.get("next")))

    if request.method == "POST":
        identifier = (request.form.get("identifier") or "").strip()
        password = request.form.get("password") or ""
        key = f"login:{_client_ip()}"

        if _throttled(key):
            flash("Too many failed attempts. Try again in a few minutes.", "error")
            return render_template("login.html")

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user and user.check_password(password):
            if not user.is_verified:
                session["pending_email"] = user.email
                try:
                    otp.issue(user.email, purpose="register")
                    flash("Your e-mail isn't verified yet — we've sent you a "
                          "fresh code.", "error")
                except otp.OTPError as exc:
                    flash(exc.message, "error")
                return redirect(url_for("auth.verify"))
            if user.status == "suspended":
                flash("This account is suspended. Contact the developer.", "error")
                return render_template("login.html")
            if user.status != "active":
                flash("Your account is waiting for administrator approval.",
                      "error")
                return render_template("login.html")

            _clear_failures(key)
            _finish_login(user, remember=bool(request.form.get("remember")))
            return redirect(_safe_next(request.args.get("next")))

        _record_failure(key)
        flash("Invalid username/e-mail or password.", "error")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        user, errors = _register(username, email,
                                 request.form.get("password"),
                                 request.form.get("confirm"))
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("register.html", username=username, email=email)

        session["pending_email"] = user.email
        flash(f"We sent a {current_app.config['OTP_LENGTH']}-digit code to "
              f"{user.email}.", "success")
        return redirect(url_for("auth.verify"))

    return render_template("register.html")


@auth_bp.route("/verify", methods=["GET", "POST"])
def verify():
    email = session.get("pending_email", "")

    if request.method == "POST":
        email = (request.form.get("email") or email).strip().lower()
        user, error = _verify(email, request.form.get("code"))
        if error:
            flash(error, "error")
            return render_template("verify.html", email=email)

        session.pop("pending_email", None)
        if user.status != "active":
            flash("E-mail verified. An administrator will approve your account "
                  "shortly.", "success")
            return redirect(url_for("auth.login"))

        _finish_login(user)
        flash("Welcome to EliteMinus! 🎵", "success")
        return redirect(url_for("main.index"))

    return render_template("verify.html", email=email)


@auth_bp.route("/verify/resend", methods=["POST"])
def resend():
    email = (request.form.get("email") or session.get("pending_email") or "").lower()
    try:
        otp.issue(email, purpose="register")
        flash("A new code is on its way.", "success")
    except otp.OTPError as exc:
        flash(exc.message, "error")
    session["pending_email"] = email
    return redirect(url_for("auth.verify"))


@auth_bp.route("/forgot", methods=["GET", "POST"])
def forgot():
    """No self-service reset — this page routes the user to the developer."""
    sent = False
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        message = (request.form.get("message") or "").strip()[:1000]
        if not EMAIL_RE.match(email):
            flash("Please enter a valid e-mail address.", "error")
        else:
            user = User.query.filter_by(email=email).first()
            dev_email = current_app.config["DEVELOPER_EMAIL"]
            if user and dev_email:
                mailer.send_password_help_request(
                    dev_email, email, user.username, message, _client_ip())
            sent = True
            flash("Your request has been sent to the developer.", "success")

    return render_template("forgot.html", developer=developer_contact(), sent=sent)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
