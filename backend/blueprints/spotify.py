"""Spotify endpoints, mounted at ``/api/spotify``.

Catalog browsing uses the app's own client credentials, so it works for every
signed-in user.  Streaming full tracks needs each listener to connect their own
**Premium** account: that runs an Authorization Code + PKCE flow whose redirect
lands back here, then the browser picks the token up for the Web Playback SDK.
"""
from datetime import timedelta

from flask import (Blueprint, current_app, jsonify, redirect, request,
                   url_for)
from flask_login import current_user, login_required

from extensions import db
from models import OAuthState, SpotifyAccount, utcnow
from services import spotify_client as sp
from services import tokens

spotify_bp = Blueprint("spotify", __name__)

STATE_TTL_MINUTES = 15


def _fail(exc, status=502):
    return jsonify(error=str(exc)), status


def _frontend(path=""):
    base = (current_app.config["FRONTEND_URL"] or "").rstrip("/")
    return f"{base}{path}"


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------
@spotify_bp.route("/status")
@login_required
def status():
    """What the client needs to decide which player to use."""
    account = db.session.get(SpotifyAccount, current_user.id)
    return jsonify({
        "configured": bool(current_app.config["SPOTIFY_CLIENT_ID"]
                           and current_app.config["SPOTIFY_CLIENT_SECRET"]),
        "connected": account is not None,
        "display_name": account.display_name if account else None,
        "product": account.product if account else None,
        # Only Premium accounts may stream through the Web Playback SDK.
        "can_stream": bool(account and account.product == "premium"),
    })


# --------------------------------------------------------------------------
# Catalog (app credentials)
# --------------------------------------------------------------------------
@spotify_bp.route("/search")
@login_required
def search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify(query="", tracks=[], artists=[], albums=[])

    types = request.args.get("type", "track,artist,album")
    limit = request.args.get("limit", 20)
    try:
        payload = sp.search(query, types=types, limit=int(limit))
    except (sp.SpotifyError, ValueError) as exc:
        return _fail(exc)

    tracks = [sp.summarize_track(t)
              for t in (payload.get("tracks") or {}).get("items", []) if t]
    artists = [{
        "spotify_id": a["id"], "name": a["name"],
        "image": sp.biggest_image(a.get("images")),
        "genres": a.get("genres") or [],
        "followers": (a.get("followers") or {}).get("total") or 0,
    } for a in (payload.get("artists") or {}).get("items", []) if a]
    albums = [{
        "spotify_id": a["id"], "title": a["name"],
        "artist": (a.get("artists") or [{}])[0].get("name", ""),
        "image": sp.biggest_image(a.get("images")),
        "year": (a.get("release_date") or "")[:4],
        "total_tracks": a.get("total_tracks") or 0,
    } for a in (payload.get("albums") or {}).get("items", []) if a]

    return jsonify(query=query, tracks=tracks, artists=artists, albums=albums)


@spotify_bp.route("/albums/<spotify_id>")
@login_required
def album(spotify_id):
    try:
        payload = sp.get_album(spotify_id)
    except sp.SpotifyError as exc:
        return _fail(exc)
    tracks = [sp.summarize_track(dict(t, album=payload))
              for t in (payload.get("tracks") or {}).get("items", [])]
    return jsonify({
        "spotify_id": payload["id"],
        "title": payload["name"],
        "artist": (payload.get("artists") or [{}])[0].get("name", ""),
        "image": sp.biggest_image(payload.get("images")),
        "year": (payload.get("release_date") or "")[:4],
        "tracks": tracks,
    })


# --------------------------------------------------------------------------
# Connecting a listener's own Spotify account (Authorization Code + PKCE)
# --------------------------------------------------------------------------
@spotify_bp.route("/authorize")
@login_required
def authorize():
    """Return the URL the browser should visit to grant access.

    The client navigates there itself, which keeps this call CORS-friendly —
    a 302 across origins would be swallowed by fetch().
    """
    if not current_app.config["SPOTIFY_CLIENT_ID"]:
        return jsonify(error="Spotify is not configured on the server."), 503

    # Housekeeping: drop states nobody came back for.
    OAuthState.query.filter(
        OAuthState.created_at < utcnow() - timedelta(minutes=STATE_TTL_MINUTES)
    ).delete(synchronize_session=False)

    verifier, challenge = sp.make_pkce_pair()
    state = OAuthState.new_state()
    return_to = request.args.get("return_to") or _frontend("/")
    db.session.add(OAuthState(state=state, user_id=current_user.id,
                              code_verifier=verifier, return_to=return_to[:300]))
    db.session.commit()

    return jsonify(url=sp.authorize_url(state, challenge), state=state)


@spotify_bp.route("/callback")
def callback():
    """Where Spotify sends the browser back.

    This runs without any session — the ``state`` we minted identifies the
    user, which is exactly what it is for.
    """
    state = request.args.get("state") or ""
    row = db.session.get(OAuthState, state)
    if not row:
        return redirect(_frontend("/?spotify=invalid_state"))

    # Read everything off the row before deleting it — the instance is expired
    # once the delete is committed.
    return_to = row.return_to or _frontend("/")
    verifier, user_id = row.code_verifier, row.user_id
    error = request.args.get("error")
    code = request.args.get("code")

    db.session.delete(row)          # single-use: a state never works twice
    db.session.commit()

    if error or not code:
        return redirect(f"{return_to}?spotify=denied")

    try:
        payload = sp.exchange_code(code, verifier)
        sp.save_user_account(user_id, payload)
    except sp.SpotifyError:
        return redirect(f"{return_to}?spotify=failed")

    return redirect(f"{return_to}?spotify=connected")


@spotify_bp.route("/token")
@login_required
def playback_token():
    """A fresh access token for the Web Playback SDK in the browser.

    Short-lived by design — the SDK calls back here whenever it needs a new one.
    """
    account = db.session.get(SpotifyAccount, current_user.id)
    if not account:
        return jsonify(error="No Spotify account linked.", code="not_linked"), 404
    try:
        token = sp.user_token(current_user.id)
    except sp.SpotifyError as exc:
        return jsonify(error=str(exc), code="reauth_required"), 401

    return jsonify({
        "access_token": token,
        "product": account.product,
        "can_stream": account.product == "premium",
        "expires_at": account.expires_at.isoformat(),
    })


@spotify_bp.route("/disconnect", methods=["POST", "DELETE"])
@login_required
def disconnect():
    account = db.session.get(SpotifyAccount, current_user.id)
    if account:
        db.session.delete(account)
        db.session.commit()
    return jsonify(ok=True, connected=False)


# --------------------------------------------------------------------------
# Small helper so the front-end can build its own "connect" link
# --------------------------------------------------------------------------
@spotify_bp.route("/connect")
@login_required
def connect():
    """Same as /authorize but performs the redirect server-side.

    Handy for the admin panel, which is same-origin and can just follow a link.
    """
    response = authorize()
    if isinstance(response, tuple):          # an error tuple from authorize()
        return response
    return redirect(response.get_json()["url"])


@spotify_bp.route("/link")
def link_with_token():
    """Start the flow from a plain ``<a href>`` that carries a Bearer token.

    Browsers can't set headers when following a link, so the Vercel client
    passes ``?token=`` here; ``tokens.from_request`` accepts either form.
    """
    user = tokens.resolve(tokens.from_request())
    if not user:
        return redirect(_frontend("/login.html"))

    verifier, challenge = sp.make_pkce_pair()
    state = OAuthState.new_state()
    return_to = request.args.get("return_to") or _frontend("/")
    db.session.add(OAuthState(state=state, user_id=user.id,
                              code_verifier=verifier, return_to=return_to[:300]))
    db.session.commit()
    return redirect(sp.authorize_url(state, challenge))


@spotify_bp.route("/redirect-uri")
def redirect_uri_hint():
    """Prints the exact Redirect URI to paste into the Spotify dashboard."""
    return jsonify({
        "configured": current_app.config["SPOTIFY_REDIRECT_URI"],
        "should_be": url_for("spotify.callback", _external=True),
    })
