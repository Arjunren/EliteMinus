/* ---------------------------------------------------------------------------
 * player.js — the audio engine. One <audio> element drives the whole app and
 * survives client-side navigation, so music keeps playing as you browse.
 * ------------------------------------------------------------------------- */
const Player = {
  audio: null,
  queue: [],
  index: -1,
  shuffle: false,
  repeat: "off",          // off | all | one
  _seeking: false,
  _recorded: false,

  get current() { return this.queue[this.index] || null; },
  get isPlaying() { return this.audio && !this.audio.paused; },

  init() {
    this.audio = document.getElementById("audio");

    const savedVol = parseFloat(localStorage.getItem("vol"));
    const v = isNaN(savedVol) ? 0.7 : savedVol;
    this.audio.volume = v;
    const volEl = document.getElementById("volume");
    volEl.value = Math.round(v * 100);
    this._fill(volEl);

    this._bindControls();
    this._bindAudio();
    this._restore();
  },

  /* ---------------- public API ---------------- */
  play(tracks, index = 0) {
    if (!tracks || !tracks.length) return;
    this.queue = tracks.slice();
    this.index = Math.max(0, Math.min(index, tracks.length - 1));
    this._load(true);
  },

  playOne(song) { if (song) this.play([song], 0); },

  toggle() {
    if (!this.current) {
      if (UI.viewTracks && UI.viewTracks.length) this.play(UI.viewTracks, 0);
      return;
    }
    if (this.audio.paused) this.audio.play().catch(() => {});
    else this.audio.pause();
  },

  next(manual = false) {
    if (!this.queue.length) return;
    if (this.repeat === "one" && !manual) { this._restart(); return; }
    let n;
    if (this.shuffle) {
      n = this.queue.length > 1 ? this._randomOther() : this.index;
    } else {
      n = this.index + 1;
      if (n >= this.queue.length) {
        if (this.repeat === "all" || manual) n = 0;
        else { this.audio.pause(); this.audio.currentTime = 0; return; }
      }
    }
    this.index = n;
    this._load(true);
  },

  prev() {
    if (!this.queue.length) return;
    if (this.audio.currentTime > 3) { this.audio.currentTime = 0; return; }
    let n = this.index - 1;
    if (n < 0) n = this.repeat === "all" ? this.queue.length - 1 : 0;
    this.index = n;
    this._load(true);
  },

  toggleLikeCurrent() {
    const s = this.current;
    if (!s) return;
    const next = !s.liked;
    API.like(s.id, next).then(() => {
      applyLikeState(s.id, next);
      toast(next ? "Added to Liked Songs" : "Removed from Liked Songs");
    }).catch(() => toast("Could not update Liked Songs"));
  },

  /* ---------------- internals ---------------- */
  _restart() { this.audio.currentTime = 0; this.audio.play().catch(() => {}); },

  _randomOther() {
    let n;
    do { n = Math.floor(Math.random() * this.queue.length); }
    while (n === this.index && this.queue.length > 1);
    return n;
  },

  _load(autoplay) {
    const s = this.current;
    if (!s) return;
    this.audio.src = s.audio_url;
    this._recorded = false;
    if (autoplay) {
      const p = this.audio.play();
      if (p && p.catch) p.catch(() => {});  // autoplay may be blocked initially
    }
    this._renderNowPlaying();
    this._persist();
  },

  _bindControls() {
    document.getElementById("btn-play").onclick = () => this.toggle();
    document.getElementById("btn-next").onclick = () => this.next(true);
    document.getElementById("btn-prev").onclick = () => this.prev();

    const shuffleBtn = document.getElementById("btn-shuffle");
    shuffleBtn.onclick = () => {
      this.shuffle = !this.shuffle;
      shuffleBtn.classList.toggle("text-brand", this.shuffle);
      shuffleBtn.classList.toggle("text-neutral-400", !this.shuffle);
    };

    const repeatBtn = document.getElementById("btn-repeat");
    repeatBtn.onclick = () => {
      this.repeat = this.repeat === "off" ? "all" : this.repeat === "all" ? "one" : "off";
      repeatBtn.classList.toggle("text-brand", this.repeat !== "off");
      repeatBtn.classList.toggle("text-neutral-400", this.repeat === "off");
      document.getElementById("repeat-one").classList.toggle("hidden", this.repeat !== "one");
    };

    document.getElementById("np-like").onclick = () => this.toggleLikeCurrent();
    document.getElementById("np-title").onclick = () => {
      if (this.current && this.current.album) location.hash = "#/album/" + this.current.album.id;
    };
    document.getElementById("np-artist").onclick = () => {
      if (this.current) location.hash = "#/artist/" + this.current.artist.id;
    };

    // seek bar
    const seek = document.getElementById("seek");
    seek.addEventListener("input", () => {
      this._seeking = true;
      const d = this.audio.duration || 0;
      document.getElementById("cur-time").textContent = fmtTime((seek.value / 100) * d);
      this._fill(seek);
    });
    seek.addEventListener("change", () => {
      const d = this.audio.duration || 0;
      this.audio.currentTime = (seek.value / 100) * d;
      this._seeking = false;
    });

    // volume
    const vol = document.getElementById("volume");
    vol.addEventListener("input", () => {
      const v = vol.value / 100;
      this.audio.volume = v;
      this.audio.muted = false;
      localStorage.setItem("vol", v);
      this._fill(vol);
      this._updateVolIcon();
    });
    document.getElementById("btn-mute").onclick = () => {
      this.audio.muted = !this.audio.muted;
      this._updateVolIcon();
    };

    // spacebar play/pause
    document.addEventListener("keydown", (e) => {
      const tag = (e.target.tagName || "").toLowerCase();
      if (e.code === "Space" && tag !== "input" && tag !== "textarea") {
        e.preventDefault();
        this.toggle();
      }
    });
  },

  _bindAudio() {
    const a = this.audio;
    a.addEventListener("play", () => {
      this._updatePlayIcon();
      UI.markPlaying();
      if (!this._recorded && this.current) {
        this._recorded = true;
        API.recordPlay(this.current.id).catch(() => {});
      }
    });
    a.addEventListener("pause", () => { this._updatePlayIcon(); UI.markPlaying(); });
    a.addEventListener("ended", () => this.next(false));
    a.addEventListener("loadedmetadata", () => {
      document.getElementById("dur-time").textContent = fmtTime(a.duration);
    });
    a.addEventListener("timeupdate", () => {
      if (this._seeking) return;
      const d = a.duration || 0;
      const seek = document.getElementById("seek");
      seek.value = d ? (a.currentTime / d) * 100 : 0;
      this._fill(seek);
      document.getElementById("cur-time").textContent = fmtTime(a.currentTime);
    });
  },

  _renderNowPlaying() {
    const s = this.current;
    if (!s) return;
    const cover = document.getElementById("np-cover");
    cover.src = s.image; cover.classList.remove("hidden");
    document.getElementById("np-title").textContent = s.title;
    document.getElementById("np-artist").textContent = s.artist.name;
    document.getElementById("dur-time").textContent = fmtTime(s.duration);
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
    const s = this.current;
    const btn = document.getElementById("np-like");
    if (!s) return;
    btn.innerHTML = s.liked ? ICON.heartFill : ICON.heart;
    btn.classList.toggle("text-brand", !!s.liked);
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

  /* persist current queue so a page refresh keeps your place (paused) */
  _persist() {
    try {
      localStorage.setItem("player", JSON.stringify({
        queue: this.queue, index: this.index,
      }));
    } catch (e) { /* ignore quota errors */ }
  },

  _restore() {
    try {
      const raw = localStorage.getItem("player");
      if (!raw) return;
      const st = JSON.parse(raw);
      if (st.queue && st.queue.length && st.index >= 0) {
        this.queue = st.queue;
        this.index = st.index;
        this._load(false);            // show it, but don't auto-blast audio
      }
    } catch (e) { /* ignore */ }
  },
};

/* keep the on-screen track highlight in sync with what's playing */
UI.markPlaying = function () {
  const cur = Player.current;
  document.querySelectorAll("[data-song-row]").forEach((row) => {
    row.classList.toggle("is-playing", !!(cur && +row.dataset.songId === cur.id));
  });
};
