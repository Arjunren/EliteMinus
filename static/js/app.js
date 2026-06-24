/* ---------------------------------------------------------------------------
 * app.js — client-side router + event wiring. Glues the API, the renderers
 * (components.js) and the audio engine (player.js) together.
 * ------------------------------------------------------------------------- */
let currentRoute = "";
let myPlaylists = [];
let menuSongId = null;
let searchTimer = null;
let searchToken = 0;

const INPUT_CLS =
  "w-full rounded bg-base-600 border border-neutral-700 px-3 py-2.5 " +
  "focus:border-white focus:ring-2 focus:ring-white/20 outline-none text-sm";

document.addEventListener("DOMContentLoaded", init);

function init() {
  // topbar identity
  const name = window.CURRENT_USER.name || window.CURRENT_USER.username;
  document.getElementById("user-initial").textContent = name.charAt(0).toUpperCase();
  document.getElementById("user-name").textContent = name;
  if (window.CURRENT_USER.isAdmin) {
    const link = document.getElementById("admin-link");
    if (link) { link.classList.remove("hidden"); link.classList.add("block"); }
  }

  Player.init();
  loadSidebar();

  // routing
  window.addEventListener("hashchange", () => { closeMenus(); router(); });
  if (!location.hash) location.hash = "#/home";  // triggers hashchange -> router()
  else router();                                  // existing hash: render immediately

  // delegated clicks inside the routed view
  document.getElementById("view").addEventListener("click", onAction);
  document.getElementById("view").addEventListener("scroll", closeMenus);

  // sidebar / topbar buttons
  document.getElementById("btn-create-playlist").onclick = createPlaylistFlow;
  document.getElementById("btn-back").onclick = () => history.back();
  document.getElementById("btn-fwd").onclick = () => history.forward();

  // user menu
  const userBtn = document.getElementById("btn-user");
  userBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    document.getElementById("context-menu").classList.add("hidden");
    document.getElementById("user-menu").classList.toggle("hidden");
  });

  // context menu actions
  document.getElementById("context-menu").addEventListener("click", onMenuAction);

  // global close / escape
  document.addEventListener("click", closeMenus);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeMenus(); closeModal(); }
  });
}

/* ===================== routing ===================== */
function parseHash() {
  const h = (location.hash.slice(1) || "/home");
  const [path, query] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  const route = parts[0] || "home";
  const id = parts[1];
  let q = "";
  if (query) q = new URLSearchParams(query).get("q") || "";
  return { route, id, q };
}

async function router() {
  const { route, id, q } = parseHash();
  setActiveNav(route);

  if (route === "search") { showSearch(q); return; }

  const view = document.getElementById("view");
  view.scrollTop = 0;
  view.innerHTML = renderLoading();
  try {
    if (route === "home")          view.innerHTML = renderHome(await API.home());
    else if (route === "library")  view.innerHTML = renderLibrary(await API.library());
    else if (route === "liked")    view.innerHTML = renderLiked(await API.liked());
    else if (route === "queue")    view.innerHTML = renderQueue();
    else if (route === "album")    view.innerHTML = renderAlbum(await API.album(id));
    else if (route === "playlist") view.innerHTML = renderPlaylist(await API.playlist(id));
    else if (route === "artist")   view.innerHTML = renderArtist(await API.artist(id));
    else                           view.innerHTML = renderHome(await API.home());
  } catch (err) {
    view.innerHTML = renderError(err.message);
  }
  currentRoute = route;
  UI.markPlaying();
}

function setActiveNav(route) {
  document.querySelectorAll("[data-nav]").forEach((el) =>
    el.classList.toggle("active", el.dataset.nav === route));
}

/* ===================== search ===================== */
function showSearch(q) {
  const view = document.getElementById("view");
  if (currentRoute !== "search") {
    view.scrollTop = 0;
    view.innerHTML = `
      <div class="px-6 pt-6 sticky top-0 bg-base-800 z-10 pb-3">
        <div class="relative max-w-md">
          <svg class="w-5 h-5 absolute left-4 top-1/2 -translate-y-1/2 text-neutral-500" viewBox="0 0 24 24" fill="currentColor"><path d="M10.5 3a7.5 7.5 0 015.94 12.08l4.24 4.24-1.42 1.42-4.24-4.24A7.5 7.5 0 1110.5 3z"/></svg>
          <input id="search-input" type="text" autocomplete="off" spellcheck="false"
                 placeholder="What do you want to listen to?"
                 class="w-full bg-white text-black rounded-full pl-11 pr-4 py-3 font-medium outline-none">
        </div>
      </div>
      <div id="search-results"></div>`;
    const input = document.getElementById("search-input");
    input.value = q || "";
    input.focus();
    input.addEventListener("input", () => onSearchInput(input.value));
  } else {
    const input = document.getElementById("search-input");
    if (input && input.value !== (q || "")) input.value = q || "";
  }
  currentRoute = "search";
  runSearch(q || "");
}

function onSearchInput(val) {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    history.replaceState(null, "", val ? "#/search?q=" + encodeURIComponent(val) : "#/search");
    runSearch(val);
  }, 250);
}

async function runSearch(val) {
  const box = document.getElementById("search-results");
  if (!box) return;
  const token = ++searchToken;
  try {
    const data = await API.search(val);
    if (token !== searchToken) return;          // a newer query won
    box.innerHTML = renderSearch(data, val);
    UI.markPlaying();
  } catch (err) {
    box.innerHTML = renderError(err.message);
  }
}

/* ===================== action dispatch ===================== */
function onAction(e) {
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const a = el.dataset.action;
  switch (a) {
    case "open": location.hash = el.dataset.href; break;
    case "play-row": Player.play(UI.viewTracks, +el.dataset.index); break;
    case "play-all": Player.play(UI.viewTracks, 0); break;
    case "shuffle-all": shuffleAll(); break;
    case "play-song": Player.playOne(UI.songIndex[el.dataset.songId]); break;
    case "play-context": playContext(el.dataset.ctype, el.dataset.cid); break;
    case "like": toggleLike(el); break;
    case "more": openContextMenu(el, e); break;
    case "follow": toggleFollow(el); break;
    case "search-genre": location.hash = "#/search?q=" + encodeURIComponent(el.dataset.q); break;
    case "edit-playlist": if (UI.pageContext) openPlaylistEditor(UI.pageContext.id); break;
    case "delete-playlist": if (UI.pageContext) confirmDeletePlaylist(UI.pageContext.id); break;
    case "new-playlist": createPlaylistFlow(); break;
  }
}

function shuffleAll() {
  if (!UI.viewTracks.length) return;
  Player.shuffle = true;
  const sb = document.getElementById("btn-shuffle");
  sb.classList.add("text-brand"); sb.classList.remove("text-neutral-400");
  Player.play(UI.viewTracks, Math.floor(Math.random() * UI.viewTracks.length));
}

async function playContext(type, id) {
  try {
    let tracks = [];
    if (type === "album") tracks = (await API.album(id)).tracks;
    else if (type === "playlist") tracks = (await API.playlist(id)).tracks;
    else if (type === "artist") tracks = (await API.artist(id)).top_songs;
    if (tracks.length) Player.play(tracks, 0);
    else toast("Nothing to play here");
  } catch (err) { toast("Could not play"); }
}

function toggleLike(el) {
  const id = +el.dataset.songId;
  const next = el.dataset.liked !== "1";
  API.like(id, next).then(() => {
    applyLikeState(id, next);
    toast(next ? "Added to Liked Songs" : "Removed from Liked Songs");
    if (currentRoute === "liked") router();   // refresh the liked list
  }).catch(() => toast("Could not update Liked Songs"));
}

function applyLikeState(id, liked) {
  id = +id;
  if (UI.songIndex[id]) UI.songIndex[id].liked = liked;
  document.querySelectorAll(`[data-action="like"][data-song-id="${id}"]`).forEach((btn) => {
    btn.dataset.liked = liked ? "1" : "0";
    btn.innerHTML = liked ? ICON.heartFill : ICON.heart;
    btn.classList.toggle("opacity-0", !liked);
    btn.classList.toggle("group-hover:opacity-100", !liked);
  });
  if (Player.current && Player.current.id === id) {
    Player.current.liked = liked;
    Player._updateLikeIcon();
  }
}

function toggleFollow(el) {
  const id = +el.dataset.artistId;
  const next = el.dataset.following !== "1";
  API.followArtist(id, next).then(() => {
    el.dataset.following = next ? "1" : "0";
    el.textContent = next ? "Following" : "Follow";
    toast(next ? "Following" : "Unfollowed");
  }).catch(() => toast("Could not update"));
}

/* ===================== context menu ===================== */
function openContextMenu(el, e) {
  e.stopPropagation();
  menuSongId = +el.dataset.songId;
  const song = UI.songIndex[menuSongId];
  const editable = UI.pageContext && UI.pageContext.type === "playlist" && UI.pageContext.editable;
  const liked = song && song.liked;

  const items = [
    `<button data-menu="queue" class="cm">Add to queue</button>`,
    `<button data-menu="like" class="cm">${liked ? "Remove from Liked Songs" : "Save to Liked Songs"}</button>`,
  ];
  if (song && song.album) items.push(`<button data-menu="album" class="cm">Go to album</button>`);
  if (song) items.push(`<button data-menu="artist" class="cm">Go to artist</button>`);
  if (editable) items.push(`<button data-menu="remove" class="cm text-red-400">Remove from this playlist</button>`);

  const plHtml = myPlaylists.length
    ? `<div class="border-t border-white/10 my-1"></div>
       <div class="px-3 pt-1 pb-1 text-xs uppercase tracking-wide text-neutral-500">Add to playlist</div>` +
      myPlaylists.map((p) =>
        `<button data-menu="addpl" data-pl-id="${p.id}" class="cm truncate">${escapeHtml(p.name)}</button>`).join("")
    : "";

  const menu = document.getElementById("context-menu");
  menu.innerHTML = items.join("") + plHtml;
  menu.classList.remove("hidden");

  let x = e.clientX, y = e.clientY;
  if (x + menu.offsetWidth > window.innerWidth) x = window.innerWidth - menu.offsetWidth - 8;
  if (y + menu.offsetHeight > window.innerHeight) y = window.innerHeight - menu.offsetHeight - 8;
  menu.style.left = x + "px";
  menu.style.top = y + "px";
}

async function onMenuAction(e) {
  const b = e.target.closest("[data-menu]");
  if (!b) return;
  const action = b.dataset.menu;
  const song = UI.songIndex[menuSongId];
  closeMenus();
  try {
    if (action === "queue") {
      if (!Player.queue.length) Player.playOne(song);
      else { Player.queue.splice(Player.index + 1, 0, song); Player._persist(); }
      toast("Added to queue");
    } else if (action === "like") {
      const next = !(song && song.liked);
      await API.like(menuSongId, next);
      applyLikeState(menuSongId, next);
      toast(next ? "Added to Liked Songs" : "Removed from Liked Songs");
      if (currentRoute === "liked") router();
    } else if (action === "album" && song && song.album) {
      location.hash = "#/album/" + song.album.id;
    } else if (action === "artist" && song) {
      location.hash = "#/artist/" + song.artist.id;
    } else if (action === "remove") {
      await API.removeFromPlaylist(UI.pageContext.id, menuSongId);
      toast("Removed from playlist");
      router();
    } else if (action === "addpl") {
      const r = await API.addToPlaylist(+b.dataset.plId, menuSongId);
      toast(r.added ? "Added to playlist" : "Already in playlist");
    }
  } catch (err) { toast("Action failed"); }
}

function closeMenus() {
  document.getElementById("context-menu").classList.add("hidden");
  document.getElementById("user-menu").classList.add("hidden");
}

/* ===================== sidebar ===================== */
async function loadSidebar() {
  try {
    myPlaylists = await API.playlists();
  } catch (e) { myPlaylists = []; }
  const list = document.getElementById("playlist-list");
  list.innerHTML = myPlaylists.map((p) => `
    <a href="#/playlist/${p.id}" class="flex items-center gap-3 p-2 rounded hover:bg-base-600">
      <img src="${p.image}" class="w-12 h-12 rounded shrink-0" alt="">
      <div class="min-w-0">
        <p class="truncate font-medium">${escapeHtml(p.name)}</p>
        <p class="text-xs text-neutral-400 truncate">Playlist · ${escapeHtml(p.owner ? p.owner.name : "you")}</p>
      </div>
    </a>`).join("") ||
    `<p class="text-sm text-neutral-500 px-2 py-4">Create your first playlist with the + above.</p>`;
}

/* ===================== modals (create / edit / delete playlist) ===== */
function openModal(html) {
  const root = document.getElementById("modal-root");
  root.innerHTML = `<div class="bg-base-700 rounded-lg p-6 w-full max-w-md shadow-2xl">${html}</div>`;
  root.classList.remove("hidden");
  root.onclick = (e) => {
    if (e.target === root || e.target.closest("[data-close]")) closeModal();
  };
}
function closeModal() {
  const root = document.getElementById("modal-root");
  root.classList.add("hidden");
  root.innerHTML = "";
}

function playlistForm(title, values = {}) {
  return `
    <form id="pl-form" class="space-y-4">
      <h2 class="text-2xl font-bold">${title}</h2>
      <div>
        <label class="block text-sm font-semibold mb-1">Name</label>
        <input name="name" required value="${escapeHtml(values.name || "")}" placeholder="My playlist" class="${INPUT_CLS}">
      </div>
      <div>
        <label class="block text-sm font-semibold mb-1">Description</label>
        <textarea name="description" rows="3" placeholder="Optional" class="${INPUT_CLS}">${escapeHtml(values.description || "")}</textarea>
      </div>
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" name="is_public" class="accent-brand w-4 h-4" ${values.is_public === false ? "" : "checked"}> Public playlist
      </label>
      <div class="flex justify-end gap-2 pt-2">
        <button type="button" data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
        <button type="submit" class="px-5 py-2 rounded-full bg-brand text-black text-sm font-bold hover:scale-105 transition">Save</button>
      </div>
    </form>`;
}

function readPlaylistForm(form) {
  const fd = new FormData(form);
  return {
    name: (fd.get("name") || "").trim(),
    description: (fd.get("description") || "").trim(),
    is_public: fd.get("is_public") != null,
  };
}

function createPlaylistFlow() {
  openModal(playlistForm("Create playlist"));
  document.getElementById("pl-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const pl = await API.createPlaylist(readPlaylistForm(e.target));
      closeModal();
      await loadSidebar();
      toast("Playlist created");
      location.hash = "#/playlist/" + pl.id;
    } catch (err) { toast("Could not create playlist"); }
  });
}

async function openPlaylistEditor(id) {
  let pl;
  try { pl = await API.playlist(id); } catch (e) { return toast("Could not load playlist"); }
  openModal(playlistForm("Edit details", {
    name: pl.name, description: pl.description, is_public: pl.is_public,
  }));
  document.getElementById("pl-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      await API.updatePlaylist(id, readPlaylistForm(e.target));
      closeModal();
      await loadSidebar();
      toast("Playlist updated");
      router();
    } catch (err) { toast("Could not update playlist"); }
  });
}

function confirmDeletePlaylist(id) {
  openModal(`
    <h2 class="text-2xl font-bold mb-2">Delete playlist?</h2>
    <p class="text-neutral-300 mb-6">This can't be undone.</p>
    <div class="flex justify-end gap-2">
      <button data-close class="px-4 py-2 rounded-full text-sm font-bold hover:bg-base-600">Cancel</button>
      <button id="confirm-del" class="px-5 py-2 rounded-full bg-red-500 text-white text-sm font-bold hover:bg-red-600">Delete</button>
    </div>`);
  document.getElementById("confirm-del").onclick = async () => {
    try {
      await API.deletePlaylist(id);
      closeModal();
      await loadSidebar();
      toast("Playlist deleted");
      location.hash = "#/library";
    } catch (err) { toast("Could not delete playlist"); }
  };
}
