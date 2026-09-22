/* ---------------------------------------------------------------------------
 * api.js — fetch wrapper around the Flask JSON API + small helpers.
 *
 * This site is served from Vercel while the API lives on PythonAnywhere, so
 * requests are cross-origin. Cookies are unreliable across sites (Safari and
 * Chrome both block third-party cookies), so identity travels in an
 * `Authorization: Bearer` header instead. The token is issued at login and
 * kept in localStorage.
 * ------------------------------------------------------------------------- */
const Auth = {
  get token() { return localStorage.getItem(CONFIG.TOKEN_KEY) || ""; },
  set token(v) {
    if (v) localStorage.setItem(CONFIG.TOKEN_KEY, v);
    else localStorage.removeItem(CONFIG.TOKEN_KEY);
  },
  get user() {
    try { return JSON.parse(localStorage.getItem(CONFIG.USER_KEY) || "null"); }
    catch (e) { return null; }
  },
  set user(u) {
    if (u) localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(u));
    else localStorage.removeItem(CONFIG.USER_KEY);
  },
  save(token, user) { this.token = token; this.user = user; },
  clear() {
    this.token = null;
    this.user = null;
    localStorage.removeItem("player");
  },
  /* Send the user to the login page unless they're already signed in. */
  require() {
    if (!this.token) { location.replace("login.html"); return false; }
    return true;
  },
};

const API = {
  url(path) {
    return path.startsWith("http") ? path : CONFIG.API_BASE + path;
  },
  asset(path) {
    return !path || path.startsWith("http") || path.startsWith("data:")
      ? path : CONFIG.API_BASE + path;
  },

  async _req(method, path, body) {
    const opts = { method, headers: {} };
    if (Auth.token) opts.headers["Authorization"] = "Bearer " + Auth.token;
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }

    let res;
    try {
      res = await fetch(this.url(path), opts);
    } catch (e) {
      throw new Error("Can't reach the server. Check your connection.");
    }

    if (res.status === 401 && !path.startsWith("/api/auth/")) {
      Auth.clear();
      location.replace("login.html?expired=1");
      throw new Error("Session expired");
    }

    const data = res.status === 204 ? null
                 : await res.json().catch(() => null);
    if (!res.ok) {
      const err = new Error((data && data.error) || res.statusText || "Request failed");
      err.status = res.status;
      err.data = data || {};
      throw err;
    }
    return data;
  },

  get(u)     { return this._req("GET", u); },
  post(u, b) { return this._req("POST", u, b || {}); },
  put(u, b)  { return this._req("PUT", u, b || {}); },
  del(u)     { return this._req("DELETE", u); },

  // --- auth -------------------------------------------------------------
  register(d)        { return this.post("/api/auth/register", d); },
  verifyOtp(d)       { return this.post("/api/auth/verify", d); },
  resendOtp(email)   { return this.post("/api/auth/resend", { email }); },
  login(d)           { return this.post("/api/auth/login", d); },
  logout()           { return this.post("/api/auth/logout"); },
  developer()        { return this.get("/api/auth/developer"); },
  passwordHelp(d)    { return this.post("/api/auth/password-help", d); },
  changePassword(d)  { return this.put("/api/me/password", d); },
  updateProfile(d)   { return this.put("/api/me", d); },

  // --- catalog ----------------------------------------------------------
  me()                       { return this.get("/api/me"); },
  home()                     { return this.get("/api/home"); },
  search(q)                  { return this.get("/api/search?q=" + encodeURIComponent(q)); },
  album(id)                  { return this.get("/api/albums/" + id); },
  artist(id)                 { return this.get("/api/artists/" + id); },
  followArtist(id, on)       { return this._req(on ? "POST" : "DELETE", "/api/artists/" + id + "/follow"); },
  liked()                    { return this.get("/api/liked"); },
  like(id, on)               { return this._req(on ? "PUT" : "DELETE", "/api/songs/" + id + "/like"); },
  library()                  { return this.get("/api/library"); },
  recordPlay(songId)         { return this.post("/api/history", { song_id: songId }); },
  suggestMusic(data)         { return this.post("/api/music-suggestions", data); },

  // --- playlists --------------------------------------------------------
  playlists()                { return this.get("/api/playlists"); },
  createPlaylist(data)       { return this.post("/api/playlists", data); },
  playlist(id)               { return this.get("/api/playlists/" + id); },
  updatePlaylist(id, data)   { return this.put("/api/playlists/" + id, data); },
  deletePlaylist(id)         { return this.del("/api/playlists/" + id); },
  duplicatePlaylist(id)      { return this.post("/api/playlists/" + id + "/duplicate"); },
  addToPlaylist(id, songId)  { return this.post("/api/playlists/" + id + "/songs", { song_id: songId }); },
  addManyToPlaylist(id, ids) { return this.post("/api/playlists/" + id + "/songs", { song_ids: ids }); },
  removeFromPlaylist(id, s)  { return this.del("/api/playlists/" + id + "/songs/" + s); },
  reorderPlaylist(id, ids)   { return this.post("/api/playlists/" + id + "/reorder", { song_ids: ids }); },

  // --- queue ------------------------------------------------------------
  queue()                    { return this.get("/api/queue"); },
  replaceQueue(ids, index)   { return this.put("/api/queue", { song_ids: ids, index }); },
  queueAdd(ids, playNext)    { return this.post("/api/queue", { song_ids: ids, play_next: !!playNext }); },
  queueIndex(index)          { return this.put("/api/queue/index", { index }); },
  queueRemove(itemId)        { return this.del("/api/queue/" + itemId); },
  queueMove(from, to)        { return this.post("/api/queue/move", { from, to }); },
  queueClear()               { return this.del("/api/queue"); },

};

/* ---- formatting helpers ---- */
function fmtTime(sec) {
  sec = Math.max(0, Math.floor(sec || 0));
  const m = Math.floor(sec / 60), s = sec % 60;
  return m + ":" + String(s).padStart(2, "0");
}
function fmtCount(n) {
  n = n || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return "" + n;
}
function fmtTotalDuration(sec) {
  sec = Math.floor(sec || 0);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h} hr ${m} min`;
  const s = sec % 60;
  return m > 0 ? `${m} min ${s} sec` : `${s} sec`;
}
function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

/* ---- toast ---- */
let _toastTimer;
function toast(msg) {
  const box = document.getElementById("toast");
  if (!box) return;
  document.getElementById("toast-msg").textContent = msg;
  box.classList.remove("hidden");
  void box.offsetWidth;               // force reflow so the pop replays
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => box.classList.add("hidden"), 2400);
}
