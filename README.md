# Epub Reader (Windows)

A minimal, offline, personal EPUB reader for Windows. Library + reader in one
small window, with touch, mouse and keyboard controls. No login, no cloud, no
databases — just JSON files and your books.

Built with **Python + pywebview (WebView2)** — the HTML inside EPUB files is
rendered by the browser engine that ships with Windows, so you see the book's
real layout, images and styles (not scraped text).

## Run it (development)

```bat
pip install -r requirements.txt
python main.py
```

## Package it (single exe)

```bat
build.bat
```

Creates `dist\EpubReader.exe` (PyInstaller, one file). The Python runtime is
embedded in the exe; WebView2 is part of Windows 10/11.

## Generate a sample book (for testing)

```bat
python make_sample_book.py
```

Writes `sample_book.epub` — add it via **＋ Add book** and read it.

## Controls

| Action | Touch | Mouse | Keyboard |
| --- | --- | --- | --- |
| Previous / next chapter | tap left / right edge, or swipe | click left / right edge | `←` / `→` |
| Focus mode (hide UI) | tap center | click center | `F` (or `Esc`) |
| Back to library | — | ‹ Library button | `Esc` |
| Settings | — | ⚙ button | `,` |
| Text size bigger / smaller | — | — | `+` / `-` |

### Focus mode
Tapping the center of the page hides every control and leaves only a thin
progress bar and percentage at the bottom. Tap the center again (or `Esc`) to
bring the UI back.

### Modes
- **Paged** — one chapter at a time; tap edges to turn.
- **Scroll** — continuous reading; each chapter is its own scrollable pane and
  neighbouring chapters load as you approach them.

### Layout
Wide windows (aspect > 1.4) automatically get the bookish **two-column**
serif layout; portrait windows get one column. Force either via Settings.

## Where things are stored

Everything lives in `%LOCALAPPDATA%\EpubReader` (deliberately outside
OneDrive):

```
EpubReader/
├── library/        # copies of your .epub files
├── library.json    # book list, series/volume, metadata
├── progress.json   # per-book chapter + position
└── settings.json   # theme, font size, spacing, columns, mode
```

## Tests

```bat
python -m pytest tests -v     # unit tests (parser, store, library)
python main.py --smoke        # end-to-end backend check without opening a GUI
```

## Manual test checklist

1. `python main.py` → library view opens, empty state visible.
2. **＋ Add book** → pick `sample_book.epub` (or any EPUB) → card appears with cover, title, author.
3. Try a bad input: point the picker at a `.txt` file → error toast, library unchanged.
4. Click the book → reader opens at chapter 1, chapter title shown in the top bar.
5. Tap right edge / press `→` → next chapter; dropdown shows all chapters with the book's own titles.
6. Scroll inside a chapter → progress bar and % update at the bottom.
7. Tap center → UI disappears, only progress bar + % remain; tap center again → UI returns.
8. Settings (⚙): change text size, paragraph spacing, theme, columns → applied live.
9. **⇵ Scroll** mode → chapters flow continuously, each with its own heading/pane.
10. Back to library → book shows its progress %; **close and reopen the app** → progress and settings are preserved.
11. ✎ on a card → set series “Demo”, volume 1 → card moves under the series group.
12. Add a second book, ✕ one of them (confirm) → card and its file are gone; the other is untouched.
13. Resize the window wide/tall → two-column ↔ one-column switches (auto mode).

## Known limitations

- Progress is tracked per chapter + scroll position (no word-exact resume inside a long chapter across restarts — you return to the same chapter and roughly the same place).
- EPUB internal hyperlinks are disabled (taps stay inside the reader).
- SVG-based book content may not render everywhere (WebView2 handles most).
- Very large image-heavy books: images are inlined per chapter on demand, which keeps loading fast, but memory grows as you scroll through scroll mode.
- No full-screen toggle (maximizing the window works).

## Suggested next improvements

1. **Word-exact resume** — save the DOM offset (or a text offset) inside the chapter, not just chapter + scroll %.
2. **Full-screen focus** — hide the Windows title bar (`window.set_fullscreen`) for distraction-free reading.
3. **Book search / filter** in the library (title/author/series) as the collection grows.
