"""SQLAlchemy models.

Two domains live side by side:

* **Staff** — the ``User`` table doubles as the staff directory (role, status,
  department, contact details) that the admin panel manages.
* **Music** — artists, albums, songs, playlists, likes, follows, play history
  and the persistent per-user playback queue.
"""
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, url_for
from flask_login import UserMixin

from extensions import bcrypt, db, login_manager


def utcnow():
    """Timezone-aware UTC timestamp (datetime.utcnow is deprecated)."""
    return datetime.now(timezone.utc)


def _aware(dt):
    """MySQL hands datetimes back naive; treat those as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def cover_url(seed, size=300):
    """URL of the generated gradient cover SVG for a given seed string."""
    return url_for("api.cover", seed=seed or "music", size=size,
                   _external=True)


# Staff roles, most privileged first. ``admin`` is the only role that can
# reach the admin panel; the rest are ordinary app accounts.
ROLES = ("admin", "manager", "staff")
STATUSES = ("pending", "active", "suspended")


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


class QueueItem(db.Model):
    """The playback queue, stored per user so it survives a reload or a
    device switch.  ``source`` distinguishes tracks the user queued by hand
    ("manual") from the rest of the context that was playing ("context")."""
    __tablename__ = "queue_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        index=True, nullable=False)
    song_id = db.Column(db.Integer, db.ForeignKey("songs.id", ondelete="CASCADE"),
                        nullable=False)
    position = db.Column(db.Integer, nullable=False, default=0, index=True)
    source = db.Column(db.String(20), nullable=False, default="context")
    added_at = db.Column(db.DateTime, default=utcnow)

    song = db.relationship("Song")


# --------------------------------------------------------------------------
# Staff / accounts
# --------------------------------------------------------------------------
class User(UserMixin, db.Model):
    """An account.  Also the staff record the admin panel manages."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(80))
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    # --- staff directory fields ---
    staff_code = db.Column(db.String(20), unique=True, index=True)
    full_name = db.Column(db.String(120))
    role = db.Column(db.String(20), nullable=False, default="staff")
    status = db.Column(db.String(20), nullable=False, default="pending")
    department = db.Column(db.String(80))
    position = db.Column(db.String(80))
    phone = db.Column(db.String(40))
    hire_date = db.Column(db.Date)
    notes = db.Column(db.Text)

    # --- verification / sign-in tracking ---
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    verified_at = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)
    last_login_ip = db.Column(db.String(45))
    login_count = db.Column(db.Integer, nullable=False, default=0)

    # Where the user is inside their saved queue (see ``QueueItem``).
    queue_index = db.Column(db.Integer, nullable=False, default=0)

    playlists = db.relationship("Playlist", back_populates="owner",
                                cascade="all, delete-orphan")
    follows = db.relationship("Artist", secondary=followed_artists,
                              backref="followers")

    # --- password helpers ---
    def set_password(self, raw):
        self.password_hash = bcrypt.generate_password_hash(raw).decode("utf-8")

    def check_password(self, raw):
        return bcrypt.check_password_hash(self.password_hash, raw)

    # --- state helpers ---
    @property
    def is_active(self):
        """Flask-Login refuses to log in accounts where this is False."""
        return self.status != "suspended" and self.is_verified

    @property
    def can_admin(self):
        return bool(self.is_admin) and self.status == "active"

    def assign_staff_code(self):
        """EM-0001, EM-0002, … — assigned once, on creation."""
        if self.staff_code:
            return self.staff_code
        last = (db.session.query(db.func.max(User.id)).scalar() or 0) + 1
        self.staff_code = f"EM-{last:04d}"
        return self.staff_code

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name or self.username,
            "full_name": self.full_name,
            "is_admin": bool(self.is_admin),
            "role": self.role,
            "status": self.status,
            "department": self.department,
            "position": self.position,
            "staff_code": self.staff_code,
            "image": cover_url(self.display_name or self.username),
        }

    def to_staff_dict(self):
        """The richer shape the admin panel's staff table renders."""
        data = self.to_dict()
        data.update({
            "phone": self.phone,
            "hire_date": self.hire_date.isoformat() if self.hire_date else None,
            "notes": self.notes,
            "is_verified": bool(self.is_verified),
            "created_at": self.created_at.strftime("%Y-%m-%d")
            if self.created_at else "",
            "last_login_at": self.last_login_at.strftime("%Y-%m-%d %H:%M")
            if self.last_login_at else "",
            "login_count": self.login_count or 0,
            "playlists": Playlist.query.filter_by(owner_id=self.id).count(),
            "likes": LikedSong.query.filter_by(user_id=self.id).count(),
        })
        return data


class EmailOTP(db.Model):
    """A one-time code e-mailed to a user.

    Only the hash of the code is stored, so a database dump never leaks a
    usable code.  ``purpose`` lets the same table serve sign-up verification
    and any future flows (e.g. an e-mail change).
    """
    __tablename__ = "email_otps"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    purpose = db.Column(db.String(30), nullable=False, default="register")
    code_hash = db.Column(db.String(255), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    consumed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    @property
    def is_expired(self):
        return utcnow() >= _aware(self.expires_at)

    @property
    def is_usable(self):
        max_attempts = current_app.config["OTP_MAX_ATTEMPTS"]
        return (self.consumed_at is None and not self.is_expired
                and self.attempts < max_attempts)

    def seconds_until_resend(self):
        cooldown = current_app.config["OTP_RESEND_SECONDS"]
        elapsed = (utcnow() - _aware(self.created_at)).total_seconds()
        return max(0, int(cooldown - elapsed))


class AuditLog(db.Model):
    """Who did what in the admin panel — shown on the dashboard."""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer,
                         db.ForeignKey("users.id", ondelete="SET NULL"))
    actor_name = db.Column(db.String(80))      # kept even if the actor is deleted
    action = db.Column(db.String(60), nullable=False)
    target = db.Column(db.String(160))
    detail = db.Column(db.String(400))
    ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "actor": self.actor_name or "—",
            "action": self.action,
            "target": self.target or "",
            "detail": self.detail or "",
            "at": self.created_at.strftime("%Y-%m-%d %H:%M")
            if self.created_at else "",
        }


class SpotifyAccount(db.Model):
    """A user's linked Spotify account, for Web Playback SDK streaming."""
    __tablename__ = "spotify_accounts"

    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        primary_key=True)
    spotify_user_id = db.Column(db.String(120))
    display_name = db.Column(db.String(120))
    product = db.Column(db.String(20))          # "premium" | "free"
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text)
    expires_at = db.Column(db.DateTime, nullable=False)
    scope = db.Column(db.String(500))
    linked_at = db.Column(db.DateTime, default=utcnow)

    @property
    def is_expired(self):
        # Refresh a minute early so a request never races the expiry.
        return utcnow() >= _aware(self.expires_at) - timedelta(seconds=60)


class OAuthState(db.Model):
    """Short-lived PKCE state for the Spotify authorisation-code flow."""
    __tablename__ = "oauth_states"

    state = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"))
    code_verifier = db.Column(db.String(128), nullable=False)
    return_to = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=utcnow, index=True)

    @staticmethod
    def new_state():
        return secrets.token_urlsafe(32)[:64]


# --------------------------------------------------------------------------
# Music catalog
# --------------------------------------------------------------------------
class Artist(db.Model):
    __tablename__ = "artists"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    bio = db.Column(db.Text)
    genre = db.Column(db.String(60))
    monthly_listeners = db.Column(db.Integer, default=0)
    image_seed = db.Column(db.String(120))

    # --- Spotify provenance ---
    spotify_id = db.Column(db.String(40), unique=True, index=True)
    image_url = db.Column(db.String(500))

    albums = db.relationship("Album", back_populates="artist",
                             cascade="all, delete-orphan")
    songs = db.relationship("Song", back_populates="artist",
                            cascade="all, delete-orphan")

    @property
    def image(self):
        return self.image_url or cover_url(self.image_seed or self.name)

    def to_dict(self, full=False):
        data = {
            "id": self.id,
            "type": "artist",
            "name": self.name,
            "genre": self.genre,
            "monthly_listeners": self.monthly_listeners,
            "image": self.image,
            "spotify_id": self.spotify_id,
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

    spotify_id = db.Column(db.String(40), unique=True, index=True)
    image_url = db.Column(db.String(500))

    artist = db.relationship("Artist", back_populates="albums")
    songs = db.relationship("Song", back_populates="album",
                            cascade="all, delete-orphan",
                            order_by="Song.track_number")

    @property
    def image(self):
        return self.image_url or cover_url(self.cover_seed or self.title)

    def to_dict(self, with_tracks=False, liked_ids=None):
        data = {
            "id": self.id,
            "type": "album",
            "title": self.title,
            "artist": {"id": self.artist.id, "name": self.artist.name}
            if self.artist else None,
            "year": self.release_date.year if self.release_date else None,
            "image": self.image,
            "song_count": len(self.songs),
            "spotify_id": self.spotify_id,
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
    audio_url = db.Column(db.String(500))              # mp3 / preview, may be null
    play_count = db.Column(db.Integer, default=0)

    # --- Spotify provenance ---
    # ``spotify_uri`` is what the Web Playback SDK plays for Premium users;
    # ``audio_url`` is the fallback <audio> source for everyone else.
    spotify_id = db.Column(db.String(40), unique=True, index=True)
    spotify_uri = db.Column(db.String(80))
    explicit = db.Column(db.Boolean, default=False)
    popularity = db.Column(db.Integer, default=0)

    artist = db.relationship("Artist", back_populates="songs")
    album = db.relationship("Album", back_populates="songs")

    @property
    def image(self):
        if self.album:
            return self.album.image
        return cover_url(self.title)

    def to_dict(self, liked_ids=None):
        return {
            "id": self.id,
            "type": "song",
            "title": self.title,
            "artist": {"id": self.artist.id, "name": self.artist.name}
            if self.artist else None,
            "album": ({"id": self.album.id, "title": self.album.title}
                      if self.album else None),
            "track_number": self.track_number,
            "duration": self.duration,
            "audio_url": self.audio_url,
            "spotify_uri": self.spotify_uri,
            "explicit": bool(self.explicit),
            "play_count": self.play_count,
            "image": self.image,
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
    image_url = db.Column(db.String(500))
    is_public = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    owner = db.relationship("User", back_populates="playlists")
    items = db.relationship("PlaylistSong", cascade="all, delete-orphan",
                            order_by="PlaylistSong.position",
                            backref="playlist")

    @property
    def songs(self):
        return [item.song for item in self.items if item.song]

    @property
    def image(self):
        return self.image_url or cover_url(self.cover_seed or self.name)

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
            "image": self.image,
            "song_count": len(songs),
            "total_duration": sum(s.duration or 0 for s in songs),
        }
        if with_tracks:
            data["tracks"] = [s.to_dict(liked_ids=liked_ids) for s in songs]
        return data


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
