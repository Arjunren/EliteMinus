"""Non-destructive migration for an EXISTING database.

Adds the `is_admin` column (if missing) and ensures an admin account exists,
WITHOUT dropping any of your data.  Run once after pulling the admin feature:

    python make_admin.py

(Fresh installs don't need this -- `python seed.py` already creates the admin.)

Admin login ->  username: admin   password: admin12345
"""
from sqlalchemy import text

from app import create_app
from extensions import db
from models import User


def main():
    app = create_app()
    with app.app_context():
        # MariaDB/MySQL support IF NOT EXISTS for ADD COLUMN.
        db.session.execute(text(
            "ALTER TABLE users "
            "ADD COLUMN IF NOT EXISTS is_admin TINYINT(1) NOT NULL DEFAULT 0"
        ))
        db.session.commit()
        print("ensured users.is_admin column exists")

        admin = User.query.filter_by(username="admin").first()
        if admin:
            admin.is_admin = True
            print("admin account already existed -> ensured admin rights")
        else:
            admin = User(username="admin", email="admin@admin.com",
                         display_name="Admin", is_admin=True)
            admin.set_password("admin12345")
            db.session.add(admin)
            print("created admin account  ->  admin / admin12345")
        db.session.commit()

    print("Done. Open http://localhost:5000/admin")


if __name__ == "__main__":
    main()
