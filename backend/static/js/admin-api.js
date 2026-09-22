/* ---------------------------------------------------------------------------
 * admin-api.js — fetch wrapper + formatting helpers for the admin panel.
 * The panel is served by Flask on the same origin, so the session cookie
 * authenticates every request; no token handling is needed here.
 * ------------------------------------------------------------------------- */
const API = {
  async _req(method, url, body) {
    const opts = { method, headers: {}, credentials: "same-origin" };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    if (res.status === 401) {            // session expired -> back to login
      window.location.href = "/login?next=/admin";
      throw new Error("Not authenticated");
    }
    const data = res.status === 204 ? null
                 : await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.error) || res.statusText);
    return data;
  },
  get(u)     { return this._req("GET", u); },
  post(u, b) { return this._req("POST", u, b || {}); },
  put(u, b)  { return this._req("PUT", u, b || {}); },
  del(u)     { return this._req("DELETE", u); },
  async upload(u, formData) {
    const res = await fetch(u, {
      method: "POST", body: formData, credentials: "same-origin",
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error((data && data.error) || res.statusText);
    return data;
  },
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
  void box.offsetWidth;               // replay the pop animation
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => box.classList.add("hidden"), 2800);
}
