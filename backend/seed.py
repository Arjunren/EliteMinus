"""Create the tables and populate them with sample data.

    python seed.py            # keep existing data, only add what's missing
    python seed.py --reset    # DROP every table first, then rebuild

On PythonAnywhere the database already exists (you create it in the Databases
tab), so ``--reset`` is the only destructive part — use it deliberately.

Accounts created:
    admin / Admin@12345     -> the admin panel at /admin
    demo  / Demo@12345      -> an ordinary listener
    user  / User@12345      -> verified listener for quick sign-in tests
"""
import argparse
import random
from datetime import date, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app import create_app
from config import Config
from extensions import db
from models import (Album, Artist, LikedSong, PlayHistory, Playlist,
                    PlaylistSong, Song, User, utcnow)

random.seed(42)  # reproducible sample data

# Royalty-free demo audio (streams from soundhelix.com — needs internet).
SOUNDHELIX = [
    f"https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{i}.mp3"
    for i in range(1, 17)
]

DEPARTMENTS = ["Operations", "Content", "Support", "Engineering"]

# ---- Catalog: artists -> albums -> track titles --------------------------
CATALOG = [
    {
        "name": "Aurora Skies", "genre": "Indie Pop",
        "bio": "Dreamy indie-pop built on shimmering synths and soaring vocals.",
        "albums": [
            ("Northern Lights", 2021,
             ["Polar", "Glow", "Midnight Sun", "Drift", "Ember"]),
            ("Daybreak", 2023,
             ["Sunrise", "Golden Hour", "Horizon", "Warmth"]),
        ],
    },
    {
        "name": "Neon Pulse", "genre": "Electronic",
        "bio": "High-voltage electronic music for late nights and bright lights.",
        "albums": [
            ("Voltage", 2020,
             ["Circuit", "Static", "Overdrive", "Synthwave", "Pulse"]),
            ("Afterglow", 2022,
             ["Neon", "Lasers", "Reflections", "Echoes"]),
        ],
    },
    {
        "name": "The Wanderers", "genre": "Indie Rock",
        "bio": "Road-trip indie rock with big guitars and bigger choruses.",
        "albums": [
            ("Roads", 2019,
             ["Highway", "Compass", "Lost and Found", "Anchor"]),
            ("Restless", 2022,
             ["Wander", "Fading Town", "Open Sky", "Rust"]),
        ],
    },
    {
        "name": "Velvet Moon", "genre": "R&B",
        "bio": "Smooth, late-night R&B and soul drenched in velvet.",
        "albums": [
            ("Silk", 2021,
             ["Velvet", "Smooth", "Honey", "Slow Dance", "Moonlight"]),
            ("Midnight", 2023, ["Crave", "Linger", "Closer"]),
        ],
    },
    {
        "name": "Cosmic Drift", "genre": "Lo-fi",
        "bio": "Chilled lo-fi soundscapes for focus, study and stargazing.",
        "albums": [
            ("Orbit", 2020,
             ["Float", "Nebula", "Gravity", "Stardust", "Meteor"]),
            ("Stillness", 2022, ["Calm", "Breathe", "Drizzle", "Haze"]),
        ],
    },
    {
        "name": "Iron Verdict", "genre": "Rock",
        "bio": "Hard-hitting rock anthems forged in steel and thunder.",
        "albums": [
            ("Forged", 2018, ["Hammer", "Thunder", "Rebellion", "Steel"]),
            ("Uprising", 2021, ["Riot", "Ashes", "Warpath", "Defiance"]),
        ],
    },
    {
        "name": "Sahara Bloom", "genre": "World",
        "bio": "Lush world-fusion blending desert rhythms with modern grooves.",
        "albums": [
            ("Mirage", 2020, ["Dunes", "Oasis", "Caravan", "Sandstorm"]),
            ("Bloom", 2022, ["Jasmine", "Henna", "Monsoon"]),
        ],
    },
    {
        "name": "Echo Lake", "genre": "Folk",
        "bio": "Warm acoustic folk songs from a cabin by the water.",
        "albums": [
            ("Cabin", 2019, ["Pinewood", "Lantern", "River Song", "Firewood"]),
            ("Seasons", 2023,
             ["Autumn Leaves", "First Snow", "Spring Thaw", "Summer Rain"]),
        ],
    },
]

PLAYLISTS = [
    ("Today's Top Hits", "The biggest tracks right now.", "TOP"),
    ("Chill Vibes", "Kick back and relax.", ["Lo-fi", "R&B", "Folk"]),
    ("Rock Anthems", "Turn it up to eleven.", ["Rock", "Indie Rock"]),
    ("Electronic Energy", "Synths, beats and neon nights.", ["Electronic", "Lo-fi"]),
    ("Indie Mix", "Fresh indie picks for your day.",
     ["Indie Pop", "Indie Rock", "Folk"]),
    ("Global Grooves", "Sounds from around the world.",
     ["World", "R&B", "Electronic"]),
]


def ensure_database():
    """Create the database if the server lets us (local XAMPP only).

    On PythonAnywhere the database is created for you in the web UI and the
    account has no CREATE DATABASE privilege, so a failure here is expected
    and harmless.
    """
    server_uri = (
        f"mysql+pymysql://{Config.DB_USER}:{Config.DB_PASSWORD}"
        f"@{Config.DB_HOST}:{Config.DB_PORT}/?charset=utf8mb4"
    )
    try:
        engine = create_engine(server_uri)
        with engine.connect() as conn:
            conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            ))
        engine.dispose()
        print(f"  database `{Config.DB_NAME}` is ready")
    except OperationalError as exc:
        print(f"  skipping CREATE DATABASE ({exc.orig.args[-1] if exc.orig else exc})")
        print("  -> assuming the database already exists (normal on PythonAnywhere)")


def make_user(username, email, password, **kwargs):
    """Create a fully verified, active account."""
    user = User(username=username, email=email,
                display_name=kwargs.pop("display_name", username),
                is_verified=True, verified_at=utcnow(),
                status=kwargs.pop("status", "active"),
                role=kwargs.pop("role", "staff"),
                hire_date=kwargs.pop("hire_date", date.today()),
                **kwargs)
    user.is_admin = user.role == "admin"
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    user.assign_staff_code()
    return user


def build_catalog():
    """Insert artists, albums and songs. Returns the flat list of songs."""
    all_songs = []
    audio_i = 0
    for spec in CATALOG:
        artist = Artist(
            name=spec["name"], genre=spec["genre"], bio=spec["bio"],
            image_seed=spec["name"],
            monthly_listeners=random.randint(150_000, 9_000_000),
        )
        db.session.add(artist)
        db.session.flush()

        for title, year, tracks in spec["albums"]:
            album = Album(
                title=title, artist_id=artist.id, cover_seed=title,
                release_date=date(year, random.randint(1, 12),
                                  random.randint(1, 28)),
            )
            db.session.add(album)
            db.session.flush()

            for n, track_title in enumerate(tracks, start=1):
                song = Song(
                    title=track_title, artist_id=artist.id, album_id=album.id,
                    track_number=n,
                    duration=random.randint(150, 268),
                    audio_url=SOUNDHELIX[audio_i % len(SOUNDHELIX)],
                    play_count=random.randint(1_000, 1_500_000),
                )
                audio_i += 1
                db.session.add(song)
                all_songs.append(song)

    db.session.flush()
    return all_songs


def build_playlists(system_user, songs):
    by_genre = {}
    for s in songs:
        by_genre.setdefault(s.artist.genre, []).append(s)

    for name, desc, rule in PLAYLISTS:
        pl = Playlist(owner_id=system_user.id, name=name, description=desc,
                      cover_seed=name, is_public=True)
        db.session.add(pl)
        db.session.flush()

        if rule == "TOP":
            picks = sorted(songs, key=lambda s: s.play_count, reverse=True)[:12]
        else:
            pool = [s for g in rule for s in by_genre.get(g, [])]
            random.shuffle(pool)
            picks = pool[:12]

        for pos, song in enumerate(picks, start=1):
            db.session.add(PlaylistSong(playlist_id=pl.id, song_id=song.id,
                                        position=pos))
    db.session.flush()


def build_demo_user(songs):
    demo = make_user("demo", "demo@demo.com", "Demo@12345",
                     display_name="Demo Listener", department="Operations",
                     position="Staff", full_name="Demo Listener")

    pl = Playlist(owner_id=demo.id, name="Demo's Favourites",
                  description="A few tracks I keep coming back to.",
                  cover_seed="Demo's Favourites", is_public=True)
    db.session.add(pl)
    db.session.flush()
    for pos, song in enumerate(random.sample(songs, 8), start=1):
        db.session.add(PlaylistSong(playlist_id=pl.id, song_id=song.id,
                                    position=pos))

    for song in random.sample(songs, 12):
        db.session.add(LikedSong(user_id=demo.id, song_id=song.id))

    now = utcnow()
    for i, song in enumerate(random.sample(songs, 10)):
        db.session.add(PlayHistory(
            user_id=demo.id, song_id=song.id,
            played_at=now - timedelta(hours=i * 5 + random.randint(0, 4)),
        ))

    artist_ids = list({s.artist_id for s in songs})
    for aid in random.sample(artist_ids, 3):
        demo.follows.append(db.session.get(Artist, aid))

    db.session.flush()
    return demo


def build_default_user():
    """Create a ready-to-use listener account without an OTP challenge.

    This is test data for a freshly seeded development database.  The account
    is deliberately marked verified, so its first login works immediately.
    """
    return make_user(
        "user", "user@eliteminus.local", "User@12345",
        display_name="Default User", full_name="Default Test User",
        department="Listener", position="Listener",
    )


def build_sample_staff():
    """A handful of staff records so the admin panel isn't empty."""
    people = [
        ("m.santos", "Maria Santos", "manager", "active", "Content", "Content Lead"),
        ("j.cruz", "Jose Cruz", "staff", "active", "Support", "Support Agent"),
        ("a.reyes", "Ana Reyes", "staff", "pending", "Operations", "Coordinator"),
        ("r.dela", "Rico Dela Cruz", "staff", "suspended", "Engineering",
         "Junior Developer"),
    ]
    for username, full_name, role, status, dept, position in people:
        user = make_user(username, f"{username}@eliteminus.local", "Staff@12345",
                         display_name=full_name.split()[0], full_name=full_name,
                         role=role, status=status, department=dept,
                         position=position,
                         hire_date=date.today() - timedelta(
                             days=random.randint(30, 900)))
        if status == "pending":
            user.is_verified = False
            user.verified_at = None
    db.session.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true",
                        help="drop every table before rebuilding")
    args = parser.parse_args()

    print("Setting up the database...")
    ensure_database()

    app = create_app()
    with app.app_context():
        if args.reset:
            print("  dropping all tables")
            db.drop_all()
        print("  creating tables")
        db.create_all()

        if User.query.count():
            print("\nTables already contain accounts — nothing to seed.")
            print("Run  python seed.py --reset  to wipe and start over.")
            return

        # System account that owns the curated public playlists.
        system = make_user("curator", "curator@eliteminus.local",
                           "not-a-login-" + str(random.random()),
                           display_name="EliteMinus", status="suspended",
                           department="Content", position="System account")

        admin = make_user("admin", "admin@eliteminus.local", "Admin@12345",
                          display_name="Administrator", full_name="System Admin",
                          role="admin", department="Operations",
                          position="Administrator")

        print("  inserting catalog (artists, albums, songs)")
        songs = build_catalog()
        print(f"    -> {len(songs)} songs")

        print("  building curated playlists")
        build_playlists(system, songs)

        print("  creating demo/default listeners + sample staff")
        build_demo_user(songs)
        build_default_user()
        build_sample_staff()

        db.session.commit()
        print(f"    -> {User.query.count()} accounts (admin: {admin.username})")

    print("\nDone!  Start the app with:  python app.py")
    print("  Admin panel   http://localhost:5000/admin   admin / Admin@12345")
    print("  Listener app  http://localhost:5000/app/    demo  / Demo@12345")
    print("  Test listener http://localhost:5000/app/    user  / User@12345 (OTP already verified)")


if __name__ == "__main__":
    main()
