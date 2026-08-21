"""Spotify Web API client.

Two separate credential flows, because Spotify splits its API in two:

1. **Client Credentials** — an app-level token used for *catalog* calls
   (search, album/artist/track lookup).  No user involved.  This is what the
   admin panel's "Import from Spotify" screen and the listener search use.

2. **Authorization Code + PKCE** — a per-user token.  Needed to actually
   *stream* full tracks through the Web Playback SDK, which requires the user
   to hold a Spotify **Premium** subscription and to grant the
   ``streaming`` scope.

Note on previews: ``preview_url`` (a 30-second MP3) is present on many tracks
but Spotify does not guarantee it — newer apps often receive ``null``.  Imported
songs therefore keep the Spotify URI as the primary source and fall back to the
preview URL for the plain ``<audio>`` player.
"""
import base64
import hashlib
import secrets
import time
import urllib.parse
from datetime import timedelta

import requests
from flask import current_app

from extensions import db
from models import Album, Artist, Song, SpotifyAccount, utcnow

API = "https://api.spotify.com/v1"
ACCOUNTS = "https://accounts.spotify.com"
TIMEOUT = 15

# Scopes the listener app asks for. ``streaming`` + the two ``*-read-*`` scopes
# are the minimum the Web Playback SDK needs.
USER_SCOPES = (
    "streaming "
    "user-read-email "
    "user-read-private "
    "user-read-playback-state "
    "user-modify-playback-state"
)


class SpotifyError(Exception):
    """A Spotify call failed; the message is safe to show the user."""


# --------------------------------------------------------------------------
# App token (client credentials)
# --------------------------------------------------------------------------
_app_token = {"value": None, "expires": 0}


def _basic_auth_header():
    cfg = current_app.config
    raw = f"{cfg['SPOTIFY_CLIENT_ID']}:{cfg['SPOTIFY_CLIENT_SECRET']}"
    return "Basic " + base64.b64encode(raw.encode()).decode()


def app_token():
    """A cached client-credentials access token."""
    cfg = current_app.config
    if not (cfg["SPOTIFY_CLIENT_ID"] and cfg["SPOTIFY_CLIENT_SECRET"]):
        raise SpotifyError("Spotify is not configured. Set SPOTIFY_CLIENT_ID "
                           "and SPOTIFY_CLIENT_SECRET.")

    if _app_token["value"] and time.time() < _app_token["expires"]:
        return _app_token["value"]

    resp = requests.post(
        f"{ACCOUNTS}/api/token",
        data={"grant_type": "client_credentials"},
        headers={"Authorization": _basic_auth_header(),
                 "Content-Type": "application/x-www-form-urlencoded"},
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        raise SpotifyError(f"Spotify rejected the app credentials "
                           f"({resp.status_code}). Check your client ID/secret.")
    payload = resp.json()
    _app_token["value"] = payload["access_token"]
    # Refresh a minute early to avoid racing the expiry.
    _app_token["expires"] = time.time() + payload.get("expires_in", 3600) - 60
    return _app_token["value"]


def api_get(path, params=None, token=None):
    """GET a Spotify endpoint and return the decoded JSON."""
    resp = requests.get(
        f"{API}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {token or app_token()}"},
        timeout=TIMEOUT,
    )
    if resp.status_code == 429:
        raise SpotifyError("Spotify rate limit reached. Try again in a minute.")
    if resp.status_code == 401:
        raise SpotifyError("Spotify token rejected. Reconnect and try again.")
    if resp.status_code == 404:
        raise SpotifyError("Not found on Spotify.")
    if not resp.ok:
        raise SpotifyError(f"Spotify error {resp.status_code}.")
    return resp.json()


# --------------------------------------------------------------------------
# Catalog helpers
# --------------------------------------------------------------------------
def search(query, types="track,artist,album", limit=20):
    """Search the Spotify catalog.  Returns the raw Spotify payload."""
    return api_get("/search", {
        "q": query,
        "type": types,
        "limit": max(1, min(50, limit)),
        "market": current_app.config["SPOTIFY_MARKET"],
    })


def get_track(spotify_id):
    return api_get(f"/tracks/{spotify_id}",
                   {"market": current_app.config["SPOTIFY_MARKET"]})


def get_album(spotify_id):
    return api_get(f"/albums/{spotify_id}",
                   {"market": current_app.config["SPOTIFY_MARKET"]})


def get_artist(spotify_id):
    return api_get(f"/artists/{spotify_id}")


def get_artist_top_tracks(spotify_id):
    return api_get(f"/artists/{spotify_id}/top-tracks",
                   {"market": current_app.config["SPOTIFY_MARKET"]})


def get_artist_albums(spotify_id, limit=20):
    return api_get(f"/artists/{spotify_id}/albums", {
        "include_groups": "album,single",
        "limit": max(1, min(50, limit)),
        "market": current_app.config["SPOTIFY_MARKET"],
    })


def biggest_image(images):
    if not images:
        return None
    return sorted(images, key=lambda i: i.get("width") or 0, reverse=True)[0]["url"]


def summarize_track(track):
    """Flatten a Spotify track into the shape the front-end renders."""
    album = track.get("album") or {}
    artists = track.get("artists") or []
    return {
        "spotify_id": track.get("id"),
        "uri": track.get("uri"),
        "title": track.get("name"),
        "artist": artists[0]["name"] if artists else "Unknown artist",
        "artist_spotify_id": artists[0]["id"] if artists else None,
        "album": album.get("name"),
        "album_spotify_id": album.get("id"),
        "image": biggest_image(album.get("images")),
        "duration": round((track.get("duration_ms") or 0) / 1000),
        "preview_url": track.get("preview_url"),
        "explicit": bool(track.get("explicit")),
        "popularity": track.get("popularity") or 0,
    }


# --------------------------------------------------------------------------
# Importing into the local catalog
# --------------------------------------------------------------------------
def _parse_release_date(value):
    """Spotify gives "2019", "2019-04" or "2019-04-23"."""
    from datetime import date
    if not value:
        return None
    parts = value.split("-")
    try:
        year = int(parts[0])
        month = int(parts[1]) if len(parts) > 1 else 1
        day = int(parts[2]) if len(parts) > 2 else 1
        return date(year, month, day)
    except (ValueError, IndexError):
        return None


def import_artist(payload, genre=None):
    """Create-or-update a local Artist from a Spotify artist object."""
    artist = Artist.query.filter_by(spotify_id=payload["id"]).first()
    if not artist:
        artist = Artist.query.filter(
            Artist.name == payload["name"], Artist.spotify_id.is_(None)).first()
    if not artist:
        artist = Artist(name=payload["name"])
        db.session.add(artist)

    artist.spotify_id = payload["id"]
    artist.name = payload["name"]
    artist.image_seed = artist.image_seed or payload["name"]
    if payload.get("images"):
        artist.image_url = biggest_image(payload["images"])
    genres = payload.get("genres") or ([genre] if genre else [])
    if genres:
        artist.genre = genres[0].title()
    if payload.get("followers"):
        artist.monthly_listeners = payload["followers"].get("total") or 0
    db.session.flush()
    return artist


def _ensure_artist(spotify_artist_stub):
    """Artist stubs inside track/album payloads carry only id + name, so fetch
    the full record the first time we see one."""
    existing = Artist.query.filter_by(spotify_id=spotify_artist_stub["id"]).first()
    if existing:
        return existing
    try:
        full = get_artist(spotify_artist_stub["id"])
    except SpotifyError:
        full = spotify_artist_stub
    return import_artist(full)


def import_album(payload, with_tracks=True):
    """Create-or-update a local Album (and optionally all of its tracks)."""
    artists = payload.get("artists") or []
    if not artists:
        raise SpotifyError("That album has no artist information.")
    artist = _ensure_artist(artists[0])

    album = Album.query.filter_by(spotify_id=payload["id"]).first()
    if not album:
        album = Album(title=payload["name"], artist_id=artist.id)
        db.session.add(album)

    album.spotify_id = payload["id"]
    album.title = payload["name"]
    album.artist_id = artist.id
    album.cover_seed = album.cover_seed or payload["name"]
    album.image_url = biggest_image(payload.get("images"))
    album.release_date = _parse_release_date(payload.get("release_date"))
    db.session.flush()

    if with_tracks:
        tracks = (payload.get("tracks") or {}).get("items") or []
        for item in tracks:
            # Album track objects omit the album, so graft it back on.
            item = dict(item, album=payload)
            import_track(item, album=album, artist=artist)

    db.session.flush()
    return album


def import_track(payload, album=None, artist=None):
    """Create-or-update a local Song from a Spotify track object."""
    if artist is None:
        artists = payload.get("artists") or []
        if not artists:
            raise SpotifyError("That track has no artist information.")
        artist = _ensure_artist(artists[0])

    if album is None:
        album_payload = payload.get("album") or {}
        if album_payload.get("id"):
            album = Album.query.filter_by(spotify_id=album_payload["id"]).first()
            if not album:
                album = import_album(album_payload, with_tracks=False)

    song = Song.query.filter_by(spotify_id=payload["id"]).first()
    if not song:
        song = Song(title=payload["name"], artist_id=artist.id)
        db.session.add(song)

    song.spotify_id = payload["id"]
    song.spotify_uri = payload.get("uri")
    song.title = payload["name"]
    song.artist_id = artist.id
    song.album_id = album.id if album else None
    song.track_number = payload.get("track_number") or 1
    song.duration = round((payload.get("duration_ms") or 0) / 1000)
    song.audio_url = payload.get("preview_url") or song.audio_url
    song.explicit = bool(payload.get("explicit"))
    song.popularity = payload.get("popularity") or 0
    if song.play_count is None:
        song.play_count = 0
    db.session.flush()
    return song


# --------------------------------------------------------------------------
# User authorisation (Authorization Code + PKCE)
# --------------------------------------------------------------------------
def make_pkce_pair():
    """Return ``(code_verifier, code_challenge)`` for the PKCE flow."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def authorize_url(state, code_challenge):
    cfg = current_app.config
    params = {
        "client_id": cfg["SPOTIFY_CLIENT_ID"],
        "response_type": "code",
        "redirect_uri": cfg["SPOTIFY_REDIRECT_URI"],
        "state": state,
        "scope": USER_SCOPES,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    return f"{ACCOUNTS}/authorize?" + urllib.parse.urlencode(params)


def exchange_code(code, code_verifier):
    cfg = current_app.config
    resp = requests.post(f"{ACCOUNTS}/api/token", data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["SPOTIFY_REDIRECT_URI"],
        "client_id": cfg["SPOTIFY_CLIENT_ID"],
        "code_verifier": code_verifier,
    }, timeout=TIMEOUT)
    if not resp.ok:
        raise SpotifyError("Spotify refused the authorisation code. "
                           "Check that the redirect URI matches exactly.")
    return resp.json()


def refresh_user_token(account):
    """Refresh and persist an expiring user token."""
    cfg = current_app.config
    if not account.refresh_token:
        raise SpotifyError("Spotify session expired. Reconnect your account.")

    resp = requests.post(f"{ACCOUNTS}/api/token", data={
        "grant_type": "refresh_token",
        "refresh_token": account.refresh_token,
        "client_id": cfg["SPOTIFY_CLIENT_ID"],
    }, timeout=TIMEOUT)
    if not resp.ok:
        raise SpotifyError("Spotify session expired. Reconnect your account.")

    payload = resp.json()
    account.access_token = payload["access_token"]
    if payload.get("refresh_token"):
        account.refresh_token = payload["refresh_token"]
    account.expires_at = utcnow() + timedelta(seconds=payload.get("expires_in", 3600))
    db.session.commit()
    return account


def user_token(user_id):
    """A valid access token for a linked user, refreshing if needed."""
    account = db.session.get(SpotifyAccount, user_id)
    if not account:
        return None
    if account.is_expired:
        refresh_user_token(account)
    return account.access_token


def save_user_account(user_id, payload):
    """Persist a token response plus the profile it belongs to."""
    profile = {}
    try:
        profile = api_get("/me", token=payload["access_token"])
    except SpotifyError:
        pass

    account = db.session.get(SpotifyAccount, user_id)
    if not account:
        account = SpotifyAccount(user_id=user_id)
        db.session.add(account)

    account.access_token = payload["access_token"]
    if payload.get("refresh_token"):
        account.refresh_token = payload["refresh_token"]
    account.expires_at = utcnow() + timedelta(seconds=payload.get("expires_in", 3600))
    account.scope = (payload.get("scope") or "")[:500]
    account.spotify_user_id = profile.get("id")
    account.display_name = profile.get("display_name")
    account.product = profile.get("product")
    account.linked_at = utcnow()
    db.session.commit()
    return account
