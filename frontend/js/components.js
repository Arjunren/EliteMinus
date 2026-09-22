/* ---------------------------------------------------------------------------
 * components.js — pure render helpers. Each returns an HTML string.
 * Anything interactive uses data-action attributes handled in app.js.
 * ------------------------------------------------------------------------- */
const UI = {
  viewTracks: [],          // tracks currently shown (for play-row / play-all)
  pageContext: null,       // { type, id, editable } of the open collection
  songIndex: {},           // id -> song object, so any rendered song is playable
};

const ICON = {
  play: '<svg class="w-6 h-6 ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
  playSm: '<svg class="w-4 h-4 ml-0.5" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>',
  heart: '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 21s-7.5-4.6-10-9.3C.6 8.7 2 5.5 5 5.5c1.9 0 3.2 1.2 4 2.4.8-1.2 2.1-2.4 4-2.4 3 0 4.4 3.2 3 6.2C19.5 16.4 12 21 12 21z"/></svg>',
  heartFill: '<svg class="w-5 h-5 text-brand" viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7.5-4.6-10-9.3C.6 8.7 2 5.5 5 5.5c1.9 0 3.2 1.2 4 2.4.8-1.2 2.1-2.4 4-2.4 3 0 4.4 3.2 3 6.2C19.5 16.4 12 21 12 21z"/></svg>',
  more: '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M6 10a2 2 0 100 4 2 2 0 000-4zm6 0a2 2 0 100 4 2 2 0 000-4zm6 0a2 2 0 100 4 2 2 0 000-4z"/></svg>',
  queue: '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M3 6h13v2H3zM3 11h13v2H3zM3 16h9v2H3zM16 11l5 3-5 3z"/></svg>',
  grip: '<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M9 4h2v2H9zM13 4h2v2h-2zM9 9h2v2H9zM13 9h2v2h-2zM9 14h2v2H9zM13 14h2v2h-2zM9 19h2v2H9zM13 19h2v2h-2z"/></svg>',
  close: '<svg class="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.4L17.6 5 12 10.6 6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4 17.6 19 19 17.6 13.4 12z"/></svg>',
};

const EQ = '<span class="eq track-eq"><span></span><span></span><span></span></span>';

/* ---- small pieces ---- */
function likeBtn(song) {
  return `<button data-action="like" data-song-id="${song.id}" data-liked="${song.liked ? 1 : 0}"
    class="like-btn shrink-0 ${song.liked ? "" : "opacity-0 group-hover:opacity-100"} text-neutral-400 hover:text-white transition"
    title="${song.liked ? "Remove from Liked Songs" : "Save to Liked Songs"}">${song.liked ? ICON.heartFill : ICON.heart}</button>`;
}

function sourceBadge(_song) { return ""; }

/* A single track row. opts: { showAlbum, showCover, number } */
function songRow(song, i, opts = {}) {
  UI.songIndex[song.id] = song;
  const showAlbum = opts.showAlbum !== false;
  const cover = opts.showCover
    ? `<img src="${song.image}" class="w-10 h-10 rounded shrink-0" alt="">` : "";
  const albumCell = showAlbum
    ? `<span data-action="open" data-href="#/album/${song.album ? song.album.id : ""}"
         class="hidden md:block text-sm text-neutral-400 truncate hover:underline hover:text-white">${escapeHtml(song.album ? song.album.title : "")}</span>`
    : "";

  return `
  <div class="track group grid items-center gap-3 px-4 py-2 rounded hover:bg-white/10
              grid-cols-[20px_1fr_auto] ${showAlbum ? "md:grid-cols-[20px_4fr_3fr_minmax(150px,1fr)]" : "md:grid-cols-[20px_1fr_minmax(150px,1fr)]"}"
       data-song-row data-song-id="${song.id}" data-action="play-row" data-index="${i}">
    <div class="text-right text-sm text-neutral-400 tabular-nums">
      <span class="track-num">${i + 1}</span>
      ${EQ}
      <button class="track-play hidden text-white" data-action="play-row" data-index="${i}">${ICON.playSm}</button>
    </div>
    <div class="flex items-center gap-3 min-w-0">
      ${cover}
      <div class="min-w-0">
        <p class="track-title font-medium truncate">${escapeHtml(song.title)}${song.explicit ? ' <span class="text-[9px] align-middle bg-neutral-600 text-neutral-200 px-1 rounded">E</span>' : ""}</p>
        <p class="text-sm text-neutral-400 truncate">
          <span data-action="open" data-href="#/artist/${song.artist ? song.artist.id : ""}" class="hover:underline hover:text-white">${escapeHtml(song.artist ? song.artist.name : "")}</span>
        </p>
      </div>
    </div>
    ${albumCell}
    <div class="flex items-center gap-3 justify-end">
      ${sourceBadge(song)}
      ${likeBtn(song)}
      <span class="text-sm text-neutral-400 tabular-nums w-10 text-right">${fmtTime(song.duration)}</span>
      <button data-action="more" data-song-id="${song.id}" data-index="${i}" class="more-btn opacity-0 group-hover:opacity-100 text-neutral-400 hover:text-white" title="More">${ICON.more}</button>
    </div>
  </div>`;
}

function trackListHeader(showAlbum) {
  return `
  <div class="grid items-center gap-3 px-4 pb-2 mb-2 border-b border-white/10 text-xs uppercase tracking-wider text-neutral-400
              grid-cols-[20px_1fr_auto] ${showAlbum ? "md:grid-cols-[20px_4fr_3fr_minmax(150px,1fr)]" : "md:grid-cols-[20px_1fr_minmax(150px,1fr)]"}">
    <span class="text-right">#</span>
    <span>Title</span>
    ${showAlbum ? '<span class="hidden md:block">Album</span>' : ""}
    <span class="text-right pr-1">
      <svg class="w-4 h-4 inline" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 100 20 10 10 0 000-20zm1 11h-4V6h2v5h3v2z"/></svg>
    </span>
  </div>`;
}

function songList(songs, opts = {}) {
  if (!songs.length)
    return `<p class="text-neutral-400 px-4 py-8">No songs here yet.</p>`;
  return trackListHeader(opts.showAlbum !== false) +
    songs.map((s, i) => songRow(s, i, opts)).join("");
}

/* ---- cards / shelves ---- */
function mediaCard(item) {
  // a song rendered as a card (Home shelves) -> clicking plays the song
  if (item.type === "song-card") {
    UI.songIndex[item.id] = item._song;
    return `
    <div class="card p-4 cursor-pointer group relative" data-action="play-song" data-song-id="${item.id}">
      <div class="relative mb-4">
        <img src="${item.image}" alt="" class="w-full aspect-square object-cover shadow-lg rounded-md">
        <button data-action="play-song" data-song-id="${item.id}"
          class="card-play absolute bottom-2 right-2 w-12 h-12 rounded-full bg-brand text-black grid place-items-center shadow-xl hover:scale-105 hover:bg-brand-light" title="Play">${ICON.play}</button>
      </div>
      <p class="font-bold truncate">${escapeHtml(item.title)}</p>
      <p class="text-sm text-neutral-400 mt-1 truncate">${escapeHtml(item.subtitle)}</p>
    </div>`;
  }

  const isArtist = item.type === "artist";
  let title, subtitle;
  if (item.type === "album") {
    title = item.title;
    subtitle = (item.artist ? item.artist.name : "") + (item.year ? " · " + item.year : "");
  } else if (item.type === "playlist") {
    title = item.name;
    subtitle = item.description || ("By " + (item.owner ? item.owner.name : "you"));
  } else {
    title = item.name;
    subtitle = "Artist";
  }

  return `
  <div class="card p-4 cursor-pointer group relative" data-action="open" data-href="#/${item.type}/${item.id}">
    <div class="relative mb-4">
      <img src="${item.image}" alt="" class="w-full aspect-square object-cover shadow-lg ${isArtist ? "rounded-full" : "rounded-md"}">
      <button data-action="play-context" data-ctype="${item.type}" data-cid="${item.id}"
        class="card-play absolute bottom-2 right-2 w-12 h-12 rounded-full bg-brand text-black grid place-items-center shadow-xl hover:scale-105 hover:bg-brand-light"
        title="Play">${ICON.play}</button>
    </div>
    <p class="font-bold truncate ${isArtist ? "text-center" : ""}">${escapeHtml(title)}</p>
    <p class="text-sm text-neutral-400 mt-1 line-clamp-2 ${isArtist ? "text-center" : ""}">${escapeHtml(subtitle)}</p>
  </div>`;
}

function shelf(title, items, opts = {}) {
  if (!items || !items.length) return "";
  const link = opts.href
    ? `<a href="${opts.href}" class="text-sm font-bold text-neutral-400 hover:underline">Show all</a>` : "";
  return `
  <section class="mb-8">
    <div class="flex items-end justify-between mb-4">
      <h2 class="text-2xl font-bold cursor-default">${escapeHtml(title)}</h2>
      ${link}
    </div>
    <div class="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      ${items.map(mediaCard).join("")}
    </div>
  </section>`;
}

/* Quick-pick tiles used at the top of Home */
function quickTile(item) {
  return `
  <div class="card flex items-center gap-3 overflow-hidden cursor-pointer group" data-action="open" data-href="#/${item.type}/${item.id}">
    <img src="${item.image}" class="w-16 h-16 object-cover ${item.type === "artist" ? "rounded-full m-1" : ""}" alt="">
    <span class="font-bold truncate flex-1">${escapeHtml(item.name || item.title)}</span>
    <button data-action="play-context" data-ctype="${item.type}" data-cid="${item.id}"
      class="card-play mr-4 w-10 h-10 rounded-full bg-brand text-black grid place-items-center shadow-lg shrink-0">${ICON.playSm}</button>
  </div>`;
}

/* ---- collection header (album / playlist / liked) ---- */
function collectionHeader({ kind, title, subtitle, image, meta, gradient, big }) {
  const cover = image
    ? `<img src="${image}" class="w-36 h-36 md:w-52 md:h-52 rounded shadow-2xl object-cover" alt="">`
    : `<div class="w-36 h-36 md:w-52 md:h-52 rounded shadow-2xl grid place-items-center bg-gradient-to-br ${gradient || "from-yellow-500 to-amber-700"}">
         <svg class="w-20 h-20 text-black" viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7.5-4.6-10-9.3C.6 8.7 2 5.5 5 5.5c1.9 0 3.2 1.2 4 2.4.8-1.2 2.1-2.4 4-2.4 3 0 4.4 3.2 3 6.2C19.5 16.4 12 21 12 21z"/></svg>
       </div>`;
  return `
  <div class="page-head px-6 pt-12 pb-6" style="--head:${gradient ? "#6b5310" : "#3a3a3a"}">
    <div class="flex flex-col md:flex-row items-center md:items-end gap-6">
      ${cover}
      <div class="text-center md:text-left">
        <p class="text-sm font-semibold uppercase">${escapeHtml(kind)}</p>
        <h1 class="font-extrabold tracking-tight ${big ? "text-4xl md:text-7xl" : "text-3xl md:text-5xl"} my-3 break-words">${escapeHtml(title)}</h1>
        ${subtitle ? `<p class="text-neutral-300 mb-1">${subtitle}</p>` : ""}
        <p class="text-sm text-neutral-300">${meta}</p>
      </div>
    </div>
  </div>`;
}

function playAllBar(extra = "") {
  return `
  <div class="px-6 py-5 flex items-center gap-5 flex-wrap">
    <button data-action="play-all" class="w-14 h-14 rounded-full bg-brand text-black grid place-items-center shadow-xl hover:scale-105 hover:bg-brand-light" title="Play">${ICON.play}</button>
    <button data-action="shuffle-all" class="text-neutral-400 hover:text-white" title="Shuffle">
      <svg class="w-7 h-7" viewBox="0 0 24 24" fill="currentColor"><path d="M17 3l4 4-4 4v-3h-2.5l-2.3 3.2-1.2-1.7L13 7h4V3zM3 7h4.5l8 11H21v-3l4 4-4 4v-3h-6.5l-8-11H3V7z"/></svg>
    </button>
    <button data-action="queue-all" class="text-neutral-400 hover:text-white" title="Add all to queue">${ICON.queue}</button>
    ${extra}
  </div>`;
}

/* =====================  QUEUE  ===================== */
/** One row in the queue side-panel: drag handle, cover, title, remove. */
function queueRow(song, i, isCurrent) {
  UI.songIndex[song.id] = song;
  return `
  <div class="queue-row group flex items-center gap-3 p-2 rounded hover:bg-white/10 ${isCurrent ? "bg-white/5" : ""}"
       draggable="true" data-queue-index="${i}" data-song-row data-song-id="${song.id}">
    <span class="text-neutral-600 cursor-grab shrink-0 opacity-0 group-hover:opacity-100">${ICON.grip}</span>
    <img src="${song.image}" class="w-10 h-10 rounded shrink-0" alt=""
         data-action="queue-play" data-queue-index="${i}">
    <div class="min-w-0 flex-1 cursor-pointer" data-action="queue-play" data-queue-index="${i}">
      <p class="text-sm font-medium truncate ${isCurrent ? "text-brand" : ""}">${escapeHtml(song.title)}</p>
      <p class="text-xs text-neutral-400 truncate">${escapeHtml(song.artist ? song.artist.name : "")}</p>
    </div>
    ${song.queue_source === "manual"
      ? '<span class="text-[9px] uppercase tracking-wide text-neutral-600 shrink-0">added</span>' : ""}
    <button data-action="queue-remove" data-item-id="${song.queue_item_id}"
            class="shrink-0 text-neutral-500 hover:text-white opacity-0 group-hover:opacity-100"
            title="Remove from queue">${ICON.close}</button>
  </div>`;
}

function renderQueuePanel(queue) {
  if (!queue.length) {
    return `<p class="text-sm text-neutral-500 p-4 text-center">
      Nothing queued yet.<br>Play something to get started.</p>`;
  }
  const current = queue.items[queue.index];
  const upNext = queue.items
    .map((s, i) => ({ s, i }))
    .filter(({ i }) => i > queue.index);

  return `
    ${current ? `
      <p class="px-2 pt-1 pb-2 text-[11px] uppercase tracking-wider text-neutral-500">Now playing</p>
      ${queueRow(current, queue.index, true)}` : ""}
    ${upNext.length ? `
      <p class="px-2 pt-4 pb-2 text-[11px] uppercase tracking-wider text-neutral-500">
        Next up · ${upNext.length}</p>
      ${upNext.map(({ s, i }) => queueRow(s, i, false)).join("")}`
      : `<p class="text-xs text-neutral-600 px-2 pt-4">Nothing else queued.</p>`}`;
}

function renderQueuePage(queue) {
  UI.viewTracks = queue.items;
  UI.pageContext = { type: "queue", id: null, editable: true };

  if (!queue.length) {
    return `<div class="px-6 pt-10 text-center text-neutral-400">
      <p class="text-2xl font-bold text-white mb-2">Your queue is empty</p>
      Play an album or a playlist and it will show up here.</div>`;
  }

  const current = queue.items[queue.index];
  const upNext = queue.items.map((s, i) => ({ s, i })).filter(({ i }) => i > queue.index);
  const played = queue.items.map((s, i) => ({ s, i })).filter(({ i }) => i < queue.index);

  return `
  <div class="view-enter px-4 sm:px-6 pt-6 pb-10 max-w-4xl">
    <div class="flex items-center justify-between mb-5">
      <h1 class="text-3xl font-bold">Queue</h1>
      <div class="flex items-center gap-2">
        <span class="text-sm text-neutral-500">${queue.length} songs · ${fmtTotalDuration(queue.items.reduce((t, s) => t + (s.duration || 0), 0))}</span>
        <button data-action="clear-queue" class="px-3 py-1.5 rounded-full bg-base-600 hover:bg-base-500 text-sm font-bold">Clear</button>
      </div>
    </div>

    ${current ? `
      <h2 class="text-sm uppercase tracking-wider text-neutral-500 mb-2">Now playing</h2>
      <div class="mb-6">${queueRow(current, queue.index, true)}</div>` : ""}

    ${upNext.length ? `
      <h2 class="text-sm uppercase tracking-wider text-neutral-500 mb-2">
        Next up <span class="normal-case text-neutral-600">— drag to reorder</span></h2>
      <div class="mb-6">${upNext.map(({ s, i }) => queueRow(s, i, false)).join("")}</div>` : ""}

    ${played.length ? `
      <h2 class="text-sm uppercase tracking-wider text-neutral-500 mb-2">Already played</h2>
      <div class="opacity-60">${played.map(({ s, i }) => queueRow(s, i, false)).join("")}</div>` : ""}
  </div>`;
}

/* =====================  PAGE RENDERERS  ===================== */
function renderLoading() {
  return `<div class="grid place-items-center h-full"><div class="animate-spin w-10 h-10 border-4 border-neutral-600 border-t-brand rounded-full"></div></div>`;
}
function renderError(msg) {
  return `<div class="grid place-items-center h-full text-center px-6">
    <div><p class="text-2xl font-bold mb-2">Something went wrong</p>
    <p class="text-neutral-400">${escapeHtml(msg || "Please try again.")}</p></div></div>`;
}

function renderHome(data) {
  UI.viewTracks = data.trending || [];
  UI.pageContext = null;
  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";

  const quick = [...(data.featured_playlists || []).slice(0, 6)];
  const quickHtml = quick.length ? `
    <div class="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 mb-8">
      ${quick.map(quickTile).join("")}
    </div>` : "";

  return `
  <div class="view-enter px-6 pt-6 pb-10">
    <h1 class="text-3xl font-bold mb-6">${greet}</h1>
    ${quickHtml}
    ${data.recently_played && data.recently_played.length
      ? shelf("Recently played", data.recently_played.map(songToCard))
      : ""}
    ${shelf("Trending now", (data.trending || []).map(songToCard))}
    ${shelf("Featured playlists", data.featured_playlists)}
    ${shelf("Popular albums", data.popular_albums)}
    ${shelf("Popular artists", data.top_artists)}
  </div>`;
}

/* turn a song into an album-style card for shelves */
function songToCard(song) {
  return {
    type: "song-card", id: song.id, image: song.image,
    title: song.title, subtitle: song.artist ? song.artist.name : "", _song: song,
  };
}

function renderSearch(data, q) {
  if (!q) {
    UI.viewTracks = [];
    const genres = (data && data.genres) || [];
    const colors = ["from-pink-500", "from-emerald-500", "from-orange-500", "from-sky-500",
                    "from-purple-500", "from-rose-500", "from-teal-500", "from-amber-500"];
    return `
    <div class="view-enter px-6 pt-6 pb-10">
      <h2 class="text-2xl font-bold mb-5">Browse all</h2>
      <div class="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
        ${genres.map((g, i) => `
          <div data-action="search-genre" data-q="${escapeHtml(g)}"
               class="relative h-32 rounded-lg overflow-hidden cursor-pointer bg-gradient-to-br ${colors[i % colors.length]} to-black/40">
            <span class="absolute top-3 left-3 text-xl font-bold">${escapeHtml(g)}</span>
          </div>`).join("")}
      </div>
    </div>`;
  }

  UI.viewTracks = data.songs || [];
  UI.pageContext = null;
  const nothing = !data.songs.length && !data.artists.length &&
                  !data.albums.length && !data.playlists.length;
  if (nothing)
    return `<div class="view-enter px-6 pt-10 text-center">
      <p class="text-2xl font-bold mb-2">No results found for "${escapeHtml(q)}"</p>
      <p class="text-neutral-400 mb-6">Check your spelling, or use the Suggest
        music link in the footer to ask an administrator to add it.</p></div>`;

  const topSong = data.songs[0];
  const topResult = topSong ? `
    <div class="md:col-span-1">
      <h2 class="text-2xl font-bold mb-4">Top result</h2>
      <div class="card p-5 group relative cursor-pointer" data-action="play-row" data-index="0">
        <img src="${topSong.image}" class="w-24 h-24 rounded shadow-lg mb-4" alt="">
        <p class="text-2xl font-bold truncate">${escapeHtml(topSong.title)}</p>
        <p class="text-sm text-neutral-400 mt-1">Song · <span data-action="open" data-href="#/artist/${topSong.artist ? topSong.artist.id : ""}" class="hover:underline">${escapeHtml(topSong.artist ? topSong.artist.name : "")}</span></p>
        <button data-action="play-row" data-index="0" class="card-play absolute bottom-5 right-5 w-12 h-12 rounded-full bg-brand text-black grid place-items-center shadow-xl">${ICON.play}</button>
      </div>
    </div>` : "";

  const songsCol = data.songs.length ? `
    <div class="md:col-span-2">
      <h2 class="text-2xl font-bold mb-4">Songs</h2>
      <div>${data.songs.slice(0, 5).map((s, i) => songRow(s, i, { showAlbum: false, showCover: true })).join("")}</div>
    </div>` : "";

  return `
  <div class="view-enter px-6 pt-6 pb-10">
    <div class="grid md:grid-cols-3 gap-6 mb-8">${topResult}${songsCol}</div>
    ${shelf("Artists", data.artists)}
    ${shelf("Albums", data.albums)}
    ${shelf("Playlists", data.playlists)}
  </div>`;
}

function renderAlbum(a) {
  UI.viewTracks = a.tracks || [];
  UI.pageContext = { type: "album", id: a.id, editable: false };
  return `
  <div class="view-enter">
    ${collectionHeader({
      kind: "Album", title: a.title, image: a.image,
      subtitle: a.artist ? `<span data-action="open" data-href="#/artist/${a.artist.id}" class="font-bold hover:underline cursor-pointer">${escapeHtml(a.artist.name)}</span>` : "",
      meta: `${a.year ? a.year + " · " : ""}${a.song_count} songs`,
    })}
    ${playAllBar()}
    <div class="px-2 pb-10">${songList(a.tracks, { showAlbum: false })}</div>
  </div>`;
}

function renderPlaylist(p) {
  UI.viewTracks = p.tracks || [];
  UI.pageContext = { type: "playlist", id: p.id, editable: !!p.editable };
  const owner = p.owner ? p.owner.name : "";
  const controls = p.editable ? `
    <button data-action="edit-playlist" class="text-neutral-400 hover:text-white" title="Edit details">
      <svg class="w-6 h-6" viewBox="0 0 24 24" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1 1 0 000-1.41l-2.34-2.34a1 1 0 00-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.58z"/></svg>
    </button>
    <button data-action="delete-playlist" class="text-neutral-400 hover:text-red-400" title="Delete playlist">
      <svg class="w-6 h-6" viewBox="0 0 24 24" fill="currentColor"><path d="M6 7h12l-1 14H7L6 7zm3-3h6l1 2H8l1-2z"/></svg>
    </button>` : `
    <button data-action="duplicate-playlist" class="px-4 py-1.5 rounded-full border border-neutral-500 hover:border-white text-sm font-bold" title="Save a copy to your library">
      Save a copy
    </button>`;

  return `
  <div class="view-enter">
    ${collectionHeader({
      kind: p.is_public ? "Playlist" : "Private playlist", title: p.name,
      image: p.image, big: true,
      subtitle: p.description ? escapeHtml(p.description) : "",
      meta: `<span class="font-bold text-white">${escapeHtml(owner)}</span> · ${p.song_count} songs, ${fmtTotalDuration(p.total_duration)}`,
    })}
    ${playAllBar(controls)}
    <div class="px-2 pb-10">
      ${p.tracks.length ? songList(p.tracks, { showAlbum: true })
        : `<div class="text-center py-16 px-6">
             <p class="text-xl font-bold mb-2">This playlist is empty</p>
             <p class="text-neutral-400 mb-6">Search for songs and use the ⋯ menu to add them here.</p>
             <a href="#/search" class="inline-block px-6 py-2.5 rounded-full bg-brand text-black font-bold">Find something to add</a>
           </div>`}
    </div>
  </div>`;
}

function renderLiked(p) {
  UI.viewTracks = p.tracks || [];
  UI.pageContext = { type: "liked", id: null, editable: false };
  return `
  <div class="view-enter">
    ${collectionHeader({
      kind: "Playlist", title: "Liked Songs", gradient: "from-yellow-500 to-amber-700",
      big: true, meta: `<span class="font-bold text-white">${escapeHtml(p.owner.name)}</span> · ${p.song_count} songs, ${fmtTotalDuration(p.total_duration)}`,
    })}
    ${p.tracks.length ? playAllBar() : ""}
    <div class="px-2 pb-10">
      ${p.tracks.length ? songList(p.tracks, { showAlbum: true })
        : `<p class="text-neutral-400 px-4 py-10 text-center">Songs you like will appear here.<br>Tap the ♡ on any song to save it.</p>`}
    </div>
  </div>`;
}

function renderArtist(a) {
  UI.viewTracks = a.top_songs || [];
  UI.pageContext = { type: "artist", id: a.id, editable: false };
  const followCls = a.following
    ? "border border-white text-white"
    : "border border-neutral-500 text-white hover:border-white";
  return `
  <div class="view-enter">
    <div class="page-head px-6 pt-16 pb-6 flex flex-col md:flex-row items-center md:items-end gap-6" style="--head:#444">
      <img src="${a.image}" class="w-40 h-40 rounded-full shadow-2xl object-cover" alt="">
      <div class="text-center md:text-left">
        <p class="text-sm font-semibold uppercase">Artist</p>
        <h1 class="text-4xl md:text-6xl font-extrabold my-3">${escapeHtml(a.name)}</h1>
        <p class="text-sm text-neutral-300">${fmtCount(a.monthly_listeners)} listeners${a.genre ? " · " + escapeHtml(a.genre) : ""}</p>
      </div>
    </div>
    <div class="px-6 py-5 flex items-center gap-5 flex-wrap">
      <button data-action="play-all" class="w-14 h-14 rounded-full bg-brand text-black grid place-items-center shadow-xl hover:scale-105" title="Play">${ICON.play}</button>
      <button data-action="queue-all" class="text-neutral-400 hover:text-white" title="Add all to queue">${ICON.queue}</button>
      <button data-action="follow" data-artist-id="${a.id}" data-following="${a.following ? 1 : 0}"
        class="follow-btn px-4 py-1.5 rounded-full text-sm font-bold ${followCls}">${a.following ? "Following" : "Follow"}</button>
    </div>
    ${a.bio ? `<p class="px-6 text-neutral-300 max-w-3xl mb-6">${escapeHtml(a.bio)}</p>` : ""}
    <div class="px-2 mb-8"><h2 class="text-2xl font-bold px-4 mb-3">Popular</h2>${songList(a.top_songs, { showAlbum: true })}</div>
    <div class="px-6 pb-10">${shelf("Albums", a.albums)}</div>
  </div>`;
}

function renderLibrary(data) {
  UI.viewTracks = [];
  UI.pageContext = null;
  const likedCard = `
    <div class="card p-4 cursor-pointer group" data-action="open" data-href="#/liked">
      <div class="w-full aspect-square rounded-md mb-4 grid place-items-center bg-gradient-to-br from-yellow-500 to-amber-700">
        <svg class="w-14 h-14 text-black" viewBox="0 0 24 24" fill="currentColor"><path d="M12 21s-7.5-4.6-10-9.3C.6 8.7 2 5.5 5 5.5c1.9 0 3.2 1.2 4 2.4.8-1.2 2.1-2.4 4-2.4 3 0 4.4 3.2 3 6.2C19.5 16.4 12 21 12 21z"/></svg>
      </div>
      <p class="font-bold truncate">Liked Songs</p>
      <p class="text-sm text-neutral-400 mt-1">${data.liked_count} liked songs</p>
    </div>`;

  return `
  <div class="view-enter px-6 pt-6 pb-10">
    <div class="flex items-center justify-between mb-5">
      <h1 class="text-3xl font-bold">Your Library</h1>
      <button data-action="new-playlist" class="px-4 py-2 rounded-full bg-base-600 hover:bg-base-500 text-sm font-bold">+ New playlist</button>
    </div>
    <h2 class="text-xl font-bold mb-3">Playlists</h2>
    <div class="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 mb-10">
      ${likedCard}
      ${data.playlists.map(mediaCard).join("")}
    </div>
    ${data.artists.length ? `
      <h2 class="text-xl font-bold mb-3">Following</h2>
      <div class="grid gap-4 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        ${data.artists.map(mediaCard).join("")}
      </div>` : ""}
  </div>`;
}
