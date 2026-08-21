"""Signed API tokens for the cross-origin (Vercel) front-end.

The admin panel is served by Flask itself, so it can use an ordinary session
cookie.  The listener app is a static site on another domain, where third-party
cookies are unreliable — it authenticates with ``Authorization: Bearer <token>``
instead.

Tokens are stateless and signed with ``SECRET_KEY``: no server-side storage, and
changing the secret invalidates every token at once.  Each token also carries a
short fingerprint of the password hash, so resetting somebody's password
immediately logs their old tokens out.
"""
import hashlib

from flask import current_app, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SALT = "eliteminus-api-token"


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=SALT)


def _fingerprint(user):
    """Short digest of the password hash — changes whenever the password does."""
    return hashlib.sha256((user.password_hash or "").encode()).hexdigest()[:16]


def issue(user):
    """Return a signed token identifying ``user``."""
    return _serializer().dumps({"uid": user.id, "fp": _fingerprint(user)})


def resolve(token):
    """Return the ``User`` a token belongs to, or ``None`` if it isn't valid."""
    from models import User

    if not token:
        return None
    try:
        data = _serializer().loads(
            token, max_age=current_app.config["API_TOKEN_MAX_AGE"])
    except (BadSignature, SignatureExpired):
        return None

    user = User.query.get(data.get("uid"))
    if not user or data.get("fp") != _fingerprint(user):
        return None            # password changed since the token was issued
    if user.status == "suspended" or not user.is_verified:
        return None
    return user


def from_request():
    """Pull a token off the current request (header first, then ?token=)."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.args.get("token")
