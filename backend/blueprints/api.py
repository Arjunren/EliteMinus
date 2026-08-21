"""JSON API powering the listener app.

Authentication is handled by Flask-Login: either a session cookie (admin panel
on the same origin) or an ``Authorization: Bearer`` token (the Vercel site) —
see the ``request_loader`` in ``app.py``.
"""
import hashlib

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from extensions import db
from models import (Album, Artist, LikedSong, PlayHistory, Playlist,
                    PlaylistSong, QueueItem, Song, followed_artists)

api_bp = Blueprint("api", __name__)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def liked_ids():
    """Set of song ids the current user has liked (one query)."""
    if not current_user.is_authenticated:
        return set()
    rows = (db.session.query(LikedSong.song_id)
            .filter_by(user_id=current_user.id).all())
    return {r[0] for r in rows}


def followed_ids():
    if not current_user.is_authenticated:
        return set()
    rows = (db.session.query(followed_artists.c.artist_id)
            .filter(followed_artists.c.user_id == current_user.id).all())
    return {r[0] for r in rows}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# Cover art generator  ->  /api/cover?seed=Foo&size=300   (gradient SVG)
# --------------------------------------------------------------------------
@api_bp.route("/cover")
def cover():
    seed = request.args.get("seed", "music")
    size = max(64, min(900, _int(request.args.get("size"), 300)))

    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    n = int(digest, 16)
    hue1 = n % 360
    hue2 = (hue1 + 55 + (n >> 12) % 110) % 360
    c1 = f"hsl({hue1}, 62%, 48%)"
    c2 = f"hsl({hue2}, 64%, 22%)"
    letter = (seed.strip()[:1] or "♪").upper().replace("&", "&amp;").replace("<", "&lt;")
    fs = int(size * 0.46)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 {size} {size}">'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{c1}"/>'
        f'<stop offset="1" stop-color="{c2}"/></linearGradient></defs>'
        f'<rect width="{size}" height="{size}" fill="url(#g)"/>'
        f'<text x="50%" y="50%" font-family="Arial, Helvetica, sans-serif" '
        f'font-size="{fs}" font-weight="700" fill="rgba(255,255,255,0.9)" '
        f'text-anchor="middle" dominant-baseline="central">{letter}</text>'
        f"</svg>"
    )
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


# --------------------------------------------------------------------------
# Current user
# --------------------------------------------------------------------------
@api_bp.route("/me")
@login_required
def me():
    return jsonify(current_user.to_dict())


@api_bp.route("/me", methods=["PUT"])
@login_required
def update_me():
    """Let a user edit their own display name and contact details."""
    data = request.get_json(silent=True) or {}
    if data.get("display_name"):
        current_user.display_name = data["display_name"].strip()[:80]
    if "full_name" in data:
        current_user.full_name = (data["full_name"] or "").strip()[:120] or None
    if "phone" in data:
        current_user.phone = (data["phone"] or "").strip()[:40] or None
    db.session.commit()
    return jsonify(current_user.to_dict())


@api_bp.route("/me/password", methods=["PUT"])
@login_required
def change_password():
    """Change your own password (you must know the current one)."""
    data = request.get_json(silent=True) or {}
    current = data.get("current_password") or ""
    new = data.get("new_password") or ""
    confirm = data.get("confirm") or ""

    if not current_user.check_password(current):
        return jsonify(error="Your current password is not correct."), 400
    if len(new) < 8:
        return jsonify(error="New password must be at least 8 characters."), 400
    if new != confirm:
        return jsonify(error="New passwords do not match."), 400

    current_user.set_password(new)
    db.session.commit()
    # Every previously issued token embeds a hash fingerprint, so they all die
    # here — the client must sign in again with a fresh one.
    from services import tokens
    return jsonify(ok=True, token=tokens.issue(current_user))


# --------------------------------------------------------------------------
# Home feed
# --------------------------------------------------------------------------
@api_bp.route("/home")
@login_required
def home():
    lids = liked_ids()

    # Recently played (distinct songs, newest first)
    recent_rows = (db.session.query(PlayHistory.song_id,
                                    func.max(PlayHistory.played_at).label("t"))
                   .filter(PlayHistory.user_id == current_user.id)
                   .group_by(PlayHistory.song_id)
                   .order_by(func.max(PlayHistory.played_at).desc())
                   .limit(8).all())
    recent_songs = []
    if recent_rows:
        ids = [r[0] for r in recent_rows]
        by_id = {s.id: s for s in Song.query.filter(Song.id.in_(ids)).all()}
        recent_songs = [by_id[i].to_dict(liked_ids=lids) for i in ids if i in by_id]

    featured = (Playlist.query.filter_by(is_public=True)
                .order_by(Playlist.id).limit(8).all())
    popular_albums = (Album.query
                      .join(Song, Song.album_id == Album.id)
                      .group_by(Album.id)
                      .order_by(func.sum(Song.play_count).desc())
                      .limit(10).all())
    if not popular_albums:
        popular_albums = Album.query.limit(10).all()
    top_artists = (Artist.query
                   .order_by(Artist.monthly_listeners.desc()).limit(10).all())
    trending = (Song.query.order_by(Song.play_count.desc()).limit(10).all())

    return jsonify({
        "greeting_name": current_user.display_name or current_user.username,
        "recently_played": recent_songs,
        "featured_playlists": [p.to_dict() for p in featured],
        "popular_albums": [a.to_dict() for a in popular_albums],
        "top_artists": [a.to_dict() for a in top_artists],
        "trending": [s.to_dict(liked_ids=lids) for s in trending],
    })


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
@api_bp.route("/search")
@login_required
def search():
    q = (request.args.get("q") or "").strip()
    if not q:
        # Empty query -> browse buckets (genres = distinct artist genres)
        genres = [g[0] for g in db.session.query(Artist.genre)
                  .distinct().filter(Artist.genre.isnot(None)).all()]
        return jsonify({"query": "", "genres": sorted(genres),
                        "songs": [], "artists": [], "albums": [], "playlists": []})

    like = f"%{q}%"
    lids = liked_ids()

    songs = (Song.query.join(Artist, Song.artist_id == Artist.id)
             .filter(or_(Song.title.ilike(like), Artist.name.ilike(like)))
             .order_by(Song.play_count.desc())
             .limit(20).all())
    artists = Artist.query.filter(Artist.name.ilike(like)).limit(10).all()
    albums = Album.query.filter(Album.title.ilike(like)).limit(10).all()
    playlists = (Playlist.query
                 .filter(Playlist.is_public.is_(True), Playlist.name.ilike(like))
                 .limit(10).all())

    return jsonify({
        "query": q,
        "songs": [s.to_dict(liked_ids=lids) for s in songs],
        "artists": [a.to_dict() for a in artists],
        "albums": [a.to_dict() for a in albums],
        "playlists": [p.to_dict() for p in playlists],
    })


# --------------------------------------------------------------------------
# Albums / Artists
# --------------------------------------------------------------------------
@api_bp.route("/albums/<int:album_id>")
@login_required
def album_detail(album_id):
    album = Album.query.get_or_404(album_id)
    return jsonify(album.to_dict(with_tracks=True, liked_ids=liked_ids()))


@api_bp.route("/artists/<int:artist_id>")
@login_required
def artist_detail(artist_id):
    artist = Artist.query.get_or_404(artist_id)
    lids = liked_ids()
    top_songs = (Song.query.filter_by(artist_id=artist_id)
                 .order_by(Song.play_count.desc()).limit(10).all())
    data = artist.to_dict(full=True)
    data["following"] = artist_id in followed_ids()
    data["top_songs"] = [s.to_dict(liked_ids=lids) for s in top_songs]
    data["albums"] = [a.to_dict() for a in
                      sorted(artist.albums,
                             key=lambda a: (a.release_date or None) is None)]
    return jsonify(data)


@api_bp.route("/artists/<int:artist_id>/follow", methods=["POST", "DELETE"])
@login_required
def follow_artist(artist_id):
    artist = Artist.query.get_or_404(artist_id)
    is_following = artist in current_user.follows
    if request.method == "POST" and not is_following:
        current_user.follows.append(artist)
    elif request.method == "DELETE" and is_following:
        current_user.follows.remove(artist)
    db.session.commit()
    return jsonify(following=request.method == "POST")


# --------------------------------------------------------------------------
# Liked songs
# --------------------------------------------------------------------------
@api_bp.route("/liked")
@login_required
def liked_collection():
    rows = (LikedSong.query.filter_by(user_id=current_user.id)
            .order_by(LikedSong.liked_at.desc()).all())
    lids = {r.song_id for r in rows}
    tracks = [r.song.to_dict(liked_ids=lids) for r in rows if r.song]
    return jsonify({
        "type": "liked",
        "name": "Liked Songs",
        "owner": {"name": current_user.display_name or current_user.username},
        "song_count": len(tracks),
        "total_duration": sum(t["duration"] or 0 for t in tracks),
        "tracks": tracks,
    })


@api_bp.route("/songs/<int:song_id>/like", methods=["PUT", "DELETE"])
@login_required
def toggle_like(song_id):
    Song.query.get_or_404(song_id)
    existing = LikedSong.query.filter_by(user_id=current_user.id,
                                         song_id=song_id).first()
    if request.method == "PUT":
        if not existing:
            db.session.add(LikedSong(user_id=current_user.id, song_id=song_id))
        liked = True
    else:
        if existing:
            db.session.delete(existing)
        liked = False
    db.session.commit()
    return jsonify(liked=liked, song_id=song_id)


# --------------------------------------------------------------------------
# Playlists
# --------------------------------------------------------------------------
@api_bp.route("/playlists", methods=["GET", "POST"])
@login_required
def playlists():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        count = Playlist.query.filter_by(owner_id=current_user.id).count()
        name = (data.get("name") or "").strip() or f"My Playlist #{count + 1}"
        pl = Playlist(
            owner_id=current_user.id,
            name=name[:120],
            description=(data.get("description") or "").strip()[:300],
            cover_seed=name,
            is_public=bool(data.get("is_public", True)),
        )
        db.session.add(pl)
        db.session.commit()

        # Optional: seed the new playlist with songs in one call.
        song_ids = data.get("song_ids") or []
        if song_ids:
            _append_songs(pl, song_ids)
            db.session.commit()

        return jsonify(pl.to_dict()), 201

    # GET -> the current user's own playlists (for sidebar + library)
    mine = (Playlist.query.filter_by(owner_id=current_user.id)
            .order_by(Playlist.created_at.desc()).all())
    return jsonify([p.to_dict() for p in mine])


def _owned_playlist_or_error(playlist_id):
    pl = Playlist.query.get_or_404(playlist_id)
    if pl.owner_id != current_user.id:
        return None, (jsonify(error="You can only modify your own playlists."), 403)
    return pl, None


def _append_songs(pl, song_ids):
    """Add songs to the end of a playlist, skipping ones already in it."""
    existing = {i.song_id for i in pl.items}
    position = (db.session.query(func.max(PlaylistSong.position))
                .filter_by(playlist_id=pl.id).scalar()) or 0
    added = 0
    for song_id in song_ids:
        song_id = _int(song_id, 0)
        if not song_id or song_id in existing:
            continue
        if not db.session.get(Song, song_id):
            continue
        position += 1
        db.session.add(PlaylistSong(playlist_id=pl.id, song_id=song_id,
                                    position=position))
        existing.add(song_id)
        added += 1
    return added


@api_bp.route("/playlists/<int:playlist_id>", methods=["GET", "PUT", "DELETE"])
@login_required
def playlist_detail(playlist_id):
    pl = Playlist.query.get_or_404(playlist_id)
    owns = pl.owner_id == current_user.id

    if request.method == "GET":
        if not pl.is_public and not owns:
            return jsonify(error="This playlist is private."), 403
        data = pl.to_dict(with_tracks=True, liked_ids=liked_ids())
        data["editable"] = owns
        return jsonify(data)

    if not owns:
        return jsonify(error="You can only modify your own playlists."), 403

    if request.method == "DELETE":
        db.session.delete(pl)
        db.session.commit()
        return jsonify(deleted=True, id=playlist_id)

    # PUT -> rename / edit
    data = request.get_json(silent=True) or {}
    if "name" in data:
        pl.name = (data["name"] or "").strip()[:120] or pl.name
    if "description" in data:
        pl.description = (data["description"] or "").strip()[:300]
    if "is_public" in data:
        pl.is_public = bool(data["is_public"])
    db.session.commit()
    return jsonify(pl.to_dict())


@api_bp.route("/playlists/<int:playlist_id>/duplicate", methods=["POST"])
@login_required
def duplicate_playlist(playlist_id):
    """Copy any playlist you can see into your own library."""
    source = Playlist.query.get_or_404(playlist_id)
    if not source.is_public and source.owner_id != current_user.id:
        return jsonify(error="This playlist is private."), 403

    copy = Playlist(owner_id=current_user.id, name=f"{source.name} (copy)"[:120],
                    description=source.description, cover_seed=source.cover_seed,
                    image_url=source.image_url, is_public=False)
    db.session.add(copy)
    db.session.flush()
    for position, item in enumerate(source.items, start=1):
        db.session.add(PlaylistSong(playlist_id=copy.id, song_id=item.song_id,
                                    position=position))
    db.session.commit()
    return jsonify(copy.to_dict()), 201


@api_bp.route("/playlists/<int:playlist_id>/songs", methods=["POST"])
@login_required
def add_to_playlist(playlist_id):
    pl, error = _owned_playlist_or_error(playlist_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    song_ids = data.get("song_ids") or ([data["song_id"]] if data.get("song_id") else [])
    if not song_ids:
        return jsonify(error="No songs given."), 400

    added = _append_songs(pl, song_ids)
    db.session.commit()
    return jsonify(added=bool(added), added_count=added,
                   song_count=len(pl.items),
                   message="Already in playlist." if not added else "Added.")


@api_bp.route("/playlists/<int:playlist_id>/songs/<int:song_id>",
              methods=["DELETE"])
@login_required
def remove_from_playlist(playlist_id, song_id):
    pl, error = _owned_playlist_or_error(playlist_id)
    if error:
        return error
    item = PlaylistSong.query.filter_by(playlist_id=playlist_id,
                                        song_id=song_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
        _renumber_playlist(pl)
    return jsonify(removed=True, song_count=len(pl.items))


@api_bp.route("/playlists/<int:playlist_id>/reorder", methods=["POST"])
@login_required
def reorder_playlist(playlist_id):
    """Drag-and-drop reordering: send the song ids in their new order."""
    pl, error = _owned_playlist_or_error(playlist_id)
    if error:
        return error

    data = request.get_json(silent=True) or {}
    order = [_int(x, 0) for x in (data.get("song_ids") or [])]
    if not order:
        return jsonify(error="No order given."), 400

    by_song = {item.song_id: item for item in pl.items}
    position = 0
    for song_id in order:
        item = by_song.pop(song_id, None)
        if item:
            position += 1
            item.position = position
    # Anything the client didn't mention keeps its relative order at the end.
    for item in sorted(by_song.values(), key=lambda i: i.position):
        position += 1
        item.position = position
    db.session.commit()
    return jsonify(ok=True, song_count=len(pl.items))


def _renumber_playlist(pl):
    for position, item in enumerate(sorted(pl.items, key=lambda i: i.position),
                                    start=1):
        item.position = position
    db.session.commit()


# --------------------------------------------------------------------------
# Playback queue (server-backed, so it survives reloads and device switches)
# --------------------------------------------------------------------------
def _queue_rows():
    return (QueueItem.query.filter_by(user_id=current_user.id)
            .order_by(QueueItem.position).all())


def _queue_payload(message=None):
    rows = _queue_rows()
    lids = liked_ids()
    index = max(0, min(current_user.queue_index or 0, max(0, len(rows) - 1)))
    items = []
    for i, row in enumerate(rows):
        if not row.song:
            continue
        track = row.song.to_dict(liked_ids=lids)
        track["queue_item_id"] = row.id
        track["queue_source"] = row.source
        track["is_current"] = i == index
        items.append(track)
    payload = {
        "items": items,
        "index": index,
        "count": len(items),
        "current": items[index] if index < len(items) else None,
        "total_duration": sum(t["duration"] or 0 for t in items),
    }
    if message:
        payload["message"] = message
    return jsonify(payload)


def _next_position():
    return ((db.session.query(func.max(QueueItem.position))
             .filter_by(user_id=current_user.id).scalar()) or 0) + 1


@api_bp.route("/queue")
@login_required
def get_queue():
    return _queue_payload()


@api_bp.route("/queue", methods=["PUT"])
@login_required
def replace_queue():
    """Start a new listening context — replaces the whole queue.

    Called when the user hits play on an album, playlist or search result.
    """
    data = request.get_json(silent=True) or {}
    song_ids = [_int(x, 0) for x in (data.get("song_ids") or []) if _int(x, 0)]
    start = _int(data.get("index"), 0)

    QueueItem.query.filter_by(user_id=current_user.id).delete(
        synchronize_session=False)

    valid = {s.id for s in Song.query.filter(Song.id.in_(song_ids)).all()} \
        if song_ids else set()
    position = 0
    kept = []
    for song_id in song_ids:
        if song_id not in valid:
            continue
        position += 1
        db.session.add(QueueItem(user_id=current_user.id, song_id=song_id,
                                 position=position, source="context"))
        kept.append(song_id)

    current_user.queue_index = max(0, min(start, max(0, len(kept) - 1)))
    db.session.commit()
    return _queue_payload()


@api_bp.route("/queue", methods=["POST"])
@login_required
def add_to_queue():
    """Add a song (or a whole collection) to the queue.

    ``play_next`` inserts right after the current track, the way Spotify's
    "Play next" does; otherwise it goes to the end.
    """
    data = request.get_json(silent=True) or {}
    song_ids = [_int(x, 0) for x in (data.get("song_ids") or [])]
    if data.get("song_id"):
        song_ids.append(_int(data["song_id"], 0))
    song_ids = [s for s in song_ids if s]
    if not song_ids:
        return jsonify(error="No songs given."), 400

    found = {s.id: s for s in Song.query.filter(Song.id.in_(song_ids)).all()}
    song_ids = [s for s in song_ids if s in found]
    if not song_ids:
        return jsonify(error="Those songs no longer exist."), 404

    rows = _queue_rows()
    if data.get("play_next") and rows:
        index = max(0, min(current_user.queue_index or 0, len(rows) - 1))
        # Push everything after the current track back to make room.
        for row in rows[index + 1:]:
            row.position += len(song_ids)
        base = rows[index].position
        for offset, song_id in enumerate(song_ids, start=1):
            db.session.add(QueueItem(user_id=current_user.id, song_id=song_id,
                                     position=base + offset, source="manual"))
    else:
        position = _next_position()
        for song_id in song_ids:
            db.session.add(QueueItem(user_id=current_user.id, song_id=song_id,
                                     position=position, source="manual"))
            position += 1

    db.session.commit()
    label = found[song_ids[0]].title if len(song_ids) == 1 else f"{len(song_ids)} songs"
    return _queue_payload(message=f"Added {label} to queue")


@api_bp.route("/queue/index", methods=["PUT"])
@login_required
def set_queue_index():
    """Tell the server which queue entry is now playing."""
    data = request.get_json(silent=True) or {}
    total = QueueItem.query.filter_by(user_id=current_user.id).count()
    current_user.queue_index = max(0, min(_int(data.get("index"), 0),
                                          max(0, total - 1)))
    db.session.commit()
    return jsonify(ok=True, index=current_user.queue_index)


@api_bp.route("/queue/<int:item_id>", methods=["DELETE"])
@login_required
def remove_queue_item(item_id):
    rows = _queue_rows()
    target = next((i for i, row in enumerate(rows) if row.id == item_id), None)
    if target is None:
        return jsonify(error="Not in your queue."), 404

    db.session.delete(rows[target])
    db.session.flush()
    remaining = [r for r in rows if r.id != item_id]
    for position, row in enumerate(remaining, start=1):
        row.position = position

    index = current_user.queue_index or 0
    if target < index:
        index -= 1                      # everything shifted up by one
    current_user.queue_index = max(0, min(index, max(0, len(remaining) - 1)))
    db.session.commit()
    return _queue_payload(message="Removed from queue")


@api_bp.route("/queue/move", methods=["POST"])
@login_required
def move_queue_item():
    """Reorder the queue by moving one entry to a new slot."""
    data = request.get_json(silent=True) or {}
    rows = _queue_rows()
    if not rows:
        return _queue_payload()

    frm = _int(data.get("from"), -1)
    to = max(0, min(_int(data.get("to"), 0), len(rows) - 1))
    if not 0 <= frm < len(rows):
        return jsonify(error="No such queue position."), 400

    moved = rows.pop(frm)
    rows.insert(to, moved)
    for position, row in enumerate(rows, start=1):
        row.position = position

    # Keep pointing at whatever was playing before the shuffle.
    index = current_user.queue_index or 0
    if frm == index:
        index = to
    elif frm < index <= to:
        index -= 1
    elif to <= index < frm:
        index += 1
    current_user.queue_index = max(0, min(index, len(rows) - 1))
    db.session.commit()
    return _queue_payload()


@api_bp.route("/queue", methods=["DELETE"])
@login_required
def clear_queue():
    """Clear everything after the current track (Spotify's "Clear queue")."""
    keep_current = request.args.get("keep_current", "1") != "0"
    rows = _queue_rows()
    index = max(0, min(current_user.queue_index or 0, max(0, len(rows) - 1)))

    doomed = rows[index + 1:] if (keep_current and rows) else rows
    for row in doomed:
        db.session.delete(row)
    if not keep_current:
        current_user.queue_index = 0
    db.session.commit()
    return _queue_payload(message="Queue cleared")


# --------------------------------------------------------------------------
# Library + history
# --------------------------------------------------------------------------
@api_bp.route("/library")
@login_required
def library():
    mine = (Playlist.query.filter_by(owner_id=current_user.id)
            .order_by(Playlist.created_at.desc()).all())
    artists = current_user.follows
    liked_count = LikedSong.query.filter_by(user_id=current_user.id).count()
    return jsonify({
        "playlists": [p.to_dict() for p in mine],
        "artists": [a.to_dict() for a in artists],
        "liked_count": liked_count,
    })


@api_bp.route("/history", methods=["POST"])
@login_required
def record_play():
    data = request.get_json(silent=True) or {}
    song = db.session.get(Song, _int(data.get("song_id"), 0))
    if not song:
        return jsonify(error="Unknown song."), 404
    song.play_count = (song.play_count or 0) + 1
    db.session.add(PlayHistory(user_id=current_user.id, song_id=song.id))
    db.session.commit()
    return jsonify(ok=True, play_count=song.play_count)


@api_bp.route("/history")
@login_required
def list_history():
    rows = (PlayHistory.query.filter_by(user_id=current_user.id)
            .order_by(PlayHistory.played_at.desc()).limit(50).all())
    lids = liked_ids()
    return jsonify([{**row.song.to_dict(liked_ids=lids),
                     "played_at": row.played_at.strftime("%Y-%m-%d %H:%M")}
                    for row in rows if row.song])
