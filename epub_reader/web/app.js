/* Epub Reader — front-end logic (vanilla JS, talks to the Python backend
   through the pywebview js_api bridge: window.pywebview.api.*) */
"use strict";

// ---------------------------------------------------------------- api ----
function apiReady() {
  return new Promise((resolve) => {
    if (window.pywebview && window.pywebview.api) return resolve(window.pywebview.api);
    const check = () => {
      if (window.pywebview && window.pywebview.api) {
        window.removeEventListener("pywebviewready", check);
        resolve(window.pywebview.api);
      }
    };
    window.addEventListener("pywebviewready", check);
    setTimeout(check, 50);
  });
}

// --------------------------------------------------------------- state ----
const state = {
  settings: { theme: "dark", font_size: 18, para_spacing: 1.2, columns: "auto", mode: "paged" },
  library: [],
  book: null,          // {id, title, author, series, volume}
  chapters: [],        // [{index, title}]
  chapterIndex: 0,
  focus: false,
  scrollCache: {},     // index -> {html, styles}
  panes: new Map(),    // index -> element
  busyChapter: null,
  libraryProgress: {},
};

const $ = (id) => document.getElementById(id);

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}

// -------------------------------------------------------------- toasts ----
let toastTimer = null;
function toast(msg, ms = 3200) {
  const t = $("global-toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), ms);
}

// ----------------------------------------------------------- settings ----
function applySettings() {
  const s = state.settings;
  const root = document.documentElement;
  root.dataset.theme = s.theme;
  root.style.setProperty("--font-size", s.font_size + "px");
  root.style.setProperty("--para-spacing", String(s.para_spacing));
  updateColumnsClass();
  if (state.book) $("btn-mode").textContent = s.mode === "scroll" ? "⇵ Paged" : "⇵ Scroll";
}

function updateColumnsClass() {
  const pages = $("pages");
  if (!pages || !state.book) return;
  let cols = state.settings.columns;
  if (cols === "auto") cols = window.innerWidth / window.innerHeight > 1.4 ? "2" : "1";
  pages.classList.toggle("two-col", cols === "2");
}

function syncSettingsPanel() {
  const s = state.settings;
  $("set-theme").value = s.theme;
  $("set-fontsize").value = s.font_size;
  $("set-spacing").value = s.para_spacing;
  $("set-columns").value = s.columns;
  $("set-mode").value = s.mode;
  $("val-fontsize").textContent = s.font_size + " px";
  $("val-spacing").textContent = "×" + Number(s.para_spacing).toFixed(1);
}

function persistSettings(patch) {
  Object.assign(state.settings, patch);
  applySettings();
  syncSettingsPanel();
  return apiReady().then((api) => api.updateSettings(patch));
}

// ------------------------------------------------------------ library ----
async function loadLibrary() {
  const api = await apiReady();
  state.library = await api.getLibrary();
  renderLibrary();
}

function renderLibrary() {
  const list = $("book-list");
  list.innerHTML = "";
  const empty = $("empty-state");

  const groups = new Map();
  for (const b of state.library) {
    const key = b.series || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(b);
  }
  for (const arr of groups.values()) {
    arr.sort((a, b) => (a.volume ?? 0) - (b.volume ?? 0) || a.title.localeCompare(b.title));
  }
  const keys = [...groups.keys()].sort((a, b) => (a === "" ? 1 : b === "" ? -1 : a.localeCompare(b)));

  if (state.library.length === 0) {
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  for (const key of keys) {
    const wrap = el("div", "series-group");
    if (key) {
      const head = el("div", "series-head", key);
      wrap.appendChild(head);
    }
    const grid = el("div", "books-grid");
    for (const b of groups.get(key)) grid.appendChild(bookCard(b));
    wrap.appendChild(grid);
    list.appendChild(wrap);
  }
}

function bookCard(b) {
  const card = el("div", "book-card");
  card.title = "Open: " + b.title;

  const coverBox = el("div", "cover-box");
  coverBox.appendChild(el("div", "cover-ph", "📖"));
  card.appendChild(coverBox);

  const meta = el("div", "book-meta");
  meta.appendChild(el("div", "book-title", b.title));
  meta.appendChild(el("div", "book-author", b.author || "Unknown author"));

  const foot = el("div", "book-foot");
  const p = state.libraryProgress[b.id] || {};
  const pct = Math.round((p.pct != null ? p.pct : 0) * 100);
  const mini = el("div", "mini-progress");
  const fill = el("div");
  fill.style.width = pct + "%";
  mini.appendChild(fill);
  foot.appendChild(mini);

  const pctRow = el("div", "book-pct");
  const label = el("span", null, pct > 0 ? pct + "% read" : "Not started");
  const actions = el("span", "book-actions");
  const edit = el("button", null, "✎");
  edit.title = "Edit series / volume";
  edit.addEventListener("click", (e) => { e.stopPropagation(); editSeries(b); });
  const del = el("button", "danger", "✕");
  del.title = "Remove from library";
  del.addEventListener("click", (e) => { e.stopPropagation(); removeBook(b); });
  actions.appendChild(edit);
  actions.appendChild(del);
  pctRow.appendChild(label);
  pctRow.appendChild(actions);
  foot.appendChild(pctRow);
  meta.appendChild(foot);
  card.appendChild(meta);

  card.addEventListener("click", () => openBook(b.id));

  // Load the cover image lazily. // eslint-disable-line
  apiReady().then(async (api) => {
    try {
      const cover = await api.getCover(b.id);
      if (cover) {
        const img = new Image();
        img.src = cover;
        img.alt = "";
        coverBox.replaceChildren(img);
      }
    } catch (err) { /* keep placeholder */ }
  });

  return card;
}

async function refreshProgress() {
  const api = await apiReady();
  state.libraryProgress = await api.getProgress();
}

function editSeries(b) {
  const series = prompt("Series (leave empty for none)", b.series || "");
  if (series === null) return;
  const volume = prompt("Volume number (leave empty if none)", b.volume != null ? String(b.volume) : "") || "";
  apiReady().then(async (api) => {
    await api.setSeries(b.id, series, volume === "" ? null : Number(volume));
    await Promise.all([loadLibrary(), refreshProgress()]);
    renderLibrary();
  });
}

function removeBook(b) {
  if (!confirm(`Remove “${b.title}” from the library? The file will be deleted.`)) return;
  apiReady().then(async (api) => {
    try {
      await api.removeBook(b.id);
      await Promise.all([loadLibrary(), refreshProgress()]);
      renderLibrary();
      toast("Book removed");
    } catch (err) {
      toast("Could not remove book: " + err.message);
    }
  });
}

// ------------------------------------------------------------- reader ----
async function openBook(id) {
  try {
    const api = await apiReady();
    const data = await api.openBook(id);
    state.book = data.book;
    state.chapters = data.chapters;
    state.chapterIndex = Math.min(Math.max(0, data.chapterIndex || 0), Math.max(0, state.chapters.length - 1));
    state.scrollCache = {};
    state.panes.clear();
    state.focus = false;
    document.body.classList.remove("focus");

    $("chapter-title").textContent = state.book.title;
    buildChapterSelect();
    $("reader-view").classList.remove("hidden");
    $("library-view").classList.add("hidden");
    $("settings-panel").classList.add("hidden");

    applySettings();
    updateColumnsClass();
    renderCurrentChapter(true);
  } catch (err) {
    toast("Could not open book: " + err.message);
  }
}

function buildChapterSelect() {
  const sel = $("chapter-select");
  sel.innerHTML = "";
  for (const c of state.chapters) {
    const opt = el("option", null, `${c.index + 1}. ${c.title}`);
    opt.value = c.index;
    sel.appendChild(opt);
  }
  sel.value = String(state.chapterIndex);
}

function chapterTitleAt(i) {
  const c = state.chapters[i];
  return c ? c.title : "";
}

async function fetchChapter(i) {
  if (state.scrollCache[i]) return state.scrollCache[i];
  const api = await apiReady();
  const data = await api.getChapter(state.book.id, i);
  state.scrollCache[i] = data;
  return data;
}

function makePane(data) {
  const pane = el("div", "chapter-pane");
  if (state.settings.mode === "scroll" && state.chapters.length > 1) {
    pane.appendChild(el("div", "chapter-h", data.title));
  }
  const body = el("div", data.title.toLowerCase().includes("cover") ? "chapter-body chapter-cover" : "chapter-body");
  body.innerHTML = data.html; // safe: sanitized + inlined by the backend
  pane.appendChild(body);
  return pane;
}

async function renderCurrentChapter(scrollToTop = false) {
  const i = state.chapterIndex;
  const pages = $("pages");
  state.busyChapter = i;
  try {
    if (state.settings.mode === "paged") {
      const data = await fetchChapter(i);
      pages.replaceChildren(makePane(data));
      state.panes.clear();
      state.panes.set(i, pages.firstElementChild);
    } else {
      // scroll mode: current chapter + neighbours, more loaded lazily
      const data = await fetchChapter(i);
      pages.replaceChildren(makePane(data));
      state.panes.clear();
      state.panes.set(i, pages.firstElementChild);
      await extendScroll(i + 1, true);
    }
    $("chapter-select").value = String(i);
    $("chapter-title").textContent = chapterTitleAt(i) || state.book.title;
    if (scrollToTop) $("reader-main").scrollTop = 0;
    updateProgress();
  } finally {
    state.busyChapter = null;
  }
}

async function extendScroll(target, afterCurrent) {
  if (state.settings.mode !== "scroll") return;
  if (target < 0 || target >= state.chapters.length) return;
  if (state.panes.has(target) || state.busyChapter === target) return;
  state.busyChapter = target;
  try {
    const data = await fetchChapter(target);
    const pane = makePane(data);
    state.panes.set(target, pane);
    if (afterCurrent) $("pages").appendChild(pane);
    else $("pages").prepend(pane);
  } finally {
    state.busyChapter = null;
  }
}

// ------------------------------------------------------------ navigation ----
function goChapter(i) {
  i = Math.max(0, Math.min(state.chapters.length - 1, i));
  if (i === state.chapterIndex && state.panes.has(i)) {
    const pane = state.panes.get(i);
    if (pane) pane.scrollIntoView({ behavior: "smooth" });
    return;
  }
  state.chapterIndex = i;
  renderCurrentChapter(true).then(() => saveProgressNow());
}

// -------------------------------------------------------------- progress ----
function computePct() {
  const main = $("reader-main");
  const pane = state.panes.get(state.chapterIndex);
  let pct = 1;
  if (pane) {
    const mainTop = main.getBoundingClientRect().top;
    const paneTop = pane.getBoundingClientRect().top - mainTop + main.scrollTop;
    const start = paneTop;
    const end = paneTop + pane.scrollHeight - main.clientHeight;
    if (end > start) {
      pct = (main.scrollTop - start) / (end - start);
    } // pane shorter than the viewport => count as fully read
  }
  pct = Math.max(0, Math.min(1, pct));
  const overall = (state.chapterIndex + pct) / Math.max(1, state.chapters.length);
  return { pct, overall: Math.max(0, Math.min(1, overall)) };
}

function updateProgress() {
  const { pct, overall } = computePct();
  $("progress-bar").style.width = (overall * 100) + "%";
  $("progress-pct").textContent = Math.round(overall * 100) + "%";
  $("focus-progress").style.width = (overall * 100) + "%";
  $("focus-pct").textContent = Math.round(overall * 100) + "%";
}

let saveTimer = null;
function saveProgressSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveProgressNow, 500);
}

function saveProgressNow() {
  if (!state.book) return;
  const { pct } = computePct();
  apiReady().then((api) =>
    api.saveProgress(state.book.id, state.chapterIndex, pct, chapterTitleAt(state.chapterIndex))
  ).catch(() => {});
}

// ------------------------------------------------------------- focus mode ----
function toggleFocus() {
  state.focus = !state.focus;
  document.body.classList.toggle("focus", state.focus);
  if (!state.focus) {
    const p = $("reader-main");
    p.focus({ preventScroll: true });
  }
}

// --------------------------------------------------------- tap / swipe ----
function initTapAndSwipe() {
  const main = $("reader-main");
  let touchStart = null;

  main.addEventListener("click", (e) => {
    if (state.book && !state.focus) {
      const w = main.clientWidth;
      const x = e.clientX;
      const target = e.target;
      if (target.closest("button, select, a, .book-actions")) return;
      if (window.getSelection().toString().length > 0) return;
      if (x < w * 0.3) goChapter(state.chapterIndex - 1);
      else if (x > w * 0.7) goChapter(state.chapterIndex + 1);
      else toggleFocus();
    }
  });

  main.addEventListener("touchstart", (e) => {
    if (e.touches.length === 1) {
      touchStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
    } else {
      touchStart = null;
    }
  }, { passive: true });

  main.addEventListener("touchend", (e) => {
    if (!touchStart) return;
    const t = e.changedTouches[0];
    const dx = t.clientX - touchStart.x;
    const dy = t.clientY - touchStart.y;
    const dt = Date.now() - touchStart.t;
    touchStart = null;
    if (dt < 600 && Math.abs(dx) > 70 && Math.abs(dx) > Math.abs(dy) * 2.5) {
      // horizontal swipe: change chapter (suppress the ensuing click)
      if (dx < 0) goChapter(state.chapterIndex + 1);
      else goChapter(state.chapterIndex - 1);
      const suppress = (ev) => { ev.stopPropagation(); ev.preventDefault(); };
      main.addEventListener("click", suppress, { capture: true, once: true });
    }
  }, { passive: true });
}

// ------------------------------------------------------------- keyboard ----
function initKeyboard() {
  window.addEventListener("keydown", (e) => {
    const inReader = !$("reader-view").classList.contains("hidden");
    const typing = /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName);

    if (e.key === "Escape") {
      if (!$("settings-panel").classList.contains("hidden")) {
        $("settings-panel").classList.add("hidden");
      } else if (state.focus) {
        toggleFocus();
      } else if (inReader) {
        backToLibrary();
      }
      e.preventDefault();
      return;
    }
    if (typing) return;

    if (inReader) {
      switch (e.key) {
        case "ArrowLeft": goChapter(state.chapterIndex - 1); e.preventDefault(); break;
        case "ArrowRight": goChapter(state.chapterIndex + 1); e.preventDefault(); break;
        case "f": case "F": toggleFocus(); e.preventDefault(); break;
        case "+": case "=": bumpFontSize(2); break;
        case "-": case "_": bumpFontSize(-2); break;
        case ",": toggleSettings(); break;
      }
    } else {
      if (e.key === "Enter" && state.library.length) openBook(state.library[0].id);
    }
  });
}

function bumpFontSize(d) {
  const next = Math.max(10, Math.min(48, state.settings.font_size + d));
  if (next !== state.settings.font_size) persistSettings({ font_size: next });
}

// --------------------------------------------------------------- wiring ----
function backToLibrary() {
  if (!state.book) return;
  saveProgressNow();
  state.book = null;
  state.panes.clear();
  state.focus = false;
  document.body.classList.remove("focus");
  $("reader-view").classList.add("hidden");
  $("library-view").classList.remove("hidden");
  Promise.all([refreshProgress(), loadLibrary()]).then(() => {
    state.libraryProgress = state.libraryProgress || {};
    renderLibrary();
  });
}

function toggleSettings() {
  const panel = $("settings-panel");
  panel.classList.toggle("hidden");
}

async function addBook() {
  try {
    const api = await apiReady();
    const entry = await api.addBook();
    if (!entry) return; // user cancelled the file dialog
    toast(`Added “${entry.title}”`);
    await Promise.all([loadLibrary(), refreshProgress()]);
    renderLibrary();
  } catch (err) {
    toast("Could not add book: " + err.message, 5000);
  }
}

function wire() {
  $("btn-add").addEventListener("click", addBook);
  $("btn-theme").addEventListener("click", () =>
    persistSettings({ theme: state.settings.theme === "dark" ? "light" : "dark" }));
  $("btn-back").addEventListener("click", backToLibrary);
  $("btn-prev").addEventListener("click", () => goChapter(state.chapterIndex - 1));
  $("btn-next").addEventListener("click", () => goChapter(state.chapterIndex + 1));
  $("chapter-select").addEventListener("change", (e) => goChapter(Number(e.target.value)));
  $("btn-mode").addEventListener("click", () => {
    const mode = state.settings.mode === "paged" ? "scroll" : "paged";
    persistSettings({ mode }).then(() => {
      if (state.book) renderCurrentChapter(true);
    });
  });
  $("btn-settings").addEventListener("click", toggleSettings);
  $("btn-settings-close").addEventListener("click", toggleSettings);

  $("set-theme").addEventListener("change", (e) => persistSettings({ theme: e.target.value }));
  $("set-fontsize").addEventListener("input", (e) => {
    state.settings.font_size = Number(e.target.value);
    applySettings();
    $("val-fontsize").textContent = state.settings.font_size + " px";
  });
  $("set-fontsize").addEventListener("change", (e) => persistSettings({ font_size: Number(e.target.value) }));
  $("set-spacing").addEventListener("input", (e) => {
    state.settings.para_spacing = Number(e.target.value);
    applySettings();
    $("val-spacing").textContent = "×" + Number(e.target.value).toFixed(1);
  });
  $("set-spacing").addEventListener("change", (e) => persistSettings({ para_spacing: Number(e.target.value) }));
  $("set-columns").addEventListener("change", (e) => persistSettings({ columns: e.target.value }));
  $("set-mode").addEventListener("change", (e) => persistSettings({ mode: e.target.value }));

  $("reader-main").addEventListener("scroll", () => {
    updateProgress();
    saveProgressSoon();
    if (state.settings.mode !== "scroll") return;
    const main = $("reader-main");
    const nearBottom = main.scrollTop + main.clientHeight > main.scrollHeight - main.clientHeight * 0.8;
    const nearTop = main.scrollTop < main.clientHeight * 0.35;
    if (nearBottom) {
      const next = state.chapterIndex + 1;
      if (next < state.chapters.length && !state.panes.has(next)) extendScroll(next, true);
    }
    if (nearTop && state.chapterIndex > 0) {
      if (!state.panes.has(state.chapterIndex - 1)) extendScroll(state.chapterIndex - 1, false);
    }
  }, { passive: true });

  window.addEventListener("resize", updateColumnsClass);
  initTapAndSwipe();
  initKeyboard();
}

// ---------------------------------------------------------------- init ----
window.addEventListener("DOMContentLoaded", async () => {
  wire();
  try {
    const api = await apiReady();
    const initial = await api.getInitial();
    Object.assign(state.settings, initial.settings);
    state.library = initial.library || [];
    state.libraryProgress = initial.progress || {};
    applySettings();
    renderLibrary();
  } catch (err) {
    toast("Backend error: " + err.message, 6000);
  }
});
