"""Epub Reader — application entry point.

Runs a pywebview window (Windows: WebView2, which ships with the OS) hosting
the HTML/CSS/JS front-end in epub_reader/web. Python exposes the backend API
through the js_api bridge; all state lives in %LOCALAPPDATA%/EpackReader
(see data_dir()).

Run:  python main.py
"""
from __future__ import annotations

import os
import sys
import traceback

from epub_reader import Epub, EpubError, Library, Store

try:
    import webview
except ImportError:  # helpful message instead of a raw traceback
    sys.stderr.write(
        "The 'pywebview' package is missing.\n"
        "Install dependencies first:  pip install -r requirements.txt\n"
    )
    sys.exit(1)


def data_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "EpubReader")


def resource_path(*parts: str) -> str:
    """Locate bundled resources both in dev and inside a PyInstaller exe."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


class Api:
    """Methods exposed to the front-end as window.pywebview.api.*."""

    def __init__(self):
        self.store = Store(data_dir())
        self.library = Library(self.store)

    # ----------------------------------------------------------- library --
    def getInitial(self):
        return {
            "settings": self.store.get_settings(),
            "library": self._library_public(),
            "progress": self.store.all_progress(),
        }

    def getLibrary(self):
        return self._library_public()

    def addBook(self):
        """Open a native file dialog, copy the EPUB into the library."""
        window = webview.windows[0]
        result = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=("EPUB files (*.epub;*.ebp)", "All files (*.*)"),
        )
        if not result:
            return None
        path = result[0] if isinstance(result, (list, tuple)) else result
        entry = self.library.add_book(path)
        return entry

    def removeBook(self, book_id: str):
        self.library.remove_book(book_id)
        return True

    def setSeries(self, book_id: str, series: str, volume):
        entry = self.library.set_series(book_id, series or "", volume)
        if entry is None:
            raise EpubError("Book not found in library")
        return entry

    # ------------------------------------------------------------ reader ---
    def openBook(self, book_id: str):
        entry = self.store.find_entry(book_id)
        if entry is None:
            raise EpubError("Book not found in library")
        path = self.library.get_book_path(book_id)
        if not path:
            raise EpubError("Book file is missing from the library folder")
        book = Epub(path)
        progress = self.store.get_progress(book_id)
        total = max(1, book.total_chapters)
        chapter_index = int(progress.get("chapter", 0)) if progress else 0
        chapter_index = max(0, min(chapter_index, total - 1))
        return {
            "book": {
                "id": entry["id"],
                "title": entry.get("title") or book.title,
                "author": entry.get("author") or book.author,
                "series": entry.get("series") or "",
                "volume": entry.get("volume"),
            },
            "chapters": [{"index": i, "title": c.title} for i, c in enumerate(book.chapters)],
            "chapterIndex": chapter_index,
        }

    def _epub_for(self, book_id: str) -> Epub:
        entry = self.store.find_entry(book_id)
        if entry is None:
            raise EpubError("Book not found in library")
        path = self.library.get_book_path(book_id)
        if not path:
            raise EpubError("Book file is missing from the library folder")
        return Epub(path)

    def getChapter(self, book_id: str, index: int):
        try:
            return self._epub_for(book_id).get_chapter(int(index))
        except IndexError as exc:
            raise EpubError(str(exc)) from exc

    def getCover(self, book_id: str):
        try:
            return self._epub_for(book_id).get_cover_data_uri()
        except EpubError:
            return None

    def saveProgress(self, book_id: str, chapter_index, pct, chapter_title: str = ""):
        self.store.find_entry(book_id)  # validate the book exists
        return self.store.save_progress(book_id, chapter_index, pct, chapter_title)

    def getProgress(self):
        return self.store.all_progress()

    # --------------------------------------------------------- settings ----
    def updateSettings(self, patch: dict):
        return self.store.update_settings(patch or {})

    # ------------------------------------------------------------- helpers -
    def _library_public(self):
        out = []
        for e in self.store.library_entries():
            out.append({
                "id": e["id"],
                "title": e.get("title") or "Untitled",
                "author": e.get("author") or "",
                "series": e.get("series") or "",
                "volume": e.get("volume"),
            })
        return out


def smoke_test() -> int:
    """Exercise the whole backend without opening a window: python main.py --smoke"""
    import tempfile

    from epub_reader.sample import build_sample_book

    with tempfile.TemporaryDirectory() as tmp:
        sample = build_sample_book(os.path.join(tmp, "sample.epub"))
        store = Store(os.path.join(tmp, "appdata"))
        lib = Library(store)
        entry = lib.add_book(sample, series="Demo", volume=1)
        book = Epub(lib.get_book_path(entry["id"]))
        assert book.total_chapters == 3, book.total_chapters
        ch = book.get_chapter(0)
        assert "data:image/png;base64," in ch["html"]
        assert ch["styles"]
        assert book.get_cover_data_uri() is not None
        p = store.save_progress(entry["id"], 2, 0.6, "Landfall")
        store2 = Store(os.path.join(tmp, "appdata"))  # simulated restart
        assert store2.get_progress(entry["id"])["chapter"] == 2
        s = store2.update_settings({"font_size": 22, "theme": "light"})
        assert s["font_size"] == 22 and s["theme"] == "light"
        print("smoke test OK: parse, cover, chapter, progress, settings all work")
        return 0


def main() -> int:
    if "--smoke" in sys.argv:
        return smoke_test()
    api = Api()
    index_html = resource_path("epub_reader", "web", "index.html")
    if not os.path.isfile(index_html):
        sys.stderr.write(f"Front-end not found at {index_html}\n")
        return 1

    try:
        window = webview.create_window(
            "Epub Reader",
            index_html,
            js_api=api,
            width=1100,
            height=760,
            min_size=(520, 420),
            background_color="#17181c",
            text_select=True,
        )
    except Exception:
        sys.stderr.write("Failed to create the window:\n" + traceback.format_exc())
        return 1

    webview.start(debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
