"""Library management: copy EPUBs into the app folder, track metadata, remove.

The app keeps its own copy of every book under <data_dir>/library so books
stay available even if the original file moves, and so the user's documents
folder is never modified.
"""
from __future__ import annotations

import os
import re
import shutil
import time
import uuid

from .epub import Epub, EpubError
from .store import Store


class Library:
    def __init__(self, store: Store):
        self.store = store

    def add_book(self, source_path: str, series: str = "", volume: int | None = None) -> dict:
        """Copy an EPUB into the library and register it. Raises EpubError."""
        source_path = os.path.abspath(source_path)
        if not os.path.isfile(source_path):
            raise EpubError("File not found")

        # Validate + read metadata before copying anything.
        book = Epub(source_path)

        entry_id = uuid.uuid4().hex[:12]
        safe_title = re.sub(r'[\\/:*?"<>|\r\n]+', "_", book.title).strip() or "book"
        dest = self._unique_path(os.path.join(self.store.library_dir, f"{safe_title} [{entry_id[:6]}].epub"))
        try:
            shutil.copy2(source_path, dest)
        except OSError as exc:
            raise EpubError(f"Could not copy the file into the library ({exc})") from exc

        try:
            volume = int(volume) if volume is not None and volume != "" else None
        except (TypeError, ValueError):
            volume = None

        entry = {
            "id": entry_id,
            "relpath": os.path.relpath(dest, self.store.library_dir).replace("\\", "/"),
            "title": book.title,
            "author": book.author,
            "series": (series or "").strip(),
            "volume": volume,
            "chapters": book.total_chapters,
            "added": int(time.time()),
        }
        self.store.add_entry(entry)
        self.store.save_progress(entry_id, 0, 0.0, book.chapters[0].title if book.chapters else "")
        return entry

    def remove_book(self, book_id: str) -> None:
        entry = self.store.find_entry(book_id)
        if entry is None:
            return
        self.store.remove_entry(book_id)
        self.store.clear_progress(book_id)
        rel = entry.get("relpath")
        if rel:
            path = os.path.join(self.store.library_dir, rel.replace("/", os.sep))
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except OSError:
                pass  # state is cleaned up regardless

    def get_book_path(self, book_id: str) -> str | None:
        entry = self.store.find_entry(book_id)
        if not entry or not entry.get("relpath"):
            return None
        path = os.path.join(self.store.library_dir, entry["relpath"].replace("/", os.sep))
        return path if os.path.isfile(path) else None

    def set_series(self, book_id: str, series: str, volume: int | None = None) -> dict | None:
        entry = self.store.find_entry(book_id)
        if entry is None:
            return None
        entry["series"] = (series or "").strip()
        try:
            entry["volume"] = int(volume) if volume is not None and volume != "" else None
        except (TypeError, ValueError):
            entry["volume"] = None
        self.store._save(self.store.library_path, self.store.library)
        return entry

    # ------------------------------------------------------------------ #
    def _unique_path(self, path: str) -> str:
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        n = 1
        while os.path.exists(f"{base} ({n}){ext}"):
            n += 1
        return f"{base} ({n}){ext}"
