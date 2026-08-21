/* ---------------------------------------------------------------------------
 * spotify.js — full-track playback through the Spotify Web Playback SDK.
 *
 * How playback is chosen, per track:
 *   1. the listener has connected a Spotify **Premium** account AND the track
 *      was imported from Spotify (it has a `spotify_uri`)  -> full track
 *   2. otherwise -> the plain <audio> element with `audio_url`
 *      (a 30-second Spotify preview, or a self-hosted mp3)
 *
 * The SDK only streams for Premium subscribers — that is Spotify's rule, not
 * ours. Free accounts still get search, imports, previews and everything else.
 * ------------------------------------------------------------------------- */
const Spotify = {
  status: null,        // last /api/spotify/status payload
  player: null,        // the SDK player instance
  deviceId: null,
  ready: false,
  _sdkLoading: null,
  _volume: 0.7,
  onState: null,       // set by player.js

  get connected() { return !!(this.status && this.status.connected); },
  get canStream() { return !!(this.status && this.status.can_stream); },

  /* ---------------- setup ---------------- */
  async init() {
    try {
      this.status = await API.spotifyStatus();
    } catch (e) {
      this.status = { configured: false, connected: false, can_stream: false };
    }
    this.renderButton();
    this.handleReturn();
    if (this.canStream) this.connect().catch(() => {});
    return this.status;
  },

  /** Show the outcome of the OAuth round-trip, then tidy the URL. */
  handleReturn() {
    const params = new URLSearchParams(location.search);
    const result = params.get("spotify");
    if (!result) return;

    const messages = {
      connected: "Spotify connected",
      denied: "Spotify connection cancelled",
      failed: "Spotify connection failed — check the redirect URI",
      invalid_state: "That Spotify link expired. Try connecting again.",
    };
    if (messages[result]) toast(messages[result]);
    history.replaceState(null, "", location.pathname + location.hash);
  },

  renderButton() {
    const button = document.getElementById("btn-spotify");
    const label = document.getElementById("spotify-label");
    if (!button || !this.status || !this.status.configured) return;

    button.classList.remove("hidden");
    button.classList.add("flex");
    if (!this.connected) {
      label.textContent = "Connect Spotify";
      button.title = "Link your Spotify account to stream full tracks";
    } else if (this.canStream) {
      label.textContent = this.status.display_name || "Premium";
      button.title = "Spotify Premium connected — full tracks are streaming";
    } else {
      label.textContent = "Spotify (free)";
      button.title = "Connected, but full-track streaming needs Spotify Premium";
    }
  },

  /** Send the browser off to Spotify's consent screen. */
  link() {
    if (!this.status || !this.status.configured) {
      toast("Spotify isn't configured on the server");
      return;
    }
    location.href = API.spotifyLinkUrl();
  },

  async disconnect() {
    await API.spotifyDisconnect();
    if (this.player) { this.player.disconnect(); this.player = null; }
    this.ready = false;
    this.deviceId = null;
    this.status = await API.spotifyStatus();
    this.renderButton();
    toast("Spotify disconnected");
  },

  /* ---------------- SDK ---------------- */
  _loadSdk() {
    if (this._sdkLoading) return this._sdkLoading;
    this._sdkLoading = new Promise((resolve, reject) => {
      if (window.Spotify && window.Spotify.Player) return resolve();
      window.onSpotifyWebPlaybackSDKReady = resolve;
      const script = document.createElement("script");
      script.src = "https://sdk.scdn.co/spotify-player.js";
      script.async = true;
      script.onerror = () => reject(new Error("Could not load the Spotify SDK"));
      document.head.appendChild(script);
    });
    return this._sdkLoading;
  },

  async connect() {
    if (this.ready || !this.canStream) return this.ready;
    await this._loadSdk();

    // The SDK asks for a token on connect and again whenever one expires, so
    // this callback is the single place tokens are refreshed.
    const player = new window.Spotify.Player({
      name: "EliteMinus Web Player",
      volume: this._volume,
      getOAuthToken: (cb) => {
        API.spotifyToken()
          .then((res) => cb(res.access_token))
          .catch(() => toast("Spotify session expired — reconnect your account"));
      },
    });

    player.addListener("ready", ({ device_id }) => {
      this.deviceId = device_id;
      this.ready = true;
    });
    player.addListener("not_ready", () => { this.ready = false; });
    player.addListener("player_state_changed", (state) => {
      if (state && this.onState) this.onState(state);
    });
    ["initialization_error", "authentication_error", "account_error",
     "playback_error"].forEach((event) => {
      player.addListener(event, ({ message }) => {
        console.warn("Spotify " + event + ":", message);
        if (event === "account_error")
          toast("Spotify Premium is required to stream full tracks");
      });
    });

    const ok = await player.connect();
    this.player = player;
    return ok;
  },

  /* ---------------- transport ---------------- */
  /** True when this track can play as a full Spotify stream. */
  canPlay(song) {
    return !!(song && song.spotify_uri && this.canStream && this.ready);
  },

  async playTrack(uri) {
    if (!this.deviceId) throw new Error("Spotify player isn't ready yet");
    const token = (await API.spotifyToken()).access_token;
    const res = await fetch(
      "https://api.spotify.com/v1/me/player/play?device_id=" + this.deviceId, {
        method: "PUT",
        headers: {
          "Authorization": "Bearer " + token,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ uris: [uri] }),
      });
    if (!res.ok && res.status !== 204) {
      throw new Error("Spotify refused to start that track");
    }
  },

  resume() { return this.player && this.player.resume(); },
  pause() { return this.player && this.player.pause(); },
  seek(ms) { return this.player && this.player.seek(ms); },
  setVolume(v) {
    this._volume = v;
    return this.player && this.player.setVolume(v);
  },
  async position() {
    if (!this.player) return null;
    return this.player.getCurrentState();
  },
};
