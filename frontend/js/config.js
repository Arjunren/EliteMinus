/* ---------------------------------------------------------------------------
 * config.js — the ONLY file you edit when you deploy.
 *
 * Point API_BASE at your PythonAnywhere backend. No trailing slash.
 *   production:  "https://YOURUSERNAME.pythonanywhere.com"
 *   local dev:   "http://localhost:5000"
 *
 * When this site is served by the Flask dev server itself (at /app/), the
 * backend is the same origin, so leave API_BASE empty and it just works.
 * ------------------------------------------------------------------------- */
window.CONFIG = {
  API_BASE: location.port === "5000" ? "" : "https://YOURUSERNAME.pythonanywhere.com",

  // Where the token lives in the browser.
  TOKEN_KEY: "em_token",
  USER_KEY: "em_user",

  BRAND: "EliteMinus-",
};
