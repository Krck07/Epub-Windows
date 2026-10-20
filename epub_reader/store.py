"""JSON-backed persistence for settings and reading progress.

Everything lives in a single data directory (default: %LOCALAPPDATA%/EpubReader)
with atomic writes so a crash mid-save never corrupts the state.
"""
from __future__ import annotations

import copy
import json
import os
import time
from typing import Dict, Any

DEFAULT_SETTINGS: Dict[str, Any] = {
    "theme": "dark",        # dark | light
    "font_size": 18,        # px
    "para_spacing": 1.2,    # multiplier applied to paragraph margins
    "columns": "auto",      # auto | 1 | 2  (auto follows the window aspect ratio)
    "mode": "paged",        # paged | scroll
}

SETTINGS_LIMITS = {
    "theme": ("dark", "light"),
    "font_size": (10, 48),
    "para_spacing": (0.2, 3.0),
    "columns": ("auto", "1", "2"),
    "mode": ("paged", "scroll"),
}


class Store:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.library_dir = os.path.join(data_dir, "library")
        os.makedirs(self.library_dir, exist_ok=True)
        self.settings_path = os.path.join(data_dir, "settings.json")
        self.progress_path = os.path.join(data_dir, "progress.json")
        self.library_path = os.path.join(data_dir, "library.json")
        self.settings = self._load_dict(self.settings_path, DEFAULT_SETTINGS)
        self.progress = self._load(self.progress_path, {})
        self.library = self._load(self.library_path, [])
        if not isinstance(self.library, list):
            self.library = []

    # ------------------------------------------------------------------ #
    # Low level
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load(path: str, default: Any) -> Any:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return copy.deepcopy(default)

    def _load_dict(self, path: str, default: Dict[str, Any]) -> Dict[str, Any]:
        data = self._load(path, {})
        merged = copy.deepcopy(default)
        if isinstance(data, dict):
            merged.update(data)
        return merged

    @staticmethod
    def _save(path: str, data: Any) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    def get_settings(self) -> Dict[str, Any]:
        return dict(self.settings)

    def update_settings(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in (patch or {}).items():
            if key not in SETTINGS_LIMITS:
                continue
            kind = SETTINGS_LIMITS[key]
            if isinstance(kind, tuple) and all(isinstance(v, str) for v in kind):
                if value in kind:
                    self.settings[key] = value
            else:
                lo, hi = kind
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    continue
                if lo <= number <= hi:
                    self.settings[key] = int(number) if key == "font_size" else number
        self._save(self.settings_path, self.settings)
        return self.get_settings()

    # ------------------------------------------------------------------ #
    # Progress
    # ------------------------------------------------------------------ #
    def get_progress(self, book_id: str) -> Dict[str, Any]:
        p = self.progress.get(book_id)
        if not isinstance(p, dict):
            return {}
        return p

    def all_progress(self) -> Dict[str, Any]:
        return {k: v for k, v in self.progress.items() if isinstance(v, dict)}

    def save_progress(self, book_id: str, chapter_index: int, pct: float, chapter_title: str = "") -> Dict[str, Any]:
        try:
            chapter_index = max(0, int(chapter_index))
            pct = max(0.0, min(1.0, float(pct)))
        except (TypeError, ValueError):
            return self.get_progress(book_id)
        self.progress[book_id] = {
            "chapter": chapter_index,
            "pct": round(pct, 4),
            "title": chapter_title or "",
            "updated": int(time.time()),
        }
        self._save(self.progress_path, self.progress)
        return self.get_progress(book_id)

    def clear_progress(self, book_id: str) -> None:
        self.progress.pop(book_id, None)
        self._save(self.progress_path, self.progress)

    # ------------------------------------------------------------------ #
    # Library
    # ------------------------------------------------------------------ #
    def library_entries(self) -> list:
        return [e for e in self.library if isinstance(e, dict) and e.get("id")]

    def find_entry(self, book_id: str) -> dict | None:
        for e in self.library:
            if e.get("id") == book_id:
                return e
        return None

    def add_entry(self, entry: dict) -> dict:
        self.library.append(entry)
        self._save(self.library_path, self.library)
        return entry

    def remove_entry(self, book_id: str) -> None:
        self.library = [e for e in self.library if e.get("id") != book_id]
        self._save(self.library_path, self.library)
