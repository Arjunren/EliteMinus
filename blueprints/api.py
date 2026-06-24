"""JSON API powering the single-page client."""
import hashlib

from flask import Blueprint, Response, jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func, or_

from extensions import db
from models import (Album, Artist, LikedSong, PlayHistory, Playlist,
                    PlaylistSong, Song, followed_artists)

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


# --------------------------------------------------------------------------
# Cover art generator  ->  /api/cover?seed=Foo&size=300   (gradient SVG)
# --------------------------------------------------------------------------
@api_bp.route("/cover")
def cover():
    seed = request.args.get("seed", "music")
    try:
        size = max(64, min(900, int(request.args.get("size", 300))))
    except (TypeError, ValueError):
        size = 300

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
    return resp


# --------------------------------------------------------------------------
# Current user
# --------------------------------------------------------------------------
@api_bp.route("/me")
@login_required
def me():
    return jsonify(current_user.to_dict())


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
        return jsonify({"query": "", "genres": genres,
                        "songs": [], "artists": [], "albums": [], "playlists": []})

    like = f"%{q}%"
    lids = liked_ids()

    songs = (Song.query.join(Artist, Song.artist_id == Artist.id)
             .filter(or_(Song.title.ilike(like), Artist.name.ilike(like)))
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
        "total_duration": sum(t["duration"] for t in tracks),
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
        name = (data.get("name") or "").strip() or "My Playlist"
        count = Playlist.query.filter_by(owner_id=current_user.id).count()
        pl = Playlist(
            owner_id=current_user.id,
            name=name or f"My Playlist #{count + 1}",
            description=(data.get("description") or "").strip(),
            cover_seed=name,
            is_public=bool(data.get("is_public", True)),
        )
        db.session.add(pl)
        db.session.commit()
        return jsonify(pl.to_dict()), 201

    # GET -> the current user's own playlists (for sidebar + library)
    mine = (Playlist.query.filter_by(owner_id=current_user.id)
            .order_by(Playlist.created_at.desc()).all())
    return jsonify([p.to_dict() for p in mine])


@api_bp.route("/playlists/<int:playlist_id>",
              methods=["GET", "PUT", "DELETE"])
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
        pl.name = (data["name"] or "").strip() or pl.name
    if "description" in data:
        pl.description = (data["description"] or "").strip()
    if "is_public" in data:
        pl.is_public = bool(data["is_public"])
    db.session.commit()
    return jsonify(pl.to_dict())


@api_bp.route("/playlists/<int:playlist_id>/songs", methods=["POST"])
@login_required
def add_to_playlist(playlist_id):
    pl = Playlist.query.get_or_404(playlist_id)
    if pl.owner_id != current_user.id:
        return jsonify(error="You can only modify your own playlists."), 403

    data = request.get_json(silent=True) or {}
    song_id = data.get("song_id")
    Song.query.get_or_404(song_id)

    exists = PlaylistSong.query.filter_by(playlist_id=playlist_id,
                                          song_id=song_id).first()
    if exists:
        return jsonify(added=False, message="Already in playlist.")

    max_pos = (db.session.query(func.max(PlaylistSong.position))
               .filter_by(playlist_id=playlist_id).scalar()) or 0
    db.session.add(PlaylistSong(playlist_id=playlist_id, song_id=song_id,
                                position=max_pos + 1))
    db.session.commit()
    return jsonify(added=True, song_count=len(pl.items))


@api_bp.route("/playlists/<int:playlist_id>/songs/<int:song_id>",
              methods=["DELETE"])
@login_required
def remove_from_playlist(playlist_id, song_id):
    pl = Playlist.query.get_or_404(playlist_id)
    if pl.owner_id != current_user.id:
        return jsonify(error="You can only modify your own playlists."), 403
    item = PlaylistSong.query.filter_by(playlist_id=playlist_id,
                                        song_id=song_id).first()
    if item:
        db.session.delete(item)
        db.session.commit()
    return jsonify(removed=True, song_count=len(pl.items))


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
    song = Song.query.get(data.get("song_id"))
    if not song:
        return jsonify(error="Unknown song."), 404
    song.play_count = (song.play_count or 0) + 1
    db.session.add(PlayHistory(user_id=current_user.id, song_id=song.id))
    db.session.commit()
    return jsonify(ok=True)
