"""Admin panel: a dashboard + CRUD for songs, artists, albums and users.

All routes require an authenticated user whose ``is_admin`` flag is set.
"""
import random
from datetime import timedelta
from functools import wraps

from flask import (Blueprint, jsonify, redirect, render_template, request,
                   url_for)
from flask_login import current_user
from sqlalchemy import func, or_

from extensions import db
from models import (Album, Artist, LikedSong, PlayHistory, Playlist, Song,
                    User, utcnow)

admin_bp = Blueprint("admin", __name__)

DEFAULT_AUDIO = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{}.mp3"


def admin_required(f):
    """Allow only logged-in admins. JSON 401/403 for the API, redirects for pages."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        is_api = request.path.startswith("/api/")
        if not current_user.is_authenticated:
            if is_api:
                return jsonify(error="authentication required"), 401
            return redirect(url_for("auth.login", next=request.path))
        if not current_user.is_admin:
            if is_api:
                return jsonify(error="admin access required"), 403
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return wrapper


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
@admin_bp.route("/admin")
@admin_required
def dashboard_page():
    return render_template("admin.html", user=current_user)


# --------------------------------------------------------------------------
# Dashboard stats / monitoring
# --------------------------------------------------------------------------
@admin_bp.route("/api/admin/stats")
@admin_required
def stats():
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    totals = {
        "users": User.query.count(),
        "songs": Song.query.count(),
        "artists": Artist.query.count(),
        "albums": Album.query.count(),
        "playlists": Playlist.query.count(),
        "likes": LikedSong.query.count(),
        "plays": int(db.session.query(
            func.coalesce(func.sum(Song.play_count), 0)).scalar() or 0),
        "play_events": PlayHistory.query.count(),
    }

    plays_today = PlayHistory.query.filter(PlayHistory.played_at >= today).count()
    plays_week = PlayHistory.query.filter(PlayHistory.played_at >= week_ago).count()

    top_songs = (Song.query.order_by(Song.play_count.desc()).limit(10).all())
    top_artists = (Artist.query
                   .order_by(Artist.monthly_listeners.desc()).limit(5).all())
    recent_users = (User.query.order_by(User.created_at.desc()).limit(6).all())
    recent_plays = (PlayHistory.query
                    .order_by(PlayHistory.played_at.desc()).limit(8).all())

    genres = (db.session.query(Artist.genre, func.count(Song.id))
              .join(Song, Song.artist_id == Artist.id)
              .group_by(Artist.genre).all())

    return jsonify({
        "totals": totals,
        "plays_today": plays_today,
        "plays_week": plays_week,
        "top_songs": [{"id": s.id, "title": s.title, "artist": s.artist.name,
                       "plays": s.play_count} for s in top_songs],
        "top_artists": [{"id": a.id, "name": a.name,
                         "monthly_listeners": a.monthly_listeners}
                        for a in top_artists],
        "recent_users": [{"id": u.id, "username": u.username,
                          "is_admin": bool(u.is_admin),
                          "created_at": u.created_at.strftime("%Y-%m-%d %H:%M")
                          if u.created_at else ""} for u in recent_users],
        "recent_plays": [{"song": p.song.title if p.song else "—",
                          "artist": p.song.artist.name if p.song else "",
                          "at": p.played_at.strftime("%Y-%m-%d %H:%M")
                          if p.played_at else ""} for p in recent_plays],
        "genres": [{"genre": g or "Unknown", "songs": c} for g, c in genres],
    })


# --------------------------------------------------------------------------
# Songs
# --------------------------------------------------------------------------
@admin_bp.route("/api/admin/songs", methods=["GET", "POST"])
@admin_required
def admin_songs():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        artist_id = data.get("artist_id")
        if not title:
            return jsonify(error="Title is required."), 400
        artist = db.session.get(Artist, artist_id) if artist_id else None
        if not artist:
            return jsonify(error="A valid artist is required."), 400

        album = None
        if data.get("album_id"):
            album = db.session.get(Album, data["album_id"])
            if album and album.artist_id != artist.id:
                return jsonify(error="That album belongs to a different artist."), 400

        audio = (data.get("audio_url") or "").strip() or \
            DEFAULT_AUDIO.format(random.randint(1, 16))
        try:
            duration = int(data.get("duration") or 200)
        except (TypeError, ValueError):
            duration = 200
        try:
            track_number = int(data.get("track_number") or 1)
        except (TypeError, ValueError):
            track_number = 1

        song = Song(title=title, artist_id=artist.id,
                    album_id=album.id if album else None,
                    audio_url=audio, duration=duration,
                    track_number=track_number, play_count=0)
        db.session.add(song)
        db.session.commit()
        return jsonify(_song_row(song)), 201

    # GET (optional ?q= search)
    q = (request.args.get("q") or "").strip()
    query = Song.query.join(Artist, Song.artist_id == Artist.id)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Song.title.ilike(like), Artist.name.ilike(like)))
    songs = query.order_by(Song.id.desc()).limit(300).all()
    return jsonify([_song_row(s) for s in songs])


@admin_bp.route("/api/admin/songs/<int:song_id>", methods=["PUT", "DELETE"])
@admin_required
def admin_song(song_id):
    song = Song.query.get_or_404(song_id)
    if request.method == "DELETE":
        db.session.delete(song)
        db.session.commit()
        return jsonify(deleted=True, id=song_id)

    data = request.get_json(silent=True) or {}
    if "title" in data and data["title"].strip():
        song.title = data["title"].strip()
    if data.get("artist_id"):
        artist = db.session.get(Artist, data["artist_id"])
        if artist:
            song.artist_id = artist.id
    if "album_id" in data:
        song.album_id = data["album_id"] or None
    if "audio_url" in data and data["audio_url"].strip():
        song.audio_url = data["audio_url"].strip()
    if "duration" in data:
        try:
            song.duration = int(data["duration"])
        except (TypeError, ValueError):
            pass
    db.session.commit()
    return jsonify(_song_row(song))


def _song_row(s):
    return {"id": s.id, "title": s.title,
            "artist": {"id": s.artist.id, "name": s.artist.name},
            "album": {"id": s.album.id, "title": s.album.title} if s.album else None,
            "duration": s.duration, "play_count": s.play_count,
            "audio_url": s.audio_url}


# --------------------------------------------------------------------------
# Artists
# --------------------------------------------------------------------------
@admin_bp.route("/api/admin/artists", methods=["GET", "POST"])
@admin_required
def admin_artists():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="Name is required."), 400
        try:
            listeners = int(data.get("monthly_listeners") or 0)
        except (TypeError, ValueError):
            listeners = 0
        artist = Artist(name=name, genre=(data.get("genre") or "").strip() or None,
                        bio=(data.get("bio") or "").strip() or None,
                        image_seed=name, monthly_listeners=listeners)
        db.session.add(artist)
        db.session.commit()
        return jsonify(_artist_row(artist)), 201

    artists = Artist.query.order_by(Artist.name).all()
    return jsonify([_artist_row(a) for a in artists])


@admin_bp.route("/api/admin/artists/<int:artist_id>", methods=["PUT", "DELETE"])
@admin_required
def admin_artist(artist_id):
    artist = Artist.query.get_or_404(artist_id)
    if request.method == "DELETE":
        db.session.delete(artist)        # cascades to albums + songs
        db.session.commit()
        return jsonify(deleted=True, id=artist_id)
    data = request.get_json(silent=True) or {}
    if data.get("name", "").strip():
        artist.name = data["name"].strip()
    if "genre" in data:
        artist.genre = (data["genre"] or "").strip() or None
    if "bio" in data:
        artist.bio = (data["bio"] or "").strip() or None
    if "monthly_listeners" in data:
        try:
            artist.monthly_listeners = int(data["monthly_listeners"])
        except (TypeError, ValueError):
            pass
    db.session.commit()
    return jsonify(_artist_row(artist))


def _artist_row(a):
    return {"id": a.id, "name": a.name, "genre": a.genre,
            "monthly_listeners": a.monthly_listeners,
            "albums": len(a.albums), "songs": len(a.songs)}


# --------------------------------------------------------------------------
# Albums
# --------------------------------------------------------------------------
@admin_bp.route("/api/admin/albums", methods=["GET", "POST"])
@admin_required
def admin_albums():
    if request.method == "POST":
        from datetime import date
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        artist = db.session.get(Artist, data.get("artist_id")) \
            if data.get("artist_id") else None
        if not title:
            return jsonify(error="Title is required."), 400
        if not artist:
            return jsonify(error="A valid artist is required."), 400
        release = None
        if data.get("year"):
            try:
                release = date(int(data["year"]), 1, 1)
            except (TypeError, ValueError):
                release = None
        album = Album(title=title, artist_id=artist.id, cover_seed=title,
                      release_date=release)
        db.session.add(album)
        db.session.commit()
        return jsonify(_album_row(album)), 201

    albums = Album.query.order_by(Album.title).all()
    return jsonify([_album_row(a) for a in albums])


@admin_bp.route("/api/admin/albums/<int:album_id>", methods=["DELETE"])
@admin_required
def admin_album(album_id):
    album = Album.query.get_or_404(album_id)
    db.session.delete(album)
    db.session.commit()
    return jsonify(deleted=True, id=album_id)


def _album_row(a):
    return {"id": a.id, "title": a.title,
            "artist": {"id": a.artist.id, "name": a.artist.name} if a.artist else None,
            "year": a.release_date.year if a.release_date else None,
            "songs": len(a.songs)}


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------
@admin_bp.route("/api/admin/users", methods=["GET", "POST"])
@admin_required
def admin_users():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if len(username) < 3:
            return jsonify(error="Username must be at least 3 characters."), 400
        if "@" not in email:
            return jsonify(error="A valid email is required."), 400
        if len(password) < 6:
            return jsonify(error="Password must be at least 6 characters."), 400
        if User.query.filter_by(username=username).first():
            return jsonify(error="Username already taken."), 400
        if User.query.filter_by(email=email).first():
            return jsonify(error="Email already in use."), 400
        user = User(username=username, email=email, display_name=username,
                    is_admin=bool(data.get("is_admin")))
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return jsonify(_user_row(user)), 201

    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([_user_row(u) for u in users])


@admin_bp.route("/api/admin/users/<int:user_id>", methods=["PUT", "DELETE"])
@admin_required
def admin_user(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == "DELETE":
        if user.id == current_user.id:
            return jsonify(error="You can't delete your own account."), 400
        db.session.delete(user)
        db.session.commit()
        return jsonify(deleted=True, id=user_id)

    data = request.get_json(silent=True) or {}
    if "is_admin" in data:
        if user.id == current_user.id and not data["is_admin"]:
            return jsonify(error="You can't remove your own admin rights."), 400
        user.is_admin = bool(data["is_admin"])
    if data.get("password"):
        if len(data["password"]) < 6:
            return jsonify(error="Password must be at least 6 characters."), 400
        user.set_password(data["password"])
    if data.get("display_name"):
        user.display_name = data["display_name"].strip()
    db.session.commit()
    return jsonify(_user_row(user))


def _user_row(u):
    return {"id": u.id, "username": u.username, "email": u.email,
            "display_name": u.display_name or u.username,
            "is_admin": bool(u.is_admin),
            "playlists": Playlist.query.filter_by(owner_id=u.id).count(),
            "likes": LikedSong.query.filter_by(user_id=u.id).count(),
            "created_at": u.created_at.strftime("%Y-%m-%d") if u.created_at else ""}
