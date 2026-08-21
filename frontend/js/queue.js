/* ---------------------------------------------------------------------------
 * queue.js — the playback queue.
 *
 * The queue lives on the server (one row per entry, ordered), so it survives a
 * reload and follows you between devices. Locally we keep a mirror and update
 * it optimistically: clicking "play" must feel instant, so the UI moves first
 * and the server call reconciles a moment later.
 * ------------------------------------------------------------------------- */
const Queue = {
  items: [],          // song objects, each with a queue_item_id
  index: 0,
  _syncing: false,

  get current() { return this.items[this.index] || null; },
  get upNext() { return this.items.slice(this.index + 1); },
  get length() { return this.items.length; },

  /* ---------------- loading ---------------- */
  async load() {
    try {
      this._apply(await API.queue());
    } catch (e) {
      this.items = [];
      this.index = 0;
    }
    this.render();
    return this.items;
  },

  _apply(payload) {
    if (!payload) return;
    this.items = payload.items || [];
    this.index = payload.index || 0;
    this.items.forEach((s) => { UI.songIndex[s.id] = s; });
  },

  /* ---------------- mutations ---------------- */
  /** Start a brand-new context (album, playlist, search results…). */
  async replace(tracks, startIndex = 0) {
    if (!tracks || !tracks.length) return;
    this.items = tracks.slice();
    this.index = Math.max(0, Math.min(startIndex, tracks.length - 1));
    this.render();

    try {
      this._apply(await API.replaceQueue(tracks.map((t) => t.id), this.index));
      this.render();
    } catch (e) { /* keep the local queue; it still plays */ }
  },

  /** Append to the end, or slot in right after the current track. */
  async add(tracks, playNext = false) {
    const list = Array.isArray(tracks) ? tracks : [tracks];
    if (!list.length) return;

    if (!this.items.length) {
      await this.replace(list, 0);
      Player.loadCurrent(true);
      return;
    }

    // Optimistic insert so the panel updates on the click.
    const at = playNext ? this.index + 1 : this.items.length;
    this.items.splice(at, 0, ...list);
    this.render();

    try {
      this._apply(await API.queueAdd(list.map((t) => t.id), playNext));
    } catch (e) { /* the optimistic copy stands */ }
    this.render();
    toast(list.length === 1
      ? (playNext ? "Playing next" : "Added to queue")
      : `${list.length} songs ${playNext ? "playing next" : "added to queue"}`);
  },

  async remove(itemId) {
    const at = this.items.findIndex((s) => s.queue_item_id === itemId);
    if (at < 0) return;
    const wasCurrent = at === this.index;

    this.items.splice(at, 1);
    if (at < this.index) this.index--;
    this.index = Math.max(0, Math.min(this.index, this.items.length - 1));
    this.render();

    try { this._apply(await API.queueRemove(itemId)); } catch (e) { /* ignore */ }
    this.render();

    // Removing the track that was playing means moving on to the next one.
    if (wasCurrent) Player.loadCurrent(Player.isPlaying);
  },

  async move(from, to) {
    if (from === to || from < 0 || from >= this.items.length) return;
    const [moved] = this.items.splice(from, 1);
    this.items.splice(to, 0, moved);

    if (from === this.index) this.index = to;
    else if (from < this.index && to >= this.index) this.index--;
    else if (from > this.index && to <= this.index) this.index++;
    this.render();

    try { this._apply(await API.queueMove(from, to)); } catch (e) { /* ignore */ }
    this.render();
  },

  /** Clear everything after the current track, the way Spotify does. */
  async clear() {
    if (this.items.length <= 1) return;
    this.items = this.items.slice(this.index, this.index + 1);
    this.index = 0;
    this.render();
    try { this._apply(await API.queueClear()); } catch (e) { /* ignore */ }
    this.render();
    toast("Queue cleared");
  },

  setIndex(i) {
    if (i < 0 || i >= this.items.length) return false;
    this.index = i;
    this.render();
    API.queueIndex(i).catch(() => {});
    return true;
  },

  /** Jump to a queue entry and start playing it. */
  playAt(i) {
    if (this.setIndex(i)) Player.loadCurrent(true);
  },

  /* ---------------- rendering ---------------- */
  render() {
    const counter = document.getElementById("queue-count");
    if (counter) {
      const left = Math.max(0, this.items.length - this.index - 1);
      counter.textContent = left ? left : "";
    }

    const body = document.getElementById("queue-body");
    if (body) body.innerHTML = renderQueuePanel(this);

    // The full-page /queue route mirrors the panel.
    if (typeof currentRoute !== "undefined" && currentRoute === "queue") {
      const view = document.getElementById("view");
      if (view) view.innerHTML = renderQueuePage(this);
    }
    if (window.UI && UI.markPlaying) UI.markPlaying();
  },
};

/* ---------------------------------------------------------------------------
 * Drag-and-drop reordering inside the queue panel / page.
 * Delegated so it keeps working after every re-render.
 * ------------------------------------------------------------------------- */
let dragFrom = null;

function bindQueueDragging(root) {
  root.addEventListener("dragstart", (e) => {
    const row = e.target.closest("[data-queue-index]");
    if (!row) return;
    dragFrom = +row.dataset.queueIndex;
    row.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    // Firefox needs some payload before it will start a drag.
    e.dataTransfer.setData("text/plain", String(dragFrom));
  });

  root.addEventListener("dragover", (e) => {
    const row = e.target.closest("[data-queue-index]");
    if (!row || dragFrom === null) return;
    e.preventDefault();
    root.querySelectorAll(".drop-target").forEach((n) => n.classList.remove("drop-target"));
    row.classList.add("drop-target");
  });

  root.addEventListener("dragleave", (e) => {
    const row = e.target.closest("[data-queue-index]");
    if (row) row.classList.remove("drop-target");
  });

  root.addEventListener("drop", (e) => {
    const row = e.target.closest("[data-queue-index]");
    if (!row || dragFrom === null) return;
    e.preventDefault();
    const to = +row.dataset.queueIndex;
    row.classList.remove("drop-target");
    if (to !== dragFrom) Queue.move(dragFrom, to);
    dragFrom = null;
  });

  root.addEventListener("dragend", () => {
    root.querySelectorAll(".dragging, .drop-target")
      .forEach((n) => n.classList.remove("dragging", "drop-target"));
    dragFrom = null;
  });
}
