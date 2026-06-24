"""SQLAlchemy models for the Spotify-style app.

The schema mirrors the core Spotify domain: users, artists, albums, songs,
playlists, plus the join tables that power "liked songs", "followed artists",
playlist membership and play history.
"""
from datetime import datetime, timezone

from flask import url_for
from flask_login import UserMixin

from extensions import bcrypt, db, login_manager


def utcnow():
    """Timezone-aware UTC timestamp (datetime.utcnow is deprecated)."""
    return datetime.now(timezone.utc)


def cover_url(seed, size=300):
    """URL of the generated gradient cover SVG for a given seed string."""
    return url_for("api.cover", seed=seed or "music", size=size)


# --------------------------------------------------------------------------
# Association tables / objects
# --------------------------------------------------------------------------
followed_artists = db.Table(
    "followed_artists",
    db.Column("user_id", db.Integer,
              db.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    db.Column("artist_id", db.Integer,
              db.ForeignKey("artists.id", ondelete="CASCADE"), primary_key=True),
    db.Column("followed_at", db.DateTime, default=utcnow),
)


class LikedSong(db.Model):
    """A user's liked/saved song (kept as an object so we can order by date)."""
    __tablename__ = "liked_songs"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey("songs.id", ondelete="CASCADE"),
                        primary_key=True)
    liked_at = db.Column(db.DateTime, default=utcnow, index=True)

    song = db.relationship("Song")


class PlaylistSong(db.Model):
    """Ordered membership of a song within a playlist."""
    __tablename__ = "playlist_songs"

    playlist_id = db.Column(db.Integer,
                            db.ForeignKey("playlists.id", ondelete="CASCADE"),
                            primary_key=True)
    song_id = db.Column(db.Integer,
                        db.ForeignKey("songs.id", ondelete="CASCADE"),
                        primary_key=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    added_at = db.Column(db.DateTime, default=utcnow)

    song = db.relationship("Song")


class PlayHistory(db.Model):
    """Every play event, used for 'Recently played'."""
    __tablename__ = "play_history"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        index=True)
    song_id = db.Column(db.Integer, db.ForeignKey("songs.id", ondelete="CASCADE"))
    played_at = db.Column(db.DateTime, default=utcnow, index=True)

    song = db.relationship("Song")


# --------------------------------------------------------------------------
# Core entities
# --------------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(80))
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    playlists = db.relationship("Playlist", back_populates="owner",
                                cascade="all, delete-orphan")
    follows = db.relationship("Artist", secondary=followed_artists,
                              backref="followers")

    # --- password helpers ---
    def set_password(self, raw):
        self.password_hash = bcrypt.generate_password_hash(raw).decode("utf-8")

    def check_password(self, raw):
        return bcrypt.check_password_hash(self.password_hash, raw)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name or self.username,
            "is_admin": bool(self.is_admin),
            "image": cover_url(self.display_name or self.username),
        }


class Artist(db.Model):
    __tablename__ = "artists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    bio = db.Column(db.Text)
    genre = db.Column(db.String(60))
    monthly_listeners = db.Column(db.Integer, default=0)
    image_seed = db.Column(db.String(120))

    albums = db.relationship("Album", back_populates="artist",
                             cascade="all, delete-orphan")
    songs = db.relationship("Song", back_populates="artist",
                            cascade="all, delete-orphan")

    def to_dict(self, full=False):
        data = {
            "id": self.id,
            "type": "artist",
            "name": self.name,
            "genre": self.genre,
            "monthly_listeners": self.monthly_listeners,
            "image": cover_url(self.image_seed or self.name),
        }
        if full:
            data["bio"] = self.bio
            data["follower_count"] = len(self.followers)
        return data


class Album(db.Model):
    __tablename__ = "albums"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, index=True)
    artist_id = db.Column(db.Integer,
                          db.ForeignKey("artists.id", ondelete="CASCADE"))
    release_date = db.Column(db.Date)
    cover_seed = db.Column(db.String(120))

    artist = db.relationship("Artist", back_populates="albums")
    songs = db.relationship("Song", back_populates="album",
                            cascade="all, delete-orphan",
                            order_by="Song.track_number")

    def to_dict(self, with_tracks=False, liked_ids=None):
        data = {
            "id": self.id,
            "type": "album",
            "title": self.title,
            "artist": {"id": self.artist.id, "name": self.artist.name},
            "year": self.release_date.year if self.release_date else None,
            "image": cover_url(self.cover_seed or self.title),
            "song_count": len(self.songs),
        }
        if with_tracks:
            data["tracks"] = [s.to_dict(liked_ids=liked_ids) for s in self.songs]
        return data


class Song(db.Model):
    __tablename__ = "songs"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False, index=True)
    artist_id = db.Column(db.Integer,
                          db.ForeignKey("artists.id", ondelete="CASCADE"))
    album_id = db.Column(db.Integer,
                         db.ForeignKey("albums.id", ondelete="SET NULL"))
    track_number = db.Column(db.Integer, default=1)
    duration = db.Column(db.Integer, default=0)        # seconds
    audio_url = db.Column(db.String(500), nullable=False)
    play_count = db.Column(db.Integer, default=0)

    artist = db.relationship("Artist", back_populates="songs")
    album = db.relationship("Album", back_populates="songs")

    def to_dict(self, liked_ids=None):
        seed = self.album.cover_seed if self.album else self.title
        return {
            "id": self.id,
            "type": "song",
            "title": self.title,
            "artist": {"id": self.artist.id, "name": self.artist.name},
            "album": ({"id": self.album.id, "title": self.album.title}
                      if self.album else None),
            "track_number": self.track_number,
            "duration": self.duration,
            "audio_url": self.audio_url,
            "play_count": self.play_count,
            "image": cover_url(seed),
            "liked": bool(liked_ids and self.id in liked_ids),
        }


class Playlist(db.Model):
    __tablename__ = "playlists"

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                         index=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300))
    cover_seed = db.Column(db.String(120))
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    owner = db.relationship("User", back_populates="playlists")
    items = db.relationship("PlaylistSong", cascade="all, delete-orphan",
                            order_by="PlaylistSong.position",
                            backref="playlist")

    @property
    def songs(self):
        return [item.song for item in self.items]

    def to_dict(self, with_tracks=False, liked_ids=None):
        songs = self.songs
        data = {
            "id": self.id,
            "type": "playlist",
            "name": self.name,
            "description": self.description,
            "owner": {"id": self.owner.id,
                      "name": self.owner.display_name or self.owner.username}
            if self.owner else None,
            "is_public": self.is_public,
            "image": cover_url(self.cover_seed or self.name),
            "song_count": len(songs),
            "total_duration": sum(s.duration for s in songs),
        }
        if with_tracks:
            data["tracks"] = [s.to_dict(liked_ids=liked_ids) for s in songs]
        return data


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
