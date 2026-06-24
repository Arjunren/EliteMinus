/* ---------------------------------------------------------------------------
 * admin.js — controller for the admin dashboard. Reuses api.js for the fetch
 * wrapper (API._req), toast(), escapeHtml(), fmtTime() and fmtCount().
 * ------------------------------------------------------------------------- */
const Admin = {
  stats:        ()      => API.get("/api/admin/stats"),
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
  users:        ()      => API.get("/api/admin/users"),
  createUser:   (d)     => API.post("/api/admin/users", d),
  updateUser:   (id, d) => API.put("/api/admin/users/" + id, d),
  deleteUser:   (id)    => API.del("/api/admin/users/" + id),
};

const INPUT = "w-full rounded bg-base-600 border border-neutral-700 px-3 py-2.5 focus:border-white focus:ring-2 focus:ring-white/20 outline-none text-sm";
const state = { songs: {}, users: {}, artists: [], albums: [] };
let searchTimer = null;

const TITLES = { dashboard: "Dashboard", songs: "Songs", artists: "Artists", albums: "Albums", users: "Users" };

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("admin-name").textContent = CURRENT_USER.name;
  document.getElementById("admin-initial").textContent = CURRENT_USER.name.charAt(0).toUpperCase();
  window.addEventListener("hashchange", routeAdmin);
  document.getElementById("admin-view").addEventListener("click", onAdminAction);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
  if (!location.hash) location.hash = "#/dashboard";
  else routeAdmin();
});

function routeAdmin() {
  const section = (location.hash.replace("#/", "") || "dashboard").split("/")[0];
  document.querySelectorAll(".anav").forEach((a) =>
    a.classList.toggle("bg-base-600", a.dataset.nav === section));
  document.querySelectorAll(".anav").forEach((a) =>
    a.classList.toggle("text-white", a.dataset.nav === section));
  document.getElementById("page-title").textContent = TITLES[section] || "Admin";
  ({ dashboard: showDashboard, songs: showSongs, artists: showArtists,
     albums: showAlbums, users: showUsers }[section] || showDashboard)();
}

const view = () => document.getElementById("admin-view");
function loading() { view().innerHTML = `<div class="grid place-items-center h-64"><div class="animate-spin w-9 h-9 border-4 border-neutral-600 border-t-brand rounded-full"></div></div>`; }
function errBox(m) { view().innerHTML = `<p class="text-red-400">${escapeHtml(m)}</p>`; }

/* ============================ DASHBOARD ============================ */
async function showDashboard() {
  loading();
  let s;
  try { s = await Admin.stats(); } catch (e) { return errBox(e.message); }
  const t = s.totals;
  const cards = [
    ["Users", t.users, "#facc15"], ["Songs", t.songs, "#3b82f6"],
    ["Artists", t.artists, "#a855f7"], ["Albums", t.albums, "#f59e0b"],
    ["Playlists", t.playlists, "#ec4899"], ["Likes", t.likes, "#ef4444"],
    ["Total plays", fmtCount(t.plays), "#14b8a6"], ["Play events", t.play_events, "#8b5cf6"],
  ];
  const maxPlays = Math.max(1, ...s.top_songs.map((x) => x.plays));

  view().innerHTML = `
    <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
      ${cards.map(([label, val, c]) => `
        <div class="bg-base-700 rounded-lg p-4">
          <div class="w-2 h-2 rounded-full mb-2" style="background:${c}"></div>
          <p class="text-2xl font-bold">${val}</p>
          <p class="text-sm text-neutral-400">${label}</p>
        </div>`).join("")}
    </div>

    <div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-6">
      <div class="bg-base-700 rounded-lg p-4">
        <p class="text-sm text-neutral-400">Plays today</p>
        <p class="text-3xl font-bold text-brand">${s.plays_today}</p>
      </div>
      <div class="bg-base-700 rounded-lg p-4">
        <p class="text-sm text-neutral-400">Plays this week</p>
        <p class="text-3xl font-bold text-brand">${s.plays_week}</p>
      </div>
      <div class="bg-base-700 rounded-lg p-4">
        <p class="text-sm text-neutral-400 mb-2">Songs by genre</p>
        <div class="flex flex-wrap gap-2">
          ${s.genres.map((g) => `<span class="text-xs bg-base-600 rounded-full px-2.5 py-1">${escapeHtml(g.genre)} · ${g.songs}</span>`).join("")}
        </div>
      </div>
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
      </div>
      <div class="space-y-3">
        <div class="bg-base-700 rounded-lg p-4">
          <h3 class="font-bold mb-3">Recent plays</h3>
          ${s.recent_plays.length ? s.recent_plays.map((p) => `
            <div class="flex justify-between text-sm py-1.5 border-b border-white/5 last:border-0">
              <span class="truncate pr-2">${escapeHtml(p.song)} <span class="text-neutral-500">· ${escapeHtml(p.artist)}</span></span>
              <span class="text-neutral-500 shrink-0">${escapeHtml(p.at)}</span>
            </div>`).join("") : '<p class="text-sm text-neutral-500">No plays yet.</p>'}
        </div>
        <div class="bg-base-700 rounded-lg p-4">
          <h3 class="font-bold mb-3">Newest users</h3>
          ${s.recent_users.map((u) => `
            <div class="flex justify-between text-sm py-1.5 border-b border-white/5 last:border-0">
              <span>${escapeHtml(u.username)} ${u.is_admin ? '<span class="text-xs bg-brand/20 text-brand rounded px-1.5 py-0.5 ml-1">admin</span>' : ""}</span>
              <span class="text-neutral-500">${escapeHtml(u.created_at)}</span>
            </div>`).join("")}
        </div>
      </div>
    </div>`;
}

/* ============================ SONGS ============================ */
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
      <table class="w-full text-sm min-w-[640px]">
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

async function showSongs() {
  view().innerHTML = toolbar("song-search", "add-song", "+ Add song") +
    tableShell(["Title", "Artist", "Album", "Duration", "Plays", ""], "song-rows");
  const input = document.getElementById("song-search");
  input.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => loadSongs(input.value), 250);
  });
  loadSongs("");
}
async function loadSongs(q) {
  const body = document.getElementById("song-rows");
  try {
    const songs = await Admin.songs(q);
    state.songs = {};
    body.innerHTML = songs.length ? songs.map((s) => {
      state.songs[s.id] = s;
      return `<tr class="border-b border-white/5 hover:bg-white/5">
        <td class="py-2.5 px-4 font-medium">${escapeHtml(s.title)}</td>
        <td class="py-2.5 px-4 text-neutral-300">${escapeHtml(s.artist.name)}</td>
        <td class="py-2.5 px-4 text-neutral-400">${escapeHtml(s.album ? s.album.title : "—")}</td>
        <td class="py-2.5 px-4 text-neutral-400 tabular-nums">${fmtTime(s.duration)}</td>
        <td class="py-2.5 px-4 text-neutral-400 tabular-nums">${fmtCount(s.play_count)}</td>
        <td class="py-2.5 px-4 text-right whitespace-nowrap">
          ${iconBtn("edit-song", s.id, "Edit", EDIT_SVG)}
          ${iconBtn("del-song", s.id, "Delete", DEL_SVG, "text-red-400")}
        </td></tr>`;
    }).join("") : `<tr><td colspan="6" class="py-8 px-4 text-center text-neutral-500">No songs found.</td></tr>`;
  } catch (e) { body.innerHTML = `<tr><td colspan="6" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`; }
}

async function songForm(song) {
  if (!state.artists.length) state.artists = await Admin.artists();
  if (!state.albums.length) state.albums = await Admin.albums();
  const artistId = song ? song.artist.id : (state.artists[0] && state.artists[0].id);
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
        <input name="audio_url" value="${song ? escapeHtml(song.audio_url) : ""}" placeholder="https://…/song.mp3" class="${INPUT}"></div>
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
    const fd = new FormData(e.target);
    const d = Object.fromEntries(fd.entries());
    try {
      if (song) await Admin.updateSong(song.id, d);
      else await Admin.createSong(d);
      closeModal(); toast(song ? "Song updated" : "Song added");
      loadSongs(document.getElementById("song-search") ? document.getElementById("song-search").value : "");
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
async function showArtists() {
  view().innerHTML = toolbar(null, "add-artist", "+ Add artist") +
    tableShell(["Name", "Genre", "Albums", "Songs", "Monthly listeners", ""], "artist-rows");
  loadArtists();
}
async function loadArtists() {
  const body = document.getElementById("artist-rows");
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
        <td class="py-2.5 px-4 text-right">${iconBtn("del-artist", a.id, "Delete", DEL_SVG, "text-red-400")}</td>
      </tr>`).join("") : `<tr><td colspan="6" class="py-8 text-center text-neutral-500">No artists.</td></tr>`;
  } catch (e) { body.innerHTML = `<tr><td colspan="6" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`; }
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
async function showAlbums() {
  view().innerHTML = toolbar(null, "add-album", "+ Add album") +
    tableShell(["Title", "Artist", "Year", "Songs", ""], "album-rows");
  loadAlbums();
}
async function loadAlbums() {
  const body = document.getElementById("album-rows");
  try {
    const albums = await Admin.albums();
    state.albums = albums;
    body.innerHTML = albums.length ? albums.map((a) => `
      <tr class="border-b border-white/5 hover:bg-white/5">
        <td class="py-2.5 px-4 font-medium">${escapeHtml(a.title)}</td>
        <td class="py-2.5 px-4 text-neutral-300">${escapeHtml(a.artist ? a.artist.name : "—")}</td>
        <td class="py-2.5 px-4 text-neutral-400">${a.year || "—"}</td>
        <td class="py-2.5 px-4 text-neutral-400">${a.songs}</td>
        <td class="py-2.5 px-4 text-right">${iconBtn("del-album", a.id, "Delete", DEL_SVG, "text-red-400")}</td>
      </tr>`).join("") : `<tr><td colspan="5" class="py-8 text-center text-neutral-500">No albums.</td></tr>`;
  } catch (e) { body.innerHTML = `<tr><td colspan="5" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`; }
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

/* ============================ USERS ============================ */
async function showUsers() {
  view().innerHTML = toolbar(null, "add-user", "+ Add user") +
    tableShell(["Username", "Email", "Role", "Playlists", "Likes", "Joined", ""], "user-rows");
  loadUsers();
}
async function loadUsers() {
  const body = document.getElementById("user-rows");
  try {
    const users = await Admin.users();
    state.users = {};
    body.innerHTML = users.map((u) => {
      state.users[u.id] = u;
      const role = u.is_admin
        ? '<span class="text-xs bg-brand/20 text-brand rounded px-2 py-0.5">admin</span>'
        : '<span class="text-xs bg-base-600 text-neutral-300 rounded px-2 py-0.5">listener</span>';
      return `<tr class="border-b border-white/5 hover:bg-white/5">
        <td class="py-2.5 px-4 font-medium">${escapeHtml(u.username)}</td>
        <td class="py-2.5 px-4 text-neutral-400">${escapeHtml(u.email)}</td>
        <td class="py-2.5 px-4">${role}</td>
        <td class="py-2.5 px-4 text-neutral-400">${u.playlists}</td>
        <td class="py-2.5 px-4 text-neutral-400">${u.likes}</td>
        <td class="py-2.5 px-4 text-neutral-500">${escapeHtml(u.created_at)}</td>
        <td class="py-2.5 px-4 text-right whitespace-nowrap">
          <button data-action="toggle-admin" data-id="${u.id}" class="text-xs px-2 py-1 rounded hover:bg-white/10 text-neutral-300">${u.is_admin ? "Revoke admin" : "Make admin"}</button>
          ${iconBtn("reset-pw", u.id, "Reset password", '<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M12 1a5 5 0 00-5 5v3H5v12h14V9h-2V6a5 5 0 00-5-5zm3 8H9V6a3 3 0 116 0v3z"/></svg>')}
          ${iconBtn("del-user", u.id, "Delete", DEL_SVG, "text-red-400")}
        </td></tr>`;
    }).join("");
  } catch (e) { body.innerHTML = `<tr><td colspan="7" class="py-4 px-4 text-red-400">${escapeHtml(e.message)}</td></tr>`; }
}
function userForm() {
  openModal(`
    <form id="user-form" class="space-y-3">
      <h2 class="text-xl font-bold mb-1">Add user</h2>
      <div><label class="block text-sm font-semibold mb-1">Username</label><input name="username" required class="${INPUT}"></div>
      <div><label class="block text-sm font-semibold mb-1">Email</label><input name="email" type="email" required class="${INPUT}"></div>
      <div><label class="block text-sm font-semibold mb-1">Password</label><input name="password" type="text" required placeholder="min 6 characters" class="${INPUT}"></div>
      <label class="flex items-center gap-2 text-sm"><input type="checkbox" name="is_admin" class="accent-brand w-4 h-4"> Make this user an admin</label>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">Create</button>
      </div>
    </form>`);
  document.getElementById("user-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    try {
      await Admin.createUser({ username: fd.get("username"), email: fd.get("email"),
        password: fd.get("password"), is_admin: fd.get("is_admin") != null });
      closeModal(); toast("User created"); loadUsers();
    } catch (err) { toast(err.message); }
  });
}
function resetPwForm(user) {
  openModal(`
    <form id="pw-form" class="space-y-3">
      <h2 class="text-xl font-bold mb-1">Reset password</h2>
      <p class="text-sm text-neutral-400">for <b class="text-white">${escapeHtml(user.username)}</b></p>
      <input name="password" type="text" required placeholder="New password (min 6)" class="${INPUT}">
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold">Reset</button>
      </div>
    </form>`);
  document.getElementById("pw-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await Admin.updateUser(user.id, { password: new FormData(e.target).get("password") });
      closeModal(); toast("Password reset");
    } catch (err) { toast(err.message); }
  });
}

/* ============================ ACTIONS ============================ */
async function onAdminAction(e) {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const id = el.dataset.id;
  const a = el.dataset.action;
  try {
    if (a === "add-song") songForm(null);
    else if (a === "edit-song") songForm(state.songs[id]);
    else if (a === "del-song") confirmDel("song", () => Admin.deleteSong(id).then(() => { toast("Song deleted"); loadSongs(""); }));
    else if (a === "add-artist") artistForm();
    else if (a === "del-artist") confirmDel("artist and ALL its albums & songs", () => Admin.deleteArtist(id).then(() => { toast("Artist deleted"); loadArtists(); }));
    else if (a === "add-album") albumForm();
    else if (a === "del-album") confirmDel("album", () => Admin.deleteAlbum(id).then(() => { toast("Album deleted"); loadAlbums(); }));
    else if (a === "add-user") userForm();
    else if (a === "reset-pw") resetPwForm(state.users[id]);
    else if (a === "del-user") confirmDel("user account", () => Admin.deleteUser(id).then(() => { toast("User deleted"); loadUsers(); }).catch((err) => toast(err.message)));
    else if (a === "toggle-admin") {
      const u = state.users[id];
      await Admin.updateUser(id, { is_admin: !u.is_admin });
      toast("Role updated"); loadUsers();
    }
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
  root.innerHTML = `<div class="bg-base-700 rounded-lg p-6 w-full max-w-md shadow-2xl max-h-[90vh] overflow-y-auto scroll-thin">${html}</div>`;
  root.classList.remove("hidden");
  root.onclick = (e) => { if (e.target === root || e.target.closest("[data-close]")) closeModal(); };
}
function closeModal() {
  const root = document.getElementById("modal-root");
  root.classList.add("hidden");
  root.innerHTML = "";
}
