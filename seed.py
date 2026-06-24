"""Create the database + tables and populate them with sample data.

Run once after starting MySQL in XAMPP:

    python seed.py

It will:
  1. CREATE DATABASE `spotify_clone` if it doesn't exist
  2. Drop & recreate all tables (clean slate)
  3. Insert artists, albums, songs, public playlists and a demo account

Demo login ->  username: demo   password: demo12345
"""
import random
from datetime import date, timedelta

from sqlalchemy import create_engine, text

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
            ("Midnight", 2023,
             ["Crave", "Linger", "Closer"]),
        ],
    },
    {
        "name": "Cosmic Drift", "genre": "Lo-fi",
        "bio": "Chilled lo-fi soundscapes for focus, study and stargazing.",
        "albums": [
            ("Orbit", 2020,
             ["Float", "Nebula", "Gravity", "Stardust", "Meteor"]),
            ("Stillness", 2022,
             ["Calm", "Breathe", "Drizzle", "Haze"]),
        ],
    },
    {
        "name": "Iron Verdict", "genre": "Rock",
        "bio": "Hard-hitting rock anthems forged in steel and thunder.",
        "albums": [
            ("Forged", 2018,
             ["Hammer", "Thunder", "Rebellion", "Steel"]),
            ("Uprising", 2021,
             ["Riot", "Ashes", "Warpath", "Defiance"]),
        ],
    },
    {
        "name": "Sahara Bloom", "genre": "World",
        "bio": "Lush world-fusion blending desert rhythms with modern grooves.",
        "albums": [
            ("Mirage", 2020,
             ["Dunes", "Oasis", "Caravan", "Sandstorm"]),
            ("Bloom", 2022,
             ["Jasmine", "Henna", "Monsoon"]),
        ],
    },
    {
        "name": "Echo Lake", "genre": "Folk",
        "bio": "Warm acoustic folk songs from a cabin by the water.",
        "albums": [
            ("Cabin", 2019,
             ["Pinewood", "Lantern", "River Song", "Firewood"]),
            ("Seasons", 2023,
             ["Autumn Leaves", "First Snow", "Spring Thaw", "Summer Rain"]),
        ],
    },
]

# ---- Curated public playlists: name -> (description, [genres or artists]) -
PLAYLISTS = [
    ("Today's Top Hits", "The biggest tracks right now.", "TOP"),
    ("Chill Vibes", "Kick back and relax.", ["Lo-fi", "R&B", "Folk"]),
    ("Rock Anthems", "Turn it up to eleven.", ["Rock", "Indie Rock"]),
    ("Electronic Energy", "Synths, beats and neon nights.", ["Electronic", "Lo-fi"]),
    ("Indie Mix", "Fresh indie picks for your day.", ["Indie Pop", "Indie Rock", "Folk"]),
    ("Global Grooves", "Sounds from around the world.", ["World", "R&B", "Electronic"]),
]


def ensure_database():
    """Connect to the MySQL server (no DB) and create the database."""
    server_uri = (
        f"mysql+pymysql://{Config.DB_USER}:{Config.DB_PASSWORD}"
        f"@{Config.DB_HOST}:{Config.DB_PORT}/?charset=utf8mb4"
    )
    engine = create_engine(server_uri)
    with engine.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{Config.DB_NAME}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
    engine.dispose()
    print(f"  database `{Config.DB_NAME}` is ready")


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
    demo = User(username="demo", email="demo@demo.com",
                display_name="Demo Listener")
    demo.set_password("demo12345")
    db.session.add(demo)
    db.session.flush()

    # A personal playlist
    pl = Playlist(owner_id=demo.id, name="Demo's Favourites",
                  description="A few tracks I keep coming back to.",
                  cover_seed="Demo's Favourites", is_public=True)
    db.session.add(pl)
    db.session.flush()
    for pos, song in enumerate(random.sample(songs, 8), start=1):
        db.session.add(PlaylistSong(playlist_id=pl.id, song_id=song.id,
                                    position=pos))

    # Liked songs
    for song in random.sample(songs, 12):
        db.session.add(LikedSong(user_id=demo.id, song_id=song.id))

    # Recently played history (spread over the last few days)
    now = utcnow()
    for i, song in enumerate(random.sample(songs, 10)):
        db.session.add(PlayHistory(
            user_id=demo.id, song_id=song.id,
            played_at=now - timedelta(hours=i * 5 + random.randint(0, 4)),
        ))

    # Follow a couple of artists
    artist_ids = list({s.artist_id for s in songs})
    for aid in random.sample(artist_ids, 3):
        demo.follows.append(db.session.get(Artist, aid))

    db.session.flush()
    return demo


def main():
    print("Setting up the database...")
    ensure_database()

    app = create_app()
    with app.app_context():
        print("  dropping & creating tables")
        db.drop_all()
        db.create_all()

        # System account that owns the curated public playlists.
        system = User(username="spotify", email="curator@spotify.local",
                      display_name="Spotify")
        system.set_password("not-a-login-account-" + str(random.random()))
        db.session.add(system)
        db.session.flush()

        # Admin account for the admin panel.
        admin = User(username="admin", email="admin@admin.com",
                     display_name="Admin", is_admin=True)
        admin.set_password("admin12345")
        db.session.add(admin)
        db.session.flush()

        print("  inserting catalog (artists, albums, songs)")
        songs = build_catalog()
        print(f"    -> {len(songs)} songs")

        print("  building curated playlists")
        build_playlists(system, songs)

        print("  creating demo user + library")
        build_demo_user(songs)

        db.session.commit()

    print("\nDone!")
    print("Start the app with:  python app.py")
    print("Listener login at http://localhost:5000  ->  demo / demo12345")
    print("Admin panel  at http://localhost:5000/admin  ->  admin / admin12345")


if __name__ == "__main__":
    main()
