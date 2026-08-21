"""Admin action logging."""
from flask import request
from flask_login import current_user

from extensions import db
from models import AuditLog


def record(action, target=None, detail=None, commit=True):
    """Write one audit row for whoever is logged in right now."""
    actor_id = getattr(current_user, "id", None) if current_user else None
    actor_name = None
    if current_user and getattr(current_user, "is_authenticated", False):
        actor_name = current_user.display_name or current_user.username

    entry = AuditLog(
        actor_id=actor_id,
        actor_name=actor_name,
        action=action,
        target=(str(target)[:160] if target else None),
        detail=(str(detail)[:400] if detail else None),
        ip=_client_ip(),
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
    return entry


def _client_ip():
    # PythonAnywhere puts the real client address in X-Forwarded-For.
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return (request.remote_addr or "")[:45]
