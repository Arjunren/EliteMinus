"""Admin panel: staff management first, music catalog second.

Everything here requires an authenticated user whose ``is_admin`` flag is set
*and* whose account is active.  Every state-changing action is written to the
audit log.
"""
import csv
import io
import os
import random
import re
import secrets
import uuid
from datetime import date, timedelta
from functools import wraps

from flask import (Blueprint, Response, current_app, jsonify, redirect,
                   render_template, request, url_for)
from flask_login import current_user
from sqlalchemy import func, or_
from werkzeug.utils import secure_filename

from extensions import db
from models import (ROLES, STATUSES, Album, Artist, AuditLog, LikedSong,
                    MusicSuggestion, PlayHistory, Playlist, Song, User, utcnow)
from services import audit, mailer
from services import spotify_client as sp

admin_bp = Blueprint("admin", __name__)

DEFAULT_AUDIO = "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-{}.mp3"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
MIN_PASSWORD = 8
MUSIC_UPLOAD_PREFIX = "/static/uploads/music/"


def admin_required(f):
    """Allow only active admins. JSON 401/403 for the API, redirects for pages."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        is_api = request.path.startswith("/api/")
        if not current_user.is_authenticated:
            if is_api:
                return jsonify(error="authentication required"), 401
            return redirect(url_for("auth.login", next=request.path))
        if not current_user.can_admin:
            if is_api:
                return jsonify(error="admin access required"), 403
            return redirect(url_for("main.index"))
        return f(*args, **kwargs)
    return wrapper


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean(value, limit=120):
    value = (value or "").strip()
    return value[:limit] or None


def _parse_date(value):
    try:
        return date.fromisoformat((value or "").strip())
    except (ValueError, AttributeError):
        return None


def _valid_http_url(value):
    value = (value or "").strip()
    return value if value.startswith(("https://", "http://")) else None


def _music_upload_dir():
    path = os.path.join(current_app.root_path, "static", "uploads", "music")
    os.makedirs(path, exist_ok=True)
    return path


def _remove_local_music(audio_url):
    """Remove a managed upload, never an arbitrary path supplied by a user."""
    if not (audio_url or "").startswith(MUSIC_UPLOAD_PREFIX):
        return
    filename = os.path.basename(audio_url)
    path = os.path.join(_music_upload_dir(), filename)
    if os.path.isfile(path):
        os.remove(path)


def _is_mp3(upload):
    """Small content check in addition to the extension/MIME allow-list."""
    header = upload.stream.read(10)
    upload.stream.seek(0)
    return header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xff)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------
@admin_bp.route("/admin")
@admin_required
def dashboard_page():
    return render_template("admin.html", user=current_user,
                           roles=ROLES, statuses=STATUSES)


# --------------------------------------------------------------------------
# Dashboard stats / monitoring
# --------------------------------------------------------------------------
@admin_bp.route("/api/admin/stats")
@admin_required
def stats():
    now = utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    by_status = dict(db.session.query(User.status, func.count(User.id))
                     .group_by(User.status).all())
    by_role = dict(db.session.query(User.role, func.count(User.id))
                   .group_by(User.role).all())
    by_department = (db.session.query(User.department, func.count(User.id))
                     .group_by(User.department)
                     .order_by(func.count(User.id).desc()).limit(8).all())

    staff = {
        "total": User.query.count(),
        "active": by_status.get("active", 0),
        "pending": by_status.get("pending", 0),
        "suspended": by_status.get("suspended", 0),
        "unverified": User.query.filter_by(is_verified=False).count(),
        "admins": User.query.filter_by(is_admin=True).count(),
        "new_this_week": User.query.filter(User.created_at >= week_ago).count(),
        "new_this_month": User.query.filter(User.created_at >= month_ago).count(),
        "active_today": User.query.filter(User.last_login_at >= today).count(),
        "never_signed_in": User.query.filter(User.last_login_at.is_(None)).count(),
    }

    catalog = {
        "songs": Song.query.count(),
        "artists": Artist.query.count(),
        "albums": Album.query.count(),
        "playlists": Playlist.query.count(),
        "likes": LikedSong.query.count(),
        "from_spotify": Song.query.filter(Song.spotify_id.isnot(None)).count(),
        "plays": int(db.session.query(
            func.coalesce(func.sum(Song.play_count), 0)).scalar() or 0),
        "play_events": PlayHistory.query.count(),
    }

    top_songs = Song.query.order_by(Song.play_count.desc()).limit(10).all()
    recent_staff = User.query.order_by(User.created_at.desc()).limit(6).all()
    recent_logins = (User.query.filter(User.last_login_at.isnot(None))
                     .order_by(User.last_login_at.desc()).limit(6).all())
    recent_audit = (AuditLog.query.order_by(AuditLog.created_at.desc())
                    .limit(10).all())
    genres = (db.session.query(Artist.genre, func.count(Song.id))
              .join(Song, Song.artist_id == Artist.id)
              .group_by(Artist.genre).all())

    return jsonify({
        "staff": staff,
        "catalog": catalog,
        "by_role": [{"role": r or "staff", "count": c} for r, c in by_role.items()],
        "by_status": [{"status": s or "pending", "count": c}
                      for s, c in by_status.items()],
        "by_department": [{"department": d or "Unassigned", "count": c}
                          for d, c in by_department],
        "plays_today": PlayHistory.query.filter(
            PlayHistory.played_at >= today).count(),
        "plays_week": PlayHistory.query.filter(
            PlayHistory.played_at >= week_ago).count(),
        "top_songs": [{"id": s.id, "title": s.title,
                       "artist": s.artist.name if s.artist else "—",
                       "plays": s.play_count} for s in top_songs],
        "recent_staff": [{"id": u.id, "username": u.username, "role": u.role,
                          "status": u.status,
                          "created_at": u.created_at.strftime("%Y-%m-%d %H:%M")
                          if u.created_at else ""} for u in recent_staff],
        "recent_logins": [{"id": u.id, "username": u.username,
                           "at": u.last_login_at.strftime("%Y-%m-%d %H:%M"),
                           "ip": u.last_login_ip or "—"} for u in recent_logins],
        "recent_audit": [a.to_dict() for a in recent_audit],
        "genres": [{"genre": g or "Unknown", "songs": c} for g, c in genres],
        "spotify_configured": bool(current_app.config["SPOTIFY_CLIENT_ID"]),
        "mail_configured": not current_app.config["MAIL_SUPPRESS_SEND"],
    })


# ==========================================================================
# STAFF MANAGEMENT
# ==========================================================================
def _staff_query():
    """Apply the ?q / ?role / ?status / ?department filters."""
    query = User.query
    q = (request.args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            User.username.ilike(like), User.email.ilike(like),
            User.full_name.ilike(like), User.staff_code.ilike(like),
            User.department.ilike(like), User.position.ilike(like),
        ))
    role = (request.args.get("role") or "").strip()
    if role in ROLES:
        query = query.filter(User.role == role)
    status = (request.args.get("status") or "").strip()
    if status in STATUSES:
        query = query.filter(User.status == status)
    department = (request.args.get("department") or "").strip()
    if department:
        query = query.filter(User.department == department)
    return query.order_by(User.created_at.desc())


@admin_bp.route("/api/admin/staff", methods=["GET", "POST"])
@admin_required
def admin_staff():
    if request.method == "POST":
        return _create_staff(request.get_json(silent=True) or {})

    rows = _staff_query().limit(500).all()
    return jsonify({
        "staff": [u.to_staff_dict() for u in rows],
        "count": len(rows),
        "roles": list(ROLES),
        "statuses": list(STATUSES),
        "departments": _departments(),
    })


def _departments():
    rows = (db.session.query(User.department)
            .filter(User.department.isnot(None), User.department != "")
            .distinct().all())
    return sorted(r[0] for r in rows)


def _create_staff(data):
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    generated = False

    if len(username) < 3:
        return jsonify(error="Username must be at least 3 characters."), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="A valid e-mail is required."), 400
    if not password:
        # Admin left it blank -> mint one and e-mail it to the new staff member.
        password = secrets.token_urlsafe(9)
        generated = True
    elif len(password) < MIN_PASSWORD:
        return jsonify(error=f"Password must be at least {MIN_PASSWORD} "
                             "characters."), 400
    if User.query.filter_by(username=username).first():
        return jsonify(error="Username already taken."), 400
    if User.query.filter_by(email=email).first():
        return jsonify(error="E-mail already in use."), 400

    role = data.get("role") if data.get("role") in ROLES else "staff"
    status = data.get("status") if data.get("status") in STATUSES else "active"

    user = User(
        username=username, email=email,
        display_name=_clean(data.get("display_name"), 80) or username,
        full_name=_clean(data.get("full_name")),
        role=role, status=status, is_admin=(role == "admin"),
        department=_clean(data.get("department"), 80),
        position=_clean(data.get("position"), 80),
        phone=_clean(data.get("phone"), 40),
        hire_date=_parse_date(data.get("hire_date")) or date.today(),
        notes=_clean(data.get("notes"), 2000),
        # Created by an admin, so the e-mail doesn't need an OTP round-trip.
        is_verified=True, verified_at=utcnow(),
    )
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    user.assign_staff_code()

    starter = Playlist(owner_id=user.id, name="My First Playlist",
                       description="Songs I love", cover_seed="My First Playlist")
    db.session.add(starter)
    db.session.commit()

    audit.record("staff.created", target=user.username,
                 detail=f"role={role} status={status}")

    emailed = False
    if data.get("send_credentials", True):
        emailed = mailer.send_account_notice(
            user.email, user.display_name or user.username,
            "Your EliteMinus account is ready",
            f"An administrator created an account for you.\n\n"
            f"Username: {user.username}\n"
            f"Password: {password}\n\n"
            "Please sign in and change your password from your profile. "
            "If you ever lose it, contact the developer — passwords can only be "
            "reset by hand.")

    payload = user.to_staff_dict()
    payload["credentials_emailed"] = emailed
    if generated:
        # Shown once in the admin UI, in case the e-mail doesn't arrive.
        payload["generated_password"] = password
    return jsonify(payload), 201


@admin_bp.route("/api/admin/staff/<int:user_id>", methods=["GET", "PUT", "DELETE"])
@admin_required
def admin_staff_member(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == "GET":
        return jsonify(user.to_staff_dict())

    if request.method == "DELETE":
        if user.id == current_user.id:
            return jsonify(error="You can't delete your own account."), 400
        if user.is_admin and User.query.filter_by(is_admin=True).count() <= 1:
            return jsonify(error="You can't delete the last administrator."), 400
        username = user.username
        db.session.delete(user)
        db.session.commit()
        audit.record("staff.deleted", target=username)
        return jsonify(deleted=True, id=user_id)

    # --- PUT: edit the staff record ---
    data = request.get_json(silent=True) or {}
    changes = []

    if data.get("username") and data["username"].strip() != user.username:
        new_username = data["username"].strip()
        if len(new_username) < 3:
            return jsonify(error="Username must be at least 3 characters."), 400
        if User.query.filter(User.username == new_username,
                             User.id != user.id).first():
            return jsonify(error="Username already taken."), 400
        changes.append(f"username {user.username}->{new_username}")
        user.username = new_username

    if data.get("email") and data["email"].strip().lower() != user.email:
        new_email = data["email"].strip().lower()
        if not EMAIL_RE.match(new_email):
            return jsonify(error="A valid e-mail is required."), 400
        if User.query.filter(User.email == new_email, User.id != user.id).first():
            return jsonify(error="E-mail already in use."), 400
        changes.append(f"email {user.email}->{new_email}")
        user.email = new_email

    if "role" in data and data["role"] in ROLES and data["role"] != user.role:
        if user.id == current_user.id and data["role"] != "admin":
            return jsonify(error="You can't change your own role."), 400
        if (user.is_admin and data["role"] != "admin"
                and User.query.filter_by(is_admin=True).count() <= 1):
            return jsonify(error="You can't remove the last administrator."), 400
        changes.append(f"role {user.role}->{data['role']}")
        user.role = data["role"]
        user.is_admin = data["role"] == "admin"

    if "status" in data and data["status"] in STATUSES and data["status"] != user.status:
        if user.id == current_user.id:
            return jsonify(error="You can't change your own status."), 400
        changes.append(f"status {user.status}->{data['status']}")
        user.status = data["status"]

    for field, limit in (("display_name", 80), ("full_name", 120),
                         ("department", 80), ("position", 80),
                         ("phone", 40), ("notes", 2000)):
        if field in data:
            setattr(user, field, _clean(data[field], limit))

    if "hire_date" in data:
        user.hire_date = _parse_date(data["hire_date"])
    if "is_verified" in data:
        user.is_verified = bool(data["is_verified"])
        if user.is_verified and not user.verified_at:
            user.verified_at = utcnow()

    db.session.commit()
    audit.record("staff.updated", target=user.username,
                 detail="; ".join(changes) or "profile fields")
    return jsonify(user.to_staff_dict())


@admin_bp.route("/api/admin/staff/<int:user_id>/status", methods=["POST"])
@admin_required
def admin_staff_status(user_id):
    """Approve, suspend or re-activate a staff account."""
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    status = data.get("status")

    if status not in STATUSES:
        return jsonify(error="Unknown status."), 400
    if user.id == current_user.id:
        return jsonify(error="You can't change your own status."), 400

    was = user.status
    user.status = status
    if status == "active" and not user.is_verified:
        user.is_verified = True
        user.verified_at = utcnow()
    db.session.commit()
    audit.record("staff.status", target=user.username, detail=f"{was} -> {status}")

    if data.get("notify", True):
        messages = {
            "active": "Your EliteMinus account has been approved. You can sign "
                      "in now.",
            "suspended": "Your EliteMinus account has been suspended. Contact "
                         "the developer if you think this is a mistake.",
            "pending": "Your EliteMinus account has been set back to pending "
                       "review.",
        }
        mailer.send_account_notice(
            user.email, user.display_name or user.username,
            "EliteMinus account update", messages[status])

    return jsonify(user.to_staff_dict())


@admin_bp.route("/api/admin/staff/<int:user_id>/password", methods=["POST"])
@admin_required
def admin_reset_password(user_id):
    """Reset a password by hand — the only way a lost password is recovered."""
    user = User.query.get_or_404(user_id)
    data = request.get_json(silent=True) or {}
    password = data.get("password") or ""
    generated = False

    if not password:
        password = secrets.token_urlsafe(9)
        generated = True
    elif len(password) < MIN_PASSWORD:
        return jsonify(error=f"Password must be at least {MIN_PASSWORD} "
                             "characters."), 400

    user.set_password(password)
    db.session.commit()
    # Existing API tokens embed a fingerprint of the old hash, so they die here.
    audit.record("staff.password_reset", target=user.username)

    emailed = False
    if data.get("notify", True):
        emailed = mailer.send_account_notice(
            user.email, user.display_name or user.username,
            "Your EliteMinus password was reset",
            f"An administrator reset your password.\n\n"
            f"New password: {password}\n\n"
            "Sign in and change it from your profile as soon as you can.")

    result = {"ok": True, "emailed": emailed}
    if generated:
        result["password"] = password
    return jsonify(result)


@admin_bp.route("/api/admin/staff/export")
@admin_required
def admin_staff_export():
    """Download the filtered staff list as CSV."""
    rows = _staff_query().all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Staff code", "Username", "Full name", "E-mail", "Role",
                     "Status", "Department", "Position", "Phone", "Hire date",
                     "Verified", "Joined", "Last sign-in", "Sign-ins"])
    for u in rows:
        writer.writerow([
            u.staff_code or "", u.username, u.full_name or "", u.email,
            u.role, u.status, u.department or "", u.position or "",
            u.phone or "", u.hire_date.isoformat() if u.hire_date else "",
            "yes" if u.is_verified else "no",
            u.created_at.strftime("%Y-%m-%d") if u.created_at else "",
            u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "",
            u.login_count or 0,
        ])

    audit.record("staff.exported", detail=f"{len(rows)} rows")
    filename = f"eliteminus-staff-{date.today().isoformat()}.csv"
    return Response(
        buffer.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@admin_bp.route("/api/admin/audit")
@admin_required
def admin_audit():
    limit = max(1, min(500, _int(request.args.get("limit"), 100)))
    rows = (AuditLog.query.order_by(AuditLog.created_at.desc())
            .limit(limit).all())
    return jsonify([a.to_dict() for a in rows])


# ===========================================================================
# LISTENER MUSIC SUGGESTIONS
# ===========================================================================
@admin_bp.route("/api/admin/music-suggestions", methods=["GET"])
@admin_required
def admin_music_suggestions():
    rows = (MusicSuggestion.query.order_by(MusicSuggestion.created_at.desc())
            .limit(500).all())
    return jsonify([row.to_dict() for row in rows])


@admin_bp.route("/api/admin/music-suggestions/<int:suggestion_id>",
                methods=["DELETE"])
@admin_required
def admin_delete_music_suggestion(suggestion_id):
    suggestion = MusicSuggestion.query.get_or_404(suggestion_id)
    title = suggestion.title
    db.session.delete(suggestion)
    db.session.commit()
    audit.record("music_suggestion.deleted", target=title)
    return jsonify(deleted=True, id=suggestion_id)


# ==========================================================================
# MUSIC CATALOG
# ===========================================================================
@admin_bp.route("/api/admin/music-upload", methods=["POST"])
@admin_required
def admin_music_upload():
    """Add an MP3 the administrator owns or is licensed to distribute."""
    title = (request.form.get("title") or "").strip()[:150]
    artist_name = (request.form.get("artist_name") or "").strip()[:120]
    poster_url = _valid_http_url(request.form.get("poster_url"))
    upload = request.files.get("audio")

    if not title:
        return jsonify(error="Title is required."), 400
    if not artist_name:
        return jsonify(error="Artist name is required."), 400
    if not upload or not upload.filename:
        return jsonify(error="Choose an MP3 file to upload."), 400

    original = secure_filename(upload.filename)
    if (not original.lower().endswith(".mp3") or not _is_mp3(upload)):
        return jsonify(error="Only valid MP3 audio files are accepted."), 400

    artist = (Artist.query.filter(func.lower(Artist.name) == artist_name.lower())
              .first())
    if not artist:
        artist = Artist(name=artist_name, image_seed=artist_name)
        db.session.add(artist)
        db.session.flush()

    filename = f"{uuid.uuid4().hex}.mp3"
    path = os.path.join(_music_upload_dir(), filename)
    try:
        upload.save(path)
        song = Song(
            title=title,
            artist_id=artist.id,
            audio_url=MUSIC_UPLOAD_PREFIX + filename,
            image_url=poster_url,
            duration=_int(request.form.get("duration"), 0),
            track_number=1,
            play_count=0,
        )
        db.session.add(song)
        db.session.commit()
    except Exception:  # noqa: BLE001 - clean up a failed upload transaction
        db.session.rollback()
        if os.path.isfile(path):
            os.remove(path)
        raise

    audit.record("music.uploaded", target=song.title,
                 detail=f"{song.music_id} by {artist.name}")
    return jsonify(_song_row(song)), 201


@admin_bp.route("/api/admin/songs", methods=["GET", "POST"])
@admin_required
def admin_songs():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        if not title:
            return jsonify(error="Title is required."), 400
        artist = db.session.get(Artist, _int(data.get("artist_id"), 0))
        if not artist:
            return jsonify(error="A valid artist is required."), 400

        album = None
        if data.get("album_id"):
            album = db.session.get(Album, _int(data["album_id"], 0))
            if album and album.artist_id != artist.id:
                return jsonify(error="That album belongs to a different artist."), 400

        song = Song(title=title, artist_id=artist.id,
                    album_id=album.id if album else None,
                    audio_url=((data.get("audio_url") or "").strip()
                               or DEFAULT_AUDIO.format(random.randint(1, 16))),
                    duration=_int(data.get("duration"), 200),
                    track_number=_int(data.get("track_number"), 1),
                    play_count=0)
        db.session.add(song)
        db.session.commit()
        audit.record("song.created", target=song.title, detail=artist.name)
        return jsonify(_song_row(song)), 201

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
        title = song.title
        _remove_local_music(song.audio_url)
        db.session.delete(song)
        db.session.commit()
        audit.record("song.deleted", target=title)
        return jsonify(deleted=True, id=song_id)

    data = request.get_json(silent=True) or {}
    if data.get("title", "").strip():
        song.title = data["title"].strip()
    if data.get("artist_id"):
        artist = db.session.get(Artist, _int(data["artist_id"], 0))
        if artist:
            song.artist_id = artist.id
    if "album_id" in data:
        song.album_id = _int(data["album_id"], 0) or None
    if data.get("audio_url", "").strip():
        song.audio_url = data["audio_url"].strip()
    if "duration" in data:
        song.duration = _int(data["duration"], song.duration)
    db.session.commit()
    audit.record("song.updated", target=song.title)
    return jsonify(_song_row(song))


def _song_row(s):
    return {"id": s.id, "music_id": s.music_id, "title": s.title,
            "artist": {"id": s.artist.id, "name": s.artist.name} if s.artist else None,
            "album": {"id": s.album.id, "title": s.album.title} if s.album else None,
            "duration": s.duration, "play_count": s.play_count,
            "audio_url": s.audio_url, "image_url": s.image_url,
            "spotify_id": s.spotify_id,
            "image": s.image}


@admin_bp.route("/api/admin/artists", methods=["GET", "POST"])
@admin_required
def admin_artists():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify(error="Name is required."), 400
        artist = Artist(name=name, genre=_clean(data.get("genre"), 60),
                        bio=_clean(data.get("bio"), 2000), image_seed=name,
                        monthly_listeners=_int(data.get("monthly_listeners"), 0))
        db.session.add(artist)
        db.session.commit()
        audit.record("artist.created", target=artist.name)
        return jsonify(_artist_row(artist)), 201

    artists = Artist.query.order_by(Artist.name).all()
    return jsonify([_artist_row(a) for a in artists])


@admin_bp.route("/api/admin/artists/<int:artist_id>", methods=["PUT", "DELETE"])
@admin_required
def admin_artist(artist_id):
    artist = Artist.query.get_or_404(artist_id)
    if request.method == "DELETE":
        name = artist.name
        db.session.delete(artist)        # cascades to albums + songs
        db.session.commit()
        audit.record("artist.deleted", target=name, detail="cascaded to albums/songs")
        return jsonify(deleted=True, id=artist_id)

    data = request.get_json(silent=True) or {}
    if data.get("name", "").strip():
        artist.name = data["name"].strip()
    if "genre" in data:
        artist.genre = _clean(data["genre"], 60)
    if "bio" in data:
        artist.bio = _clean(data["bio"], 2000)
    if "monthly_listeners" in data:
        artist.monthly_listeners = _int(data["monthly_listeners"],
                                        artist.monthly_listeners)
    db.session.commit()
    audit.record("artist.updated", target=artist.name)
    return jsonify(_artist_row(artist))


def _artist_row(a):
    return {"id": a.id, "name": a.name, "genre": a.genre,
            "monthly_listeners": a.monthly_listeners,
            "albums": len(a.albums), "songs": len(a.songs),
            "spotify_id": a.spotify_id, "image": a.image}


@admin_bp.route("/api/admin/albums", methods=["GET", "POST"])
@admin_required
def admin_albums():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        artist = db.session.get(Artist, _int(data.get("artist_id"), 0))
        if not title:
            return jsonify(error="Title is required."), 400
        if not artist:
            return jsonify(error="A valid artist is required."), 400

        year = _int(data.get("year"), 0)
        album = Album(title=title, artist_id=artist.id, cover_seed=title,
                      release_date=date(year, 1, 1) if 1900 <= year <= 2100 else None)
        db.session.add(album)
        db.session.commit()
        audit.record("album.created", target=album.title, detail=artist.name)
        return jsonify(_album_row(album)), 201

    albums = Album.query.order_by(Album.title).all()
    return jsonify([_album_row(a) for a in albums])


@admin_bp.route("/api/admin/albums/<int:album_id>", methods=["DELETE"])
@admin_required
def admin_album(album_id):
    album = Album.query.get_or_404(album_id)
    title = album.title
    db.session.delete(album)
    db.session.commit()
    audit.record("album.deleted", target=title)
    return jsonify(deleted=True, id=album_id)


def _album_row(a):
    return {"id": a.id, "title": a.title,
            "artist": {"id": a.artist.id, "name": a.artist.name} if a.artist else None,
            "year": a.release_date.year if a.release_date else None,
            "songs": len(a.songs), "spotify_id": a.spotify_id, "image": a.image}


# ==========================================================================
# SPOTIFY IMPORT
# ==========================================================================
@admin_bp.route("/api/admin/spotify/search")
@admin_required
def admin_spotify_search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify(tracks=[], albums=[], artists=[])
    try:
        payload = sp.search(query, types="track,album,artist",
                            limit=_int(request.args.get("limit"), 20))
    except sp.SpotifyError as exc:
        return jsonify(error=str(exc)), 502

    imported_tracks = {s.spotify_id for s in
                       Song.query.filter(Song.spotify_id.isnot(None)).all()}
    imported_albums = {a.spotify_id for a in
                       Album.query.filter(Album.spotify_id.isnot(None)).all()}

    tracks = []
    for item in (payload.get("tracks") or {}).get("items", []):
        row = sp.summarize_track(item)
        row["imported"] = row["spotify_id"] in imported_tracks
        tracks.append(row)

    albums = [{
        "spotify_id": a["id"], "title": a["name"],
        "artist": (a.get("artists") or [{}])[0].get("name", ""),
        "image": sp.biggest_image(a.get("images")),
        "year": (a.get("release_date") or "")[:4],
        "total_tracks": a.get("total_tracks") or 0,
        "imported": a["id"] in imported_albums,
    } for a in (payload.get("albums") or {}).get("items", [])]

    artists = [{
        "spotify_id": a["id"], "name": a["name"],
        "image": sp.biggest_image(a.get("images")),
        "genres": a.get("genres") or [],
        "followers": (a.get("followers") or {}).get("total") or 0,
    } for a in (payload.get("artists") or {}).get("items", [])]

    return jsonify(tracks=tracks, albums=albums, artists=artists)


@admin_bp.route("/api/admin/spotify/import", methods=["POST"])
@admin_required
def admin_spotify_import():
    """Pull a Spotify track, album or artist into the local catalog."""
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    spotify_id = (data.get("spotify_id") or "").strip()
    if not spotify_id:
        return jsonify(error="No Spotify id given."), 400

    try:
        if kind == "track":
            song = sp.import_track(sp.get_track(spotify_id))
            db.session.commit()
            audit.record("spotify.import", target=song.title, detail="track")
            return jsonify(kind="track", imported=1, item=_song_row(song)), 201

        if kind == "album":
            album = sp.import_album(sp.get_album(spotify_id), with_tracks=True)
            db.session.commit()
            audit.record("spotify.import", target=album.title,
                         detail=f"album, {len(album.songs)} tracks")
            return jsonify(kind="album", imported=len(album.songs),
                           item=_album_row(album)), 201

        if kind == "artist":
            artist = sp.import_artist(sp.get_artist(spotify_id))
            top = sp.get_artist_top_tracks(spotify_id).get("tracks", [])
            for track in top:
                sp.import_track(track, artist=artist)
            db.session.commit()
            audit.record("spotify.import", target=artist.name,
                         detail=f"artist, {len(top)} top tracks")
            return jsonify(kind="artist", imported=len(top),
                           item=_artist_row(artist)), 201

        return jsonify(error="kind must be track, album or artist."), 400

    except sp.SpotifyError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 502
