/* ---------------------------------------------------------------------------
 * api.js — thin fetch wrapper around the Flask JSON API + small helpers.
 * Cookies (Flask session) ride along automatically for same-origin requests.
 * ------------------------------------------------------------------------- */
const API = {
  async _req(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (res.status === 401) {            // session expired -> back to login
      window.location.href = "/login";
      throw new Error("Not authenticated");
    }
    const data = res.status === 204 ? null
                 : await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.error) || res.statusText);
    return data;
  },
  get(u)        { return this._req("GET", u); },
  post(u, b)    { return this._req("POST", u, b || {}); },
  put(u, b)     { return this._req("PUT", u, b || {}); },
  del(u)        { return this._req("DELETE", u); },

  // domain helpers ---------------------------------------------------------
  me()                       { return this.get("/api/me"); },
  home()                     { return this.get("/api/home"); },
  search(q)                  { return this.get("/api/search?q=" + encodeURIComponent(q)); },
  album(id)                  { return this.get("/api/albums/" + id); },
  artist(id)                 { return this.get("/api/artists/" + id); },
  followArtist(id, on)       { return this._req(on ? "POST" : "DELETE", "/api/artists/" + id + "/follow"); },
  liked()                    { return this.get("/api/liked"); },
  like(id, on)               { return this._req(on ? "PUT" : "DELETE", "/api/songs/" + id + "/like"); },
  playlists()                { return this.get("/api/playlists"); },
  createPlaylist(data)       { return this.post("/api/playlists", data); },
  playlist(id)               { return this.get("/api/playlists/" + id); },
  updatePlaylist(id, data)   { return this.put("/api/playlists/" + id, data); },
  deletePlaylist(id)         { return this.del("/api/playlists/" + id); },
  addToPlaylist(id, songId)  { return this.post("/api/playlists/" + id + "/songs", { song_id: songId }); },
  removeFromPlaylist(id, s)  { return this.del("/api/playlists/" + id + "/songs/" + s); },
  library()                  { return this.get("/api/library"); },
  recordPlay(songId)         { return this.post("/api/history", { song_id: songId }); },
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
  document.getElementById("toast-msg").textContent = msg;
  box.classList.remove("hidden");
  // force reflow so the pop animation replays
  void box.offsetWidth;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => box.classList.add("hidden"), 2200);
}
