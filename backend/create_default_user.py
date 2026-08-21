"""Create the pre-verified development listener without resetting the database.

Run from the backend directory:

    python create_default_user.py

The command is safe to run more than once.  It never changes an existing
``user`` account; use the staff admin panel if that account needs changes.
"""
from app import create_app
from extensions import db
from models import User, utcnow


USERNAME = "user"
EMAIL = "user@eliteminus.local"
PASSWORD = "User@12345"


def create_default_user():
    """Create the account in the current Flask application context.

    Returns ``(user, created)`` and leaves any existing matching account alone.
    """
    existing = User.query.filter(
        (User.username == USERNAME) | (User.email == EMAIL)).first()
    if existing:
        return existing, False

    user = User(
        username=USERNAME,
        email=EMAIL,
        display_name="Default User",
        full_name="Default Test User",
        role="staff",
        status="active",
        is_verified=True,
        verified_at=utcnow(),
        department="Listener",
        position="Listener",
    )
    user.set_password(PASSWORD)
    db.session.add(user)
    db.session.flush()
    user.assign_staff_code()
    db.session.commit()
    return user, True


def main():
    app = create_app()
    with app.app_context():
        db.create_all()
        user, created = create_default_user()
        if created:
            print("Created verified test listener: user / User@12345")
        else:
            print(f"Account already exists: {user.username}")


if __name__ == "__main__":
    main()
