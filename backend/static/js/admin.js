/* ---------------------------------------------------------------------------
 * admin.js — controller for the staff admin panel.
 * Uses the fetch wrapper and helpers from admin-api.js.
 * ------------------------------------------------------------------------- */
const Admin = {
  stats:        ()      => API.get("/api/admin/stats"),

  // --- staff ---
  staff:        (qs)    => API.get("/api/admin/staff" + (qs ? "?" + qs : "")),
  createStaff:  (d)     => API.post("/api/admin/staff", d),
  updateStaff:  (id, d) => API.put("/api/admin/staff/" + id, d),
  deleteStaff:  (id)    => API.del("/api/admin/staff/" + id),
  setStatus:    (id, d) => API.post("/api/admin/staff/" + id + "/status", d),
  resetPw:      (id, d) => API.post("/api/admin/staff/" + id + "/password", d),
  audit:        ()      => API.get("/api/admin/audit?limit=200"),

  // --- catalog ---
  songs:        (q)     => API.get("/api/admin/songs" + (q ? "?q=" + encodeURIComponent(q) : "")),
  createSong:   (d)     => API.post("/api/admin/songs", d),
  updateSong:   (id, d) => API.put("/api/admin/songs/" + id, d),
  deleteSong:   (id)    => API.del("/api/admin/songs/" + id),
  artists:      ()      => API.get("/api/admin/artists"),
  createArtist: (d)     => API.post("/api/admin/artists", d),
  deleteArtist: (id)    => API.del("/api/admin/artists/" + id),
  albums:       ()      => API.get("/api/admin/albums"),
  createAlbum:  (d)     => API.post("/api/admin/albums", d),
  deleteAlbum:  (id)    => API.del("/api/admin/albums/" + id),

  // --- spotify ---
  spotifySearch: (q)    => API.get("/api/admin/spotify/search?q=" + encodeURIComponent(q)),
  spotifyImport: (d)    => API.post("/api/admin/spotify/import", d),
};

const INPUT = "w-full rounded bg-base-600 border border-neutral-700 px-3 py-2.5 focus:border-white focus:ring-2 focus:ring-white/20 outline-none text-sm";
const state = { songs: {}, staff: {}, artists: [], albums: [], filters: {} };
let searchTimer = null;

const TITLES = {
  dashboard: "Dashboard", staff: "Staff directory", audit: "Activity log",
  songs: "Songs", artists: "Artists", albums: "Albums",
  spotify: "Spotify import",
};

const ROLE_STYLE = {
  admin: "bg-brand/20 text-brand",
  manager: "bg-sky-500/20 text-sky-300",
  staff: "bg-base-600 text-neutral-300",
};
const STATUS_STYLE = {
  active: "bg-emerald-500/20 text-emerald-300",
  pending: "bg-amber-500/20 text-amber-300",
  suspended: "bg-red-500/20 text-red-300",
};

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("admin-name").textContent = CURRENT_USER.name;
  document.getElementById("admin-initial").textContent =
    CURRENT_USER.name.charAt(0).toUpperCase();
  window.addEventListener("hashchange", routeAdmin);
  document.getElementById("admin-view").addEventListener("click", onAdminAction);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  if (!location.hash) location.hash = "#/dashboard";
  else routeAdmin();
});

function routeAdmin() {
  const section = (location.hash.replace("#/", "") || "dashboard").split("/")[0];
  document.querySelectorAll(".anav").forEach((a) => {
    const on = a.dataset.nav === section;
    a.classList.toggle("bg-base-600", on);
    a.classList.toggle("text-white", on);
  });
  document.getElementById("page-title").textContent = TITLES[section] || "Admin";
  ({
    dashboard: showDashboard, staff: showStaff, audit: showAudit,
    songs: showSongs, artists: showArtists, albums: showAlbums,
    spotify: showSpotify,
  }[section] || showDashboard)();
}

const view = () => document.getElementById("admin-view");
function loading() {
  view().innerHTML = `<div class="grid place-items-center h-64"><div class="animate-spin w-9 h-9 border-4 border-neutral-600 border-t-brand rounded-full"></div></div>`;
}
function errBox(m) { view().innerHTML = `<p class="text-red-400">${escapeHtml(m)}</p>`; }

const pill = (text, cls) =>
  `<span class="text-xs rounded px-2 py-0.5 whitespace-nowrap ${cls}">${escapeHtml(text)}</span>`;

/* ============================ DASHBOARD ============================ */
async function showDashboard() {
  loading();
  let s;
  try { s = await Admin.stats(); } catch (e) { return errBox(e.message); }

  const staffCards = [
    ["Total staff", s.staff.total, "#facc15"],
    ["Active", s.staff.active, "#10b981"],
    ["Pending approval", s.staff.pending, "#f59e0b"],
    ["Suspended", s.staff.suspended, "#ef4444"],
    ["Administrators", s.staff.admins, "#a855f7"],
    ["New this week", s.staff.new_this_week, "#3b82f6"],
    ["Signed in today", s.staff.active_today, "#14b8a6"],
    ["Never signed in", s.staff.never_signed_in, "#6b7280"],
  ];
  const catalogCards = [
    ["Songs", fmtCount(s.catalog.songs)], ["Artists", fmtCount(s.catalog.artists)],
    ["Albums", fmtCount(s.catalog.albums)], ["Playlists", fmtCount(s.catalog.playlists)],
    ["From Spotify", fmtCount(s.catalog.from_spotify)],
    ["Total plays", fmtCount(s.catalog.plays)],
  ];
  const maxPlays = Math.max(1, ...s.top_songs.map((x) => x.plays));

  const warnings = [];
  if (!s.mail_configured)
    warnings.push("SMTP isn't configured — verification codes are being written to the server log instead of e-mailed.");
  if (!s.spotify_configured)
    warnings.push("Spotify credentials aren't set — the import screen won't work.");
  if (s.staff.pending)
    warnings.push(`${s.staff.pending} account(s) are waiting for approval in the staff directory.`);

  view().innerHTML = `
    ${warnings.length ? `
      <div class="mb-6 space-y-2">
        ${warnings.map((w) => `
          <div class="flex items-start gap-3 rounded-lg bg-amber-500/10 border border-amber-500/30 px-4 py-3 text-sm text-amber-200">
            <svg class="w-5 h-5 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L1 21h22L12 2zm0 5l7.5 13h-15L12 7zm-1 4v4h2v-4h-2zm0 6v2h2v-2h-2z"/></svg>
            <span>${escapeHtml(w)}</span>
          </div>`).join("")}
      </div>` : ""}

    <h2 class="text-sm font-bold text-neutral-400 uppercase tracking-wider mb-3">Staff overview</h2>
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      ${staffCards.map(([label, val, c]) => `
        <div class="bg-base-700 rounded-lg p-4">
          <div class="w-2 h-2 rounded-full mb-2" style="background:${c}"></div>
          <p class="text-2xl font-bold">${val}</p>
          <p class="text-sm text-neutral-400">${label}</p>
        </div>`).join("")}
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-3 mb-6">
      <div class="bg-base-700 rounded-lg p-4">
        <h3 class="font-bold mb-3">Staff by department</h3>
        ${s.by_department.length ? s.by_department.map((d) => `
          <div class="flex justify-between text-sm py-1.5 border-b border-white/5 last:border-0">
            <span>${escapeHtml(d.department)}</span>
            <span class="text-neutral-400 tabular-nums">${d.count}</span>
          </div>`).join("") : '<p class="text-sm text-neutral-500">No departments set yet.</p>'}
        <h3 class="font-bold mt-4 mb-2">By role</h3>
        <div class="flex flex-wrap gap-2">
          ${s.by_role.map((r) => pill(`${r.role} · ${r.count}`, ROLE_STYLE[r.role] || ROLE_STYLE.staff)).join("")}
        </div>
      </div>

      <div class="bg-base-700 rounded-lg p-4">
        <h3 class="font-bold mb-3">Newest accounts</h3>
        ${s.recent_staff.map((u) => `
          <div class="flex items-center justify-between text-sm py-1.5 border-b border-white/5 last:border-0">
            <span class="flex items-center gap-2 truncate">
              ${escapeHtml(u.username)}
              ${pill(u.role, ROLE_STYLE[u.role] || ROLE_STYLE.staff)}
              ${pill(u.status, STATUS_STYLE[u.status] || "")}
            </span>
            <span class="text-neutral-500 shrink-0 pl-2">${escapeHtml(u.created_at)}</span>
          </div>`).join("")}
      </div>
    </div>

    <h2 class="text-sm font-bold text-neutral-400 uppercase tracking-wider mb-3">Catalog &amp; listening</h2>
    <div class="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
      ${catalogCards.map(([label, val]) => `
        <div class="bg-base-700 rounded-lg p-4">
          <p class="text-xl font-bold">${val}</p>
          <p class="text-xs text-neutral-400">${label}</p>
        </div>`).join("")}
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
      <div class="bg-base-700 rounded-lg p-4">
        <h3 class="font-bold mb-3">Top songs by plays</h3>
        <div class="space-y-2">
          ${s.top_songs.map((song) => `
            <div>
              <div class="flex justify-between text-sm mb-1">
                <span class="truncate pr-2">${escapeHtml(song.title)} <span class="text-neutral-500">· ${escapeHtml(song.artist)}</span></span>
                <span class="text-neutral-400 tabular-nums">${fmtCount(song.plays)}</span>
              </div>
              <div class="h-2 rounded-full bg-base-600 overflow-hidden">
                <div class="h-full bg-brand rounded-full" style="width:${(song.plays / maxPlays * 100).toFixed(1)}%"></div>
              </div>
            </div>`).join("")}
        </div>
        <div class="flex gap-6 mt-4 pt-3 border-t border-white/5 text-sm">
          <span class="text-neutral-400">Plays today <b class="text-brand">${s.plays_today}</b></span>
          <span class="text-neutral-400">This week <b class="text-brand">${s.plays_week}</b></span>
        </div>
      </div>

      <div class="bg-base-700 rounded-lg p-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="font-bold">Recent admin activity</h3>
          <a href="#/audit" class="text-xs text-neutral-400 hover:text-brand">View all</a>
        </div>
        ${s.recent_audit.length ? s.recent_audit.map((a) => `
          <div class="text-sm py-1.5 border-b border-white/5 last:border-0">
            <div class="flex justify-between gap-2">
              <span class="truncate"><b class="text-white">${escapeHtml(a.actor)}</b>
                <span class="text-neutral-400">${escapeHtml(a.action)}</span>
                ${a.target ? `<span class="text-neutral-300">${escapeHtml(a.target)}</span>` : ""}</span>
              <span class="text-neutral-500 shrink-0">${escapeHtml(a.at)}</span>
            </div>
          </div>`).join("") : '<p class="text-sm text-neutral-500">Nothing logged yet.</p>'}
      </div>
    </div>`;
}

/* ============================ STAFF ============================ */
const ROLES = () => (window.ADMIN_META && ADMIN_META.roles) || ["admin", "manager", "staff"];
const STATUSES = () => (window.ADMIN_META && ADMIN_META.statuses) || ["pending", "active", "suspended"];

function showStaff() {
  const f = state.filters;
  view().innerHTML = `
    <div class="flex flex-wrap items-center gap-2 mb-4">
      <input id="staff-search" value="${escapeHtml(f.q || "")}" placeholder="Search name, e-mail, code, department…"
             class="${INPUT} max-w-xs">
      <select id="staff-role" class="${INPUT} w-auto">
        <option value="">All roles</option>
        ${ROLES().map((r) => `<option value="${r}" ${f.role === r ? "selected" : ""}>${r}</option>`).join("")}
      </select>
      <select id="staff-status" class="${INPUT} w-auto">
        <option value="">All statuses</option>
        ${STATUSES().map((s) => `<option value="${s}" ${f.status === s ? "selected" : ""}>${s}</option>`).join("")}
      </select>
      <span class="flex-1"></span>
      <a href="/api/admin/staff/export" class="px-4 py-2 rounded-full bg-base-600 hover:bg-base-500 text-sm font-bold">Export CSV</a>
      <button data-action="add-staff" class="px-4 py-2 rounded-full bg-brand text-black text-sm font-bold hover:bg-brand-light">+ Add staff</button>
    </div>
    <p id="staff-count" class="text-sm text-neutral-500 mb-3"></p>
    ${tableShell(["Staff", "Contact", "Role", "Status", "Department", "Last sign-in", ""], "staff-rows")}`;

  const search = document.getElementById("staff-search");
  search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => { state.filters.q = search.value; loadStaff(); }, 250);
  });
  document.getElementById("staff-role").addEventListener("change", (e) => {
    state.filters.role = e.target.value; loadStaff();
  });
  document.getElementById("staff-status").addEventListener("change", (e) => {
    state.filters.status = e.target.value; loadStaff();
  });
  loadStaff();
}

function filterQuery() {
  const p = new URLSearchParams();
  Object.entries(state.filters).forEach(([k, v]) => { if (v) p.set(k, v); });
  return p.toString();
}

async function loadStaff() {
  const body = document.getElementById("staff-rows");
  if (!body) return;
  try {
    const data = await Admin.staff(filterQuery());
    state.staff = {};
    document.getElementById("staff-count").textContent =
      `${data.count} account${data.count === 1 ? "" : "s"}`;

    body.innerHTML = data.staff.length ? data.staff.map((u) => {
      state.staff[u.id] = u;
      const self = u.id === CURRENT_USER.id;
      return `<tr class="border-b border-white/5 hover:bg-white/5">
        <td class="py-2.5 px-4">
          <div class="font-medium flex items-center gap-2">${escapeHtml(u.full_name || u.display_name)}
            ${self ? pill("you", "bg-white/10 text-neutral-300") : ""}</div>
          <div class="text-xs text-neutral-500">${escapeHtml(u.staff_code || "—")} · @${escapeHtml(u.username)}</div>
        </td>
        <td class="py-2.5 px-4 text-neutral-400">
          <div class="truncate max-w-[220px]">${escapeHtml(u.email)}</div>
          <div class="text-xs">${escapeHtml(u.phone || "—")}
            ${u.is_verified ? "" : pill("unverified", "bg-amber-500/20 text-amber-300")}</div>
        </td>
        <td class="py-2.5 px-4">${pill(u.role, ROLE_STYLE[u.role] || ROLE_STYLE.staff)}</td>
        <td class="py-2.5 px-4">${pill(u.status, STATUS_STYLE[u.status] || "")}</td>
        <td class="py-2.5 px-4 text-neutral-400">
          <div>${escapeHtml(u.department || "—")}</div>
          <div class="text-xs text-neutral-500">${escapeHtml(u.position || "")}</div>
        </td>
        <td class="py-2.5 px-4 text-neutral-500 text-xs">
          <div>${escapeHtml(u.last_login_at || "never")}</div>
          <div>${u.login_count} sign-in${u.login_count === 1 ? "" : "s"}</div>
        </td>
        <td class="py-2.5 px-4 text-right whitespace-nowrap">
          ${u.status !== "active" && !self
            ? `<button data-action="approve" data-id="${u.id}" class="text-xs px-2 py-1 rounded hover:bg-white/10 text-emerald-400">Approve</button>` : ""}
          ${u.status === "active" && !self
            ? `<button data-action="suspend" data-id="${u.id}" class="text-xs px-2 py-1 rounded hover:bg-white/10 text-amber-400">Suspend</button>` : ""}
          ${iconBtn("edit-staff", u.id, "Edit", EDIT_SVG)}
          ${iconBtn("reset-pw", u.id, "Reset password", KEY_SVG)}
          ${self ? "" : iconBtn("del-staff", u.id, "Delete", DEL_SVG, "text-red-400")}
        </td></tr>`;
    }).join("") : `<tr><td colspan="7" class="py-8 px-4 text-center text-neutral-500">No staff match those filters.</td></tr>`;
  } catch (e) {
    body.innerHTML = `<tr><td colspan="7" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`;
  }
}

function staffForm(user) {
  const editing = !!user;
  const u = user || {};
  const opts = (values, selected) => values.map((v) =>
    `<option value="${v}" ${v === selected ? "selected" : ""}>${v}</option>`).join("");

  openModal(`
    <form id="staff-form" class="space-y-3">
      <h2 class="text-xl font-bold mb-1">${editing ? "Edit staff member" : "Add staff member"}</h2>
      ${editing ? `<p class="text-xs text-neutral-500 mb-2">${escapeHtml(u.staff_code || "")}</p>` : ""}

      <div class="grid grid-cols-2 gap-3">
        <div><label class="block text-sm font-semibold mb-1">Username</label>
          <input name="username" required minlength="3" value="${escapeHtml(u.username || "")}" class="${INPUT}"></div>
        <div><label class="block text-sm font-semibold mb-1">Full name</label>
          <input name="full_name" value="${escapeHtml(u.full_name || "")}" class="${INPUT}"></div>
      </div>

      <div><label class="block text-sm font-semibold mb-1">E-mail</label>
        <input name="email" type="email" required value="${escapeHtml(u.email || "")}" class="${INPUT}"></div>

      ${editing ? "" : `
      <div><label class="block text-sm font-semibold mb-1">Password
          <span class="text-neutral-500 font-normal">(blank = generate one)</span></label>
        <input name="password" type="text" placeholder="min 8 characters" class="${INPUT}"></div>`}

      <div class="grid grid-cols-2 gap-3">
        <div><label class="block text-sm font-semibold mb-1">Role</label>
          <select name="role" class="${INPUT}">${opts(ROLES(), u.role || "staff")}</select></div>
        <div><label class="block text-sm font-semibold mb-1">Status</label>
          <select name="status" class="${INPUT}">${opts(STATUSES(), u.status || "active")}</select></div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div><label class="block text-sm font-semibold mb-1">Department</label>
          <input name="department" value="${escapeHtml(u.department || "")}" placeholder="e.g. Operations" class="${INPUT}"></div>
        <div><label class="block text-sm font-semibold mb-1">Position</label>
          <input name="position" value="${escapeHtml(u.position || "")}" placeholder="e.g. Support Agent" class="${INPUT}"></div>
      </div>

      <div class="grid grid-cols-2 gap-3">
        <div><label class="block text-sm font-semibold mb-1">Phone</label>
          <input name="phone" value="${escapeHtml(u.phone || "")}" class="${INPUT}"></div>
        <div><label class="block text-sm font-semibold mb-1">Hire date</label>
          <input name="hire_date" type="date" value="${escapeHtml(u.hire_date || "")}" class="${INPUT}"></div>
      </div>

      <div><label class="block text-sm font-semibold mb-1">Notes</label>
        <textarea name="notes" rows="2" class="${INPUT}">${escapeHtml(u.notes || "")}</textarea></div>

      ${editing ? "" : `
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" name="send_credentials" checked class="accent-brand w-4 h-4">
        E-mail the sign-in details to this address
      </label>`}

      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">${editing ? "Save" : "Create"}</button>
      </div>
    </form>`);

  document.getElementById("staff-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const payload = Object.fromEntries(fd.entries());
    payload.send_credentials = fd.get("send_credentials") != null;
    try {
      if (editing) {
        await Admin.updateStaff(u.id, payload);
        closeModal();
        toast("Staff member updated");
      } else {
        const created = await Admin.createStaff(payload);
        closeModal();
        if (created.generated_password) {
          showGeneratedPassword(created.username, created.generated_password,
                                created.credentials_emailed);
        } else {
          toast(created.credentials_emailed
            ? "Staff member created — details e-mailed"
            : "Staff member created");
        }
      }
      loadStaff();
    } catch (err) { toast(err.message); }
  });
}

function showGeneratedPassword(username, password, emailed) {
  openModal(`
    <h2 class="text-xl font-bold mb-2">Account created</h2>
    <p class="text-sm text-neutral-300 mb-4">
      A password was generated for <b class="text-white">${escapeHtml(username)}</b>.
      ${emailed ? "It has been e-mailed to them." : "E-mail delivery is off, so copy it now — it won't be shown again."}
    </p>
    <div class="bg-base-600 rounded-lg px-4 py-3 font-mono text-lg text-brand break-all mb-4">${escapeHtml(password)}</div>
    <div class="flex justify-end"><button data-close class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">Done</button></div>`);
}

function resetPwForm(user) {
  openModal(`
    <form id="pw-form" class="space-y-3">
      <h2 class="text-xl font-bold mb-1">Reset password</h2>
      <p class="text-sm text-neutral-400">for <b class="text-white">${escapeHtml(user.username)}</b> (${escapeHtml(user.email)})</p>
      <input name="password" type="text" placeholder="New password — leave blank to generate one" class="${INPUT}">
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" name="notify" checked class="accent-brand w-4 h-4"> E-mail the new password to them
      </label>
      <p class="text-xs text-neutral-500">Any sessions they have open will be signed out.</p>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">Reset</button>
      </div>
    </form>`);

  document.getElementById("pw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      const res = await Admin.resetPw(user.id, {
        password: fd.get("password") || "", notify: fd.get("notify") != null,
      });
      closeModal();
      if (res.password) showGeneratedPassword(user.username, res.password, res.emailed);
      else toast(res.emailed ? "Password reset — e-mail sent" : "Password reset");
    } catch (err) { toast(err.message); }
  });
}

/* ============================ AUDIT LOG ============================ */
async function showAudit() {
  loading();
  let rows;
  try { rows = await Admin.audit(); } catch (e) { return errBox(e.message); }
  view().innerHTML = `
    <p class="text-sm text-neutral-500 mb-3">${rows.length} most recent admin actions.</p>
    ${tableShell(["When", "Who", "Action", "Target", "Detail"], "audit-rows")}`;
  document.getElementById("audit-rows").innerHTML = rows.length ? rows.map((a) => `
    <tr class="border-b border-white/5 hover:bg-white/5">
      <td class="py-2.5 px-4 text-neutral-500 whitespace-nowrap">${escapeHtml(a.at)}</td>
      <td class="py-2.5 px-4 font-medium">${escapeHtml(a.actor)}</td>
      <td class="py-2.5 px-4"><code class="text-xs text-brand">${escapeHtml(a.action)}</code></td>
      <td class="py-2.5 px-4 text-neutral-300">${escapeHtml(a.target)}</td>
      <td class="py-2.5 px-4 text-neutral-500 text-xs">${escapeHtml(a.detail)}</td>
    </tr>`).join("") : `<tr><td colspan="5" class="py-8 text-center text-neutral-500">Nothing logged yet.</td></tr>`;
}

/* ============================ SHARED TABLE BITS ============================ */
function toolbar(searchId, addAction, addLabel) {
  return `
    <div class="flex items-center justify-between gap-3 mb-4">
      ${searchId ? `<input id="${searchId}" placeholder="Search…" class="${INPUT} max-w-xs">` : "<div></div>"}
      <button data-action="${addAction}" class="px-4 py-2 rounded-full bg-brand text-black text-sm font-bold hover:bg-brand-light shrink-0">${addLabel}</button>
    </div>`;
}
function tableShell(headers, bodyId) {
  return `
    <div class="bg-base-700 rounded-lg overflow-x-auto">
      <table class="w-full text-sm min-w-[720px]">
        <thead class="text-left text-neutral-400 border-b border-white/10">
          <tr>${headers.map((h) => `<th class="py-3 px-4 font-medium">${h}</th>`).join("")}</tr>
        </thead>
        <tbody id="${bodyId}"></tbody>
      </table>
    </div>`;
}
const iconBtn = (action, id, title, svg, cls = "") =>
  `<button data-action="${action}" data-id="${id}" title="${title}" class="p-1.5 rounded hover:bg-white/10 ${cls}">${svg}</button>`;
const EDIT_SVG = '<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.58z"/></svg>';
const DEL_SVG = '<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M6 7h12l-1 14H7L6 7zm3-3h6l1 2H8l1-2z"/></svg>';
const KEY_SVG = '<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1a5 5 0 00-5 5v3H5v12h14V9h-2V6a5 5 0 00-5-5zm3 8H9V6a3 3 0 116 0v3z"/></svg>';

/* ============================ SONGS ============================ */
function showSongs() {
  view().innerHTML = toolbar("song-search", "add-song", "+ Add song") +
    tableShell(["Title", "Artist", "Album", "Duration", "Plays", "Source", ""], "song-rows");
  const input = document.getElementById("song-search");
  input.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadSongs(input.value), 250);
  });
  loadSongs("");
}
async function loadSongs(q) {
  const body = document.getElementById("song-rows");
  if (!body) return;
  try {
    const songs = await Admin.songs(q);
    state.songs = {};
    body.innerHTML = songs.length ? songs.map((s) => {
      state.songs[s.id] = s;
      return `<tr class="border-b border-white/5 hover:bg-white/5">
        <td class="py-2.5 px-4 font-medium">${escapeHtml(s.title)}</td>
        <td class="py-2.5 px-4 text-neutral-300">${escapeHtml(s.artist ? s.artist.name : "—")}</td>
        <td class="py-2.5 px-4 text-neutral-400">${escapeHtml(s.album ? s.album.title : "—")}</td>
        <td class="py-2.5 px-4 text-neutral-400 tabular-nums">${fmtTime(s.duration)}</td>
        <td class="py-2.5 px-4 text-neutral-400 tabular-nums">${fmtCount(s.play_count)}</td>
        <td class="py-2.5 px-4">${s.spotify_id ? pill("Spotify", "bg-emerald-500/20 text-emerald-300") : pill("local", "bg-base-600 text-neutral-400")}</td>
        <td class="py-2.5 px-4 text-right whitespace-nowrap">
          ${iconBtn("edit-song", s.id, "Edit", EDIT_SVG)}
          ${iconBtn("del-song", s.id, "Delete", DEL_SVG, "text-red-400")}
        </td></tr>`;
    }).join("") : `<tr><td colspan="7" class="py-8 px-4 text-center text-neutral-500">No songs found.</td></tr>`;
  } catch (e) {
    body.innerHTML = `<tr><td colspan="7" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`;
  }
}

async function songForm(song) {
  if (!state.artists.length) state.artists = await Admin.artists();
  if (!state.albums.length) state.albums = await Admin.albums();
  const artistId = song && song.artist ? song.artist.id : (state.artists[0] && state.artists[0].id);
  const albumId = song && song.album ? song.album.id : "";
  const artistOpts = state.artists.map((a) =>
    `<option value="${a.id}" ${a.id == artistId ? "selected" : ""}>${escapeHtml(a.name)}</option>`).join("");

  openModal(`
    <form id="song-form" class="space-y-3">
      <h2 class="text-xl font-bold mb-1">${song ? "Edit song" : "Add song"}</h2>
      <div><label class="block text-sm font-semibold mb-1">Title</label>
        <input name="title" required value="${song ? escapeHtml(song.title) : ""}" class="${INPUT}"></div>
      <div><label class="block text-sm font-semibold mb-1">Artist</label>
        <select name="artist_id" id="sf-artist" class="${INPUT}">${artistOpts}</select></div>
      <div><label class="block text-sm font-semibold mb-1">Album</label>
        <select name="album_id" id="sf-album" class="${INPUT}">${albumOptions(artistId, albumId)}</select></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label class="block text-sm font-semibold mb-1">Duration (sec)</label>
          <input name="duration" type="number" min="1" value="${song ? song.duration : 200}" class="${INPUT}"></div>
        <div><label class="block text-sm font-semibold mb-1">Track #</label>
          <input name="track_number" type="number" min="1" value="1" class="${INPUT}"></div>
      </div>
      <div><label class="block text-sm font-semibold mb-1">Audio URL <span class="text-neutral-500 font-normal">(blank = demo track)</span></label>
        <input name="audio_url" value="${song ? escapeHtml(song.audio_url || "") : ""}" placeholder="https://…/song.mp3" class="${INPUT}"></div>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">${song ? "Save" : "Add"}</button>
      </div>
    </form>`);

  document.getElementById("sf-artist").addEventListener("change", (e) => {
    document.getElementById("sf-album").innerHTML = albumOptions(e.target.value, "");
  });
  document.getElementById("song-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target).entries());
    try {
      if (song) await Admin.updateSong(song.id, d);
      else await Admin.createSong(d);
      closeModal();
      toast(song ? "Song updated" : "Song added");
      const input = document.getElementById("song-search");
      loadSongs(input ? input.value : "");
    } catch (err) { toast(err.message); }
  });
}
function albumOptions(artistId, selectedId) {
  const opts = ['<option value="">— No album (single) —</option>'];
  state.albums.filter((a) => !artistId || (a.artist && a.artist.id == artistId))
    .forEach((a) => opts.push(`<option value="${a.id}" ${a.id == selectedId ? "selected" : ""}>${escapeHtml(a.title)}</option>`));
  return opts.join("");
}

/* ============================ ARTISTS ============================ */
function showArtists() {
  view().innerHTML = toolbar(null, "add-artist", "+ Add artist") +
    tableShell(["Name", "Genre", "Albums", "Songs", "Monthly listeners", "Source", ""], "artist-rows");
  loadArtists();
}
async function loadArtists() {
  const body = document.getElementById("artist-rows");
  if (!body) return;
  try {
    const artists = await Admin.artists();
    state.artists = artists; state.albums = [];   // refresh caches
    body.innerHTML = artists.length ? artists.map((a) => `
      <tr class="border-b border-white/5 hover:bg-white/5">
        <td class="py-2.5 px-4 font-medium">${escapeHtml(a.name)}</td>
        <td class="py-2.5 px-4 text-neutral-300">${escapeHtml(a.genre || "—")}</td>
        <td class="py-2.5 px-4 text-neutral-400">${a.albums}</td>
        <td class="py-2.5 px-4 text-neutral-400">${a.songs}</td>
        <td class="py-2.5 px-4 text-neutral-400 tabular-nums">${fmtCount(a.monthly_listeners)}</td>
        <td class="py-2.5 px-4">${a.spotify_id ? pill("Spotify", "bg-emerald-500/20 text-emerald-300") : pill("local", "bg-base-600 text-neutral-400")}</td>
        <td class="py-2.5 px-4 text-right">${iconBtn("del-artist", a.id, "Delete", DEL_SVG, "text-red-400")}</td>
      </tr>`).join("") : `<tr><td colspan="7" class="py-8 text-center text-neutral-500">No artists.</td></tr>`;
  } catch (e) {
    body.innerHTML = `<tr><td colspan="7" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`;
  }
}
function artistForm() {
  openModal(`
    <form id="artist-form" class="space-y-3">
      <h2 class="text-xl font-bold mb-1">Add artist</h2>
      <div><label class="block text-sm font-semibold mb-1">Name</label><input name="name" required class="${INPUT}"></div>
      <div><label class="block text-sm font-semibold mb-1">Genre</label><input name="genre" placeholder="e.g. Pop" class="${INPUT}"></div>
      <div><label class="block text-sm font-semibold mb-1">Monthly listeners</label><input name="monthly_listeners" type="number" min="0" value="0" class="${INPUT}"></div>
      <div><label class="block text-sm font-semibold mb-1">Bio</label><textarea name="bio" rows="2" class="${INPUT}"></textarea></div>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">Add</button>
      </div>
    </form>`);
  document.getElementById("artist-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await Admin.createArtist(Object.fromEntries(new FormData(e.target).entries()));
      closeModal(); toast("Artist added"); loadArtists();
    } catch (err) { toast(err.message); }
  });
}

/* ============================ ALBUMS ============================ */
function showAlbums() {
  view().innerHTML = toolbar(null, "add-album", "+ Add album") +
    tableShell(["Title", "Artist", "Year", "Songs", "Source", ""], "album-rows");
  loadAlbums();
}
async function loadAlbums() {
  const body = document.getElementById("album-rows");
  if (!body) return;
  try {
    const albums = await Admin.albums();
    state.albums = albums;
    body.innerHTML = albums.length ? albums.map((a) => `
      <tr class="border-b border-white/5 hover:bg-white/5">
        <td class="py-2.5 px-4 font-medium">${escapeHtml(a.title)}</td>
        <td class="py-2.5 px-4 text-neutral-300">${escapeHtml(a.artist ? a.artist.name : "—")}</td>
        <td class="py-2.5 px-4 text-neutral-400">${a.year || "—"}</td>
        <td class="py-2.5 px-4 text-neutral-400">${a.songs}</td>
        <td class="py-2.5 px-4">${a.spotify_id ? pill("Spotify", "bg-emerald-500/20 text-emerald-300") : pill("local", "bg-base-600 text-neutral-400")}</td>
        <td class="py-2.5 px-4 text-right">${iconBtn("del-album", a.id, "Delete", DEL_SVG, "text-red-400")}</td>
      </tr>`).join("") : `<tr><td colspan="6" class="py-8 text-center text-neutral-500">No albums.</td></tr>`;
  } catch (e) {
    body.innerHTML = `<tr><td colspan="6" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`;
  }
}
async function albumForm() {
  if (!state.artists.length) state.artists = await Admin.artists();
  const opts = state.artists.map((a) => `<option value="${a.id}">${escapeHtml(a.name)}</option>`).join("");
  openModal(`
    <form id="album-form" class="space-y-3">
      <h2 class="text-xl font-bold mb-1">Add album</h2>
      <div><label class="block text-sm font-semibold mb-1">Title</label><input name="title" required class="${INPUT}"></div>
      <div><label class="block text-sm font-semibold mb-1">Artist</label><select name="artist_id" class="${INPUT}">${opts}</select></div>
      <div><label class="block text-sm font-semibold mb-1">Year</label><input name="year" type="number" min="1900" max="2100" placeholder="2024" class="${INPUT}"></div>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">Add</button>
      </div>
    </form>`);
  document.getElementById("album-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await Admin.createAlbum(Object.fromEntries(new FormData(e.target).entries()));
      closeModal(); toast("Album added"); state.albums = []; loadAlbums();
    } catch (err) { toast(err.message); }
  });
}

/* ============================ SPOTIFY IMPORT ============================ */
function showSpotify() {
  view().innerHTML = `
    <div class="max-w-3xl">
      <p class="text-sm text-neutral-400 mb-4">
        Search the Spotify catalog and pull tracks, albums or artists into
        EliteMinus. Imported items keep their real cover art and their Spotify
        URI, which is what Premium listeners stream through the Web Playback SDK.
      </p>
      <input id="sp-search" placeholder="Search Spotify for a song, album or artist…" class="${INPUT} mb-4">
      <div id="sp-results"></div>
    </div>`;
  const input = document.getElementById("sp-search");
  input.focus();
  input.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runSpotifySearch(input.value.trim()), 350);
  });
}

async function runSpotifySearch(q) {
  const box = document.getElementById("sp-results");
  if (!box) return;
  if (!q) { box.innerHTML = ""; return; }
  box.innerHTML = `<div class="grid place-items-center h-32"><div class="animate-spin w-8 h-8 border-4 border-neutral-600 border-t-brand rounded-full"></div></div>`;

  let data;
  try { data = await Admin.spotifySearch(q); }
  catch (e) { box.innerHTML = `<p class="text-red-400 text-sm">${escapeHtml(e.message)}</p>`; return; }

  const row = (img, title, sub, kind, id, imported, badge) => `
    <div class="flex items-center gap-3 py-2 border-b border-white/5">
      ${img ? `<img src="${escapeHtml(img)}" class="w-11 h-11 rounded object-cover shrink-0" alt="">`
            : `<div class="w-11 h-11 rounded bg-base-600 shrink-0"></div>`}
      <div class="min-w-0 flex-1">
        <p class="font-medium truncate">${escapeHtml(title)}</p>
        <p class="text-xs text-neutral-500 truncate">${escapeHtml(sub)}</p>
      </div>
      ${badge || ""}
      <button data-action="sp-import" data-kind="${kind}" data-sid="${escapeHtml(id)}"
        class="shrink-0 px-3 py-1.5 rounded-full text-xs font-bold ${imported ? "bg-base-600 text-neutral-400" : "bg-brand text-black hover:bg-brand-light"}">
        ${imported ? "Re-import" : "Import"}
      </button>
    </div>`;

  const section = (heading, rows) => rows.length ? `
    <div class="bg-base-700 rounded-lg p-4 mb-4">
      <h3 class="font-bold mb-2">${heading}</h3>${rows.join("")}
    </div>` : "";

  box.innerHTML =
    section("Tracks", data.tracks.map((t) => row(
      t.image, t.title, `${t.artist} · ${t.album || ""} · ${fmtTime(t.duration)}`,
      "track", t.spotify_id, t.imported,
      t.preview_url ? "" : `<span class="text-[10px] text-neutral-600 shrink-0 mr-2">no preview</span>`))) +
    section("Albums", data.albums.map((a) => row(
      a.image, a.title, `${a.artist} · ${a.year} · ${a.total_tracks} tracks`,
      "album", a.spotify_id, a.imported))) +
    section("Artists", data.artists.map((a) => row(
      a.image, a.name, `${(a.genres[0] || "Artist")} · ${fmtCount(a.followers)} followers`,
      "artist", a.spotify_id, false))) ||
    `<p class="text-neutral-500 text-sm">Nothing found on Spotify for "${escapeHtml(q)}".</p>`;
}

async function importFromSpotify(kind, spotifyId, button) {
  const original = button.textContent;
  button.disabled = true;
  button.textContent = "Importing…";
  try {
    const res = await Admin.spotifyImport({ kind, spotify_id: spotifyId });
    toast(kind === "track"
      ? `Imported "${res.item.title}"`
      : `Imported ${res.imported} track${res.imported === 1 ? "" : "s"}`);
    button.textContent = "Imported ✓";
    button.classList.remove("bg-brand", "text-black");
    button.classList.add("bg-emerald-500/20", "text-emerald-300");
  } catch (err) {
    toast(err.message);
    button.disabled = false;
    button.textContent = original;
  }
}

/* ============================ ACTIONS ============================ */
async function onAdminAction(e) {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const id = el.dataset.id;
  const a = el.dataset.action;
  try {
    // --- staff ---
    if (a === "add-staff") staffForm(null);
    else if (a === "edit-staff") staffForm(state.staff[id]);
    else if (a === "reset-pw") resetPwForm(state.staff[id]);
    else if (a === "approve") {
      await Admin.setStatus(id, { status: "active" });
      toast("Account approved"); loadStaff();
    } else if (a === "suspend") {
      await Admin.setStatus(id, { status: "suspended" });
      toast("Account suspended"); loadStaff();
    } else if (a === "del-staff") {
      const u = state.staff[id];
      confirmDel(`staff account "${u.username}"`,
        () => Admin.deleteStaff(id).then(() => { toast("Staff member deleted"); loadStaff(); }));
    }
    // --- catalog ---
    else if (a === "add-song") songForm(null);
    else if (a === "edit-song") songForm(state.songs[id]);
    else if (a === "del-song") confirmDel("song", () => Admin.deleteSong(id).then(() => { toast("Song deleted"); loadSongs(""); }));
    else if (a === "add-artist") artistForm();
    else if (a === "del-artist") confirmDel("artist and ALL its albums & songs", () => Admin.deleteArtist(id).then(() => { toast("Artist deleted"); loadArtists(); }));
    else if (a === "add-album") albumForm();
    else if (a === "del-album") confirmDel("album", () => Admin.deleteAlbum(id).then(() => { toast("Album deleted"); loadAlbums(); }));
    // --- spotify ---
    else if (a === "sp-import") importFromSpotify(el.dataset.kind, el.dataset.sid, el);
  } catch (err) { toast(err.message); }
}

function confirmDel(label, onYes) {
  openModal(`
    <h2 class="text-xl font-bold mb-2">Delete ${escapeHtml(label)}?</h2>
    <p class="text-neutral-300 mb-5 text-sm">This can't be undone.</p>
    <div class="flex justify-end gap-2">
      <button data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
      <button id="do-del" class="px-5 py-2 rounded-full bg-red-500 text-white text-sm font-bold hover:bg-red-600">Delete</button>
    </div>`);
  document.getElementById("do-del").onclick = async () => {
    try { await onYes(); closeModal(); } catch (err) { toast(err.message); }
  };
}

/* ============================ MODAL ============================ */
function openModal(html) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="bg-base-700 rounded-lg p-6 w-full max-w-lg shadow-2xl max-h-[90vh] overflow-y-auto scroll-thin">${html}</div>`;
  root.classList.remove("hidden");
  root.onclick = (e) => { if (e.target === root || e.target.closest("[data-close]")) closeModal(); };
}
function closeModal() {
  const root = document.getElementById("modal-root");
  root.classList.add("hidden");
  root.innerHTML = "";
}
