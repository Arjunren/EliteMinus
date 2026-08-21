/* ---------------------------------------------------------------------------
 * player.js — the audio engine.
 *
 * The queue lives in queue.js; this file only decides *how* the current entry
 * is played and drives the transport bar. Two back-ends:
 *
 *   "spotify" — full track via the Web Playback SDK (Premium accounts only)
 *   "audio"   — the <audio> element, playing `audio_url` (preview or mp3)
 *
 * Which one is used is decided per track in `loadCurrent`, so a queue can mix
 * imported Spotify tracks and locally hosted ones without the user noticing.
 * ------------------------------------------------------------------------- */
const Player = {
  audio: null,
  mode: "audio",
  shuffle: false,
  repeat: "off",          // off | all | one
  _seeking: false,
  _recorded: false,
  _skips: 0,              // guards against looping over unplayable tracks
  _spotifyTimer: null,
  _spotifyPos: 0,
  _spotifyDur: 0,
  _spotifyPaused: true,

  get current() { return Queue.current; },
  get isPlaying() {
    return this.mode === "spotify" ? !this._spotifyPaused
                                   : !!(this.audio && !this.audio.paused);
  },

  init() {
    this.audio = document.getElementById("audio");

    const saved = parseFloat(localStorage.getItem("vol"));
    const volume = isNaN(saved) ? 0.7 : saved;
    this.audio.volume = volume;
    const volEl = document.getElementById("volume");
    volEl.value = Math.round(volume * 100);
    this._fill(volEl);

    Spotify.onState = (state) => this._onSpotifyState(state);

    this._bindControls();
    this._bindAudio();
  },

  /* ---------------- public API ---------------- */
  /** Play a list of tracks — this replaces the queue, like Spotify does. */
  async play(tracks, index = 0) {
    if (!tracks || !tracks.length) return;
    await Queue.replace(tracks, index);
    this.loadCurrent(true);
  },

  playOne(song) { if (song) this.play([song], 0); },

  toggle() {
    if (!this.current) {
      if (UI.viewTracks && UI.viewTracks.length) this.play(UI.viewTracks, 0);
      return;
    }
    if (this.mode === "spotify") {
      if (this._spotifyPaused) Spotify.resume();
      else Spotify.pause();
      return;
    }
    if (this.audio.paused) {
      // A track loaded but never started has no src yet if it was restored.
      if (!this.audio.src) { this.loadCurrent(true); return; }
      this.audio.play().catch(() => {});
    } else {
      this.audio.pause();
    }
  },

  next(manual = false) {
    if (!Queue.length) return;
    if (this.repeat === "one" && !manual) { this._restart(); return; }

    let n;
    if (this.shuffle && Queue.length > 1) {
      n = this._randomOther();
    } else {
      n = Queue.index + 1;
      if (n >= Queue.length) {
        if (this.repeat === "all" || manual) n = 0;
        else { this._stop(); return; }
      }
    }
    Queue.setIndex(n);
    this.loadCurrent(true);
  },

  prev() {
    if (!Queue.length) return;
    if (this.position() > 3) { this.seekTo(0); return; }
    let n = Queue.index - 1;
    if (n < 0) n = this.repeat === "all" ? Queue.length - 1 : 0;
    Queue.setIndex(n);
    this.loadCurrent(true);
  },

  /** Load whatever the queue currently points at. */
  async loadCurrent(autoplay) {
    const song = this.current;
    if (!song) { this._stop(); this._renderNowPlaying(); return; }
    this._recorded = false;

    if (Spotify.canPlay(song)) {
      this._useSpotify(song, autoplay);
    } else if (song.audio_url) {
      this._useAudio(song, autoplay);
    } else {
      // Imported from Spotify but no preview, and the listener isn't Premium.
      this._skips++;
      this._renderNowPlaying();
      if (this._skips > 3 || !autoplay) {
        this._skips = 0;
        toast(song.spotify_uri
          ? "Connect Spotify Premium to play this track"
          : "This track has no playable audio");
        return;
      }
      this.next(false);
      return;
    }
    this._skips = 0;
    this._renderNowPlaying();
  },

  toggleLikeCurrent() {
    const song = this.current;
    if (!song) return;
    const next = !song.liked;
    API.like(song.id, next).then(() => {
      applyLikeState(song.id, next);
      toast(next ? "Added to Liked Songs" : "Removed from Liked Songs");
    }).catch(() => toast("Could not update Liked Songs"));
  },

  /* ---------------- back-end: <audio> ---------------- */
  _useAudio(song, autoplay) {
    this._stopSpotifyPolling();
    if (this.mode === "spotify") Spotify.pause();
    this.mode = "audio";
    this.audio.src = song.audio_url;
    if (autoplay) {
      const p = this.audio.play();
      if (p && p.catch) p.catch(() => {});  // autoplay may be blocked initially
    }
  },

  /* ---------------- back-end: Spotify SDK ---------------- */
  async _useSpotify(song, autoplay) {
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.mode = "spotify";
    this._spotifyDur = (song.duration || 0) * 1000;
    this._spotifyPos = 0;

    if (!autoplay) { this._spotifyPaused = true; this._updatePlayIcon(); return; }
    try {
      await Spotify.playTrack(song.spotify_uri);
      this._spotifyPaused = false;
      this._startSpotifyPolling();
    } catch (err) {
      toast(err.message || "Spotify playback failed");
      // Fall back to the preview rather than leaving the user stuck.
      if (song.audio_url) this._useAudio(song, true);
    }
  },

  _onSpotifyState(state) {
    if (this.mode !== "spotify") return;
    const wasPlaying = !this._spotifyPaused;
    this._spotifyPaused = state.paused;
    this._spotifyPos = state.position;
    this._spotifyDur = state.duration || this._spotifyDur;

    // The SDK reports a finished track as paused at position 0.
    if (state.paused && state.position === 0 && wasPlaying) {
      this.next(false);
      return;
    }
    this._updatePlayIcon();
    this._recordPlayOnce();
    UI.markPlaying();
  },

  _startSpotifyPolling() {
    this._stopSpotifyPolling();
    this._spotifyTimer = setInterval(async () => {
      const state = await Spotify.position();
      if (!state) return;
      this._spotifyPos = state.position;
      this._spotifyDur = state.duration || this._spotifyDur;
      this._spotifyPaused = state.paused;
      if (!this._seeking) this._renderProgress(state.position / 1000,
                                               state.duration / 1000);
      this._updatePlayIcon();
      this._recordPlayOnce();
    }, 500);
  },

  _stopSpotifyPolling() {
    if (this._spotifyTimer) clearInterval(this._spotifyTimer);
    this._spotifyTimer = null;
  },

  /* ---------------- transport helpers ---------------- */
  position() {
    return this.mode === "spotify" ? this._spotifyPos / 1000
                                   : (this.audio.currentTime || 0);
  },
  duration() {
    if (this.mode === "spotify") return this._spotifyDur / 1000;
    return this.audio.duration || (this.current ? this.current.duration : 0) || 0;
  },
  seekTo(seconds) {
    if (this.mode === "spotify") Spotify.seek(Math.round(seconds * 1000));
    else this.audio.currentTime = seconds;
  },
  _restart() { this.seekTo(0); if (!this.isPlaying) this.toggle(); },
  _stop() {
    this._stopSpotifyPolling();
    if (this.mode === "spotify") Spotify.pause();
    else { this.audio.pause(); this.audio.currentTime = 0; }
    this._updatePlayIcon();
  },

  _randomOther() {
    let n;
    do { n = Math.floor(Math.random() * Queue.length); }
    while (n === Queue.index && Queue.length > 1);
    return n;
  },

  _recordPlayOnce() {
    if (this._recorded || !this.current || !this.isPlaying) return;
    this._recorded = true;
    API.recordPlay(this.current.id).catch(() => {});
  },

  /* ---------------- wiring ---------------- */
  _bindControls() {
    document.getElementById("btn-play").onclick = () => this.toggle();
    document.getElementById("btn-next").onclick = () => this.next(true);
    document.getElementById("btn-prev").onclick = () => this.prev();

    const shuffleBtn = document.getElementById("btn-shuffle");
    shuffleBtn.onclick = () => {
      this.shuffle = !this.shuffle;
      shuffleBtn.classList.toggle("text-brand", this.shuffle);
      shuffleBtn.classList.toggle("text-neutral-400", !this.shuffle);
      toast(this.shuffle ? "Shuffle on" : "Shuffle off");
    };

    const repeatBtn = document.getElementById("btn-repeat");
    repeatBtn.onclick = () => {
      this.repeat = this.repeat === "off" ? "all"
                  : this.repeat === "all" ? "one" : "off";
      repeatBtn.classList.toggle("text-brand", this.repeat !== "off");
      repeatBtn.classList.toggle("text-neutral-400", this.repeat === "off");
      document.getElementById("repeat-one")
        .classList.toggle("hidden", this.repeat !== "one");
    };

    document.getElementById("np-like").onclick = () => this.toggleLikeCurrent();
    document.getElementById("np-title").onclick = () => {
      if (this.current && this.current.album)
        location.hash = "#/album/" + this.current.album.id;
    };
    document.getElementById("np-artist").onclick = () => {
      if (this.current && this.current.artist)
        location.hash = "#/artist/" + this.current.artist.id;
    };

    // seek bar
    const seek = document.getElementById("seek");
    seek.addEventListener("input", () => {
      this._seeking = true;
      document.getElementById("cur-time").textContent =
        fmtTime((seek.value / 100) * this.duration());
      this._fill(seek);
    });
    seek.addEventListener("change", () => {
      this.seekTo((seek.value / 100) * this.duration());
      this._seeking = false;
    });

    // volume
    const vol = document.getElementById("volume");
    vol.addEventListener("input", () => {
      const v = vol.value / 100;
      this.audio.volume = v;
      this.audio.muted = false;
      Spotify.setVolume(v);
      localStorage.setItem("vol", v);
      this._fill(vol);
      this._updateVolIcon();
    });
    document.getElementById("btn-mute").onclick = () => {
      this.audio.muted = !this.audio.muted;
      Spotify.setVolume(this.audio.muted ? 0 : this.audio.volume);
      this._updateVolIcon();
    };

    // keyboard shortcuts
    document.addEventListener("keydown", (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea") return;
      if (e.code === "Space") { e.preventDefault(); this.toggle(); }
      else if (e.code === "ArrowRight" && e.shiftKey) this.next(true);
      else if (e.code === "ArrowLeft" && e.shiftKey) this.prev();
    });
  },

  _bindAudio() {
    const a = this.audio;
    a.addEventListener("play", () => {
      this._updatePlayIcon();
      UI.markPlaying();
      this._recordPlayOnce();
    });
    a.addEventListener("pause", () => { this._updatePlayIcon(); UI.markPlaying(); });
    a.addEventListener("ended", () => this.next(false));
    a.addEventListener("error", () => {
      if (this.mode === "audio" && this.current) toast("Could not load that track");
    });
    a.addEventListener("loadedmetadata", () => {
      document.getElementById("dur-time").textContent = fmtTime(a.duration);
    });
    a.addEventListener("timeupdate", () => {
      if (this._seeking || this.mode !== "audio") return;
      this._renderProgress(a.currentTime, a.duration || 0);
    });
  },

  /* ---------------- rendering ---------------- */
  _renderProgress(current, total) {
    const seek = document.getElementById("seek");
    seek.value = total ? (current / total) * 100 : 0;
    this._fill(seek);
    document.getElementById("cur-time").textContent = fmtTime(current);
    document.getElementById("dur-time").textContent = fmtTime(total);
  },

  _renderNowPlaying() {
    const song = this.current;
    const cover = document.getElementById("np-cover");
    const source = document.getElementById("np-source");

    if (!song) {
      cover.classList.add("hidden");
      document.getElementById("np-title").textContent = "—";
      document.getElementById("np-artist").textContent = "";
      source.classList.add("hidden");
      this._renderProgress(0, 0);
      return;
    }

    cover.src = song.image;
    cover.classList.remove("hidden");
    document.getElementById("np-title").textContent = song.title;
    document.getElementById("np-artist").textContent =
      song.artist ? song.artist.name : "";
    document.getElementById("dur-time").textContent = fmtTime(song.duration);

    // Tell the user which source they're hearing — full track or 30s preview.
    if (this.mode === "spotify") {
      source.textContent = "▸ Spotify · full track";
      source.classList.remove("hidden");
    } else if (song.spotify_uri) {
      source.textContent = "▸ 30-second preview";
      source.classList.remove("hidden");
    } else {
      source.classList.add("hidden");
    }

    this._updateLikeIcon();
    this._updatePlayIcon();
    UI.markPlaying();
  },

  _updatePlayIcon() {
    const playing = this.isPlaying;
    document.getElementById("icon-play").classList.toggle("hidden", playing);
    document.getElementById("icon-pause").classList.toggle("hidden", !playing);
    document.getElementById("btn-play").title = playing ? "Pause" : "Play";
  },

  _updateLikeIcon() {
    const song = this.current;
    const btn = document.getElementById("np-like");
    if (!song) return;
    btn.innerHTML = song.liked ? ICON.heartFill : ICON.heart;
    btn.classList.toggle("text-brand", !!song.liked);
  },

  _updateVolIcon() {
    const muted = this.audio.muted || this.audio.volume === 0;
    document.getElementById("icon-vol").classList.toggle("hidden", muted);
    document.getElementById("icon-mute").classList.toggle("hidden", !muted);
  },

  _fill(el) {
    const pct = (el.value - el.min) / (el.max - el.min) * 100;
    el.style.setProperty("--pct", pct + "%");
  },
};

/* keep the on-screen track highlight in sync with what's playing */
UI.markPlaying = function () {
  const cur = Player.current;
  document.querySelectorAll("[data-song-row]").forEach((row) => {
    row.classList.toggle("is-playing", !!(cur && +row.dataset.songId === cur.id));
  });
};
