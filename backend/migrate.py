"""Non-destructive schema upgrade.

Brings a database created by an older version of EliteMinus up to date without
touching any existing rows:

  * creates the new tables (email_otps, queue_items, audit_log,
    spotify_accounts, oauth_states)
  * adds the new staff / Spotify columns to the existing tables
  * back-fills sensible values (existing accounts become verified + active)
  * makes sure at least one administrator exists

Safe to run repeatedly:

    python migrate.py
"""
import argparse
import getpass

from sqlalchemy import inspect, text

from app import create_app
from extensions import db
from models import User, utcnow

# table -> column -> DDL fragment
NEW_COLUMNS = {
    "users": {
        "staff_code": "VARCHAR(20) NULL",
        "full_name": "VARCHAR(120) NULL",
        "role": "VARCHAR(20) NOT NULL DEFAULT 'staff'",
        "status": "VARCHAR(20) NOT NULL DEFAULT 'pending'",
        "department": "VARCHAR(80) NULL",
        "position": "VARCHAR(80) NULL",
        "phone": "VARCHAR(40) NULL",
        "hire_date": "DATE NULL",
        "notes": "TEXT NULL",
        "is_verified": "TINYINT(1) NOT NULL DEFAULT 0",
        "verified_at": "DATETIME NULL",
        "last_login_at": "DATETIME NULL",
        "last_login_ip": "VARCHAR(45) NULL",
        "login_count": "INT NOT NULL DEFAULT 0",
        "queue_index": "INT NOT NULL DEFAULT 0",
    },
    "artists": {
        "spotify_id": "VARCHAR(40) NULL",
        "image_url": "VARCHAR(500) NULL",
    },
    "albums": {
        "spotify_id": "VARCHAR(40) NULL",
        "image_url": "VARCHAR(500) NULL",
    },
    "songs": {
        "spotify_id": "VARCHAR(40) NULL",
        "spotify_uri": "VARCHAR(80) NULL",
        "explicit": "TINYINT(1) NOT NULL DEFAULT 0",
        "popularity": "INT NOT NULL DEFAULT 0",
    },
    "playlists": {
        "image_url": "VARCHAR(500) NULL",
        "updated_at": "DATETIME NULL",
    },
}

# table -> (index name, DDL)
NEW_INDEXES = [
    ("users", "ix_users_staff_code", "CREATE UNIQUE INDEX ix_users_staff_code "
                                     "ON users (staff_code)"),
    ("artists", "ix_artists_spotify_id", "CREATE UNIQUE INDEX ix_artists_spotify_id "
                                         "ON artists (spotify_id)"),
    ("albums", "ix_albums_spotify_id", "CREATE UNIQUE INDEX ix_albums_spotify_id "
                                       "ON albums (spotify_id)"),
    ("songs", "ix_songs_spotify_id", "CREATE UNIQUE INDEX ix_songs_spotify_id "
                                     "ON songs (spotify_id)"),
]


def add_missing_columns(inspector):
    added = 0
    for table, columns in NEW_COLUMNS.items():
        if table not in inspector.get_table_names():
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, ddl in columns.items():
            if name in existing:
                continue
            db.session.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{name}` {ddl}"))
            print(f"  + {table}.{name}")
            added += 1
    db.session.commit()
    return added


def add_missing_indexes(inspector):
    added = 0
    for table, name, ddl in NEW_INDEXES:
        if table not in inspector.get_table_names():
            continue
        existing = {i["name"] for i in inspector.get_indexes(table)}
        if name in existing:
            continue
        try:
            db.session.execute(text(ddl))
            print(f"  + index {name}")
            added += 1
        except Exception as exc:                    # noqa: BLE001
            db.session.rollback()
            print(f"  ! could not create {name}: {exc}")
    db.session.commit()
    return added


def backfill():
    """Existing accounts predate verification, so grandfather them in."""
    updated = db.session.execute(text(
        "UPDATE users SET is_verified = 1, verified_at = COALESCE(verified_at, created_at) "
        "WHERE is_verified = 0"
    )).rowcount
    db.session.execute(text(
        "UPDATE users SET status = 'active' WHERE status IS NULL OR status = 'pending'"))
    db.session.execute(text(
        "UPDATE users SET role = 'admin' WHERE is_admin = 1 AND role <> 'admin'"))
    db.session.execute(text(
        "UPDATE users SET role = 'staff' WHERE role IS NULL OR role = ''"))
    db.session.commit()

    # Staff codes for anyone who doesn't have one yet.
    coded = 0
    for user in User.query.filter(
            (User.staff_code.is_(None)) | (User.staff_code == "")).all():
        user.staff_code = f"EM-{user.id:04d}"
        coded += 1
    db.session.commit()

    print(f"  verified {updated} existing account(s), assigned {coded} staff code(s)")


def ensure_admin(username=None, password=None):
    if User.query.filter_by(is_admin=True).count():
        print("  an administrator already exists")
        return

    print("\nNo administrator found — let's create one.")
    username = username or input("  username [admin]: ").strip() or "admin"
    email = input(f"  e-mail [{username}@eliteminus.local]: ").strip() \
        or f"{username}@eliteminus.local"
    while not password or len(password) < 8:
        password = getpass.getpass("  password (min 8 chars): ")

    existing = User.query.filter_by(username=username).first()
    if existing:
        existing.is_admin = True
        existing.role = "admin"
        existing.status = "active"
        existing.is_verified = True
        existing.set_password(password)
        print(f"  promoted existing user '{username}' to administrator")
    else:
        user = User(username=username, email=email, display_name=username,
                    role="admin", is_admin=True, status="active",
                    is_verified=True, verified_at=utcnow())
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        user.assign_staff_code()
        print(f"  created administrator '{username}'")
    db.session.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-user", help="username for the admin account")
    parser.add_argument("--admin-password", help="password for the admin account")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        print("Migrating database...")
        print("  creating any missing tables")
        db.create_all()

        inspector = inspect(db.engine)
        columns = add_missing_columns(inspector)
        indexes = add_missing_indexes(inspect(db.engine))
        if not columns:
            print("  no new columns needed")
        if not indexes:
            print("  no new indexes needed")

        backfill()
        ensure_admin(args.admin_user, args.admin_password)

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
