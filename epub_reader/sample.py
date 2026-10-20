"""Generate a small demo EPUB for trying out the reader.

Usage:  python -m epub_reader.sample [output.epub]
"""
from __future__ import annotations

import base64
import struct
import sys
import zipfile
import zlib

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _solid_png(width: int, height: int, rgb) -> bytes:
    """Minimal solid-color PNG writer (stdlib only)."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(rgb) * width
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(row * height, 9))
            + chunk(b"IEND", b""))


COVER_PNG = _solid_png(480, 720, (52, 78, 138))

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

CSS = """
body { font-family: Georgia, serif; color: #222; }
h1 { font-size: 1.5em; margin: 0 0 0.6em; }
h2 { font-size: 1.2em; margin: 1.2em 0 0.5em; }
p { margin: 0.55em 0; line-height: 1.6; }
img { max-width: 100%; height: auto; display: block; margin: 1em auto; }
"""


def _chapter(title: str, body: str, img: bool = False) -> str:
    # chapters live in OEBPS/text/, assets one level up -> exercise ../ resolution
    img_tag = '<img src="../images/pic.png"/>' if img else ""
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>' + title +
        '</title><link rel="stylesheet" href="../style.css"/></head><body>'
        "<h1>" + title + "</h1>" + body + img_tag + "</body></html>"
    )


def build_sample_book(path: str = "sample_book.epub") -> str:
    ch1 = _chapter(
        "The Lighthouse",
        "<p>The sea was the colour of slate that morning, and the lighthouse beam swept over it "
        "like a slow metronome. Mara climbed the ninety-one steps for the third time that week; "
        "the lamp had a habit of flickering, and nobody else would go up to look.</p>"
        "<p>Halfway up she paused, as always, at the narrow window where the keeper’s log was "
        "stapled to the wall. The last entry was dated three winters ago, in handwriting that "
        "grew shakier with each line.</p>"
        "<p>At the top of the stairs, the great lens waited in its cage of brass, and the "
        "flicker began the moment her shadow crossed the floor.</p>",
        img=True,
    )
    ch2 = _chapter(
        "What the Lens Remembered",
        "<p>The mechanism was a clockwork of mirrors, and like all clocks it kept a time that "
        "was not quite the town’s. When Mara oiled the bearings, the beam steadied — and in "
        "the steadied light she could see, just for a moment, the outline of a ship that "
        "should have been forty years adrift.</p>"
        "<p>“Not a fault in the glass,” she wrote in the log, in her own hand, “a fault in the "
        "remembering.”</p>"
        "<p>Below, the village bells rang the hour. Above, the lens turned, patient as a "
        "weather system, gathering whatever the night let go.</p>",
    )
    ch3 = _chapter(
        "Landfall",
        "<p>By the third night the flickering had stopped altogether. The beam went out and "
        "came back on schedule, clean as a struck match, and the ships in the channel "
        "reported, one by one, that they had lost whatever it was they had been chasing.</p>"
        "<p>Mara kept the log open on the desk, pen ready, in case the light wanted to say "
        "something else. It did not. Some machines only want to be wound.</p>"
        "<p>And some evenings, if the fog was thin enough, the beam reached further than the "
        "horizon — politely, briefly, and only for ships that were lost.</p>",
    )

    opf = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>The Lighthouse That Kept Its Own Time</dc:title>"
        "<dc:creator>Mara Quill</dc:creator>"
        '<meta name="cover" content="cover-item"/>'
        "</metadata><manifest>"
        '<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="ch2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="ch3" href="text/ch3.xhtml" media-type="application/xhtml+xml"/>'
        '<item id="nav" href="text/nav.xhtml" media-type="application/vnd.epub+xml"/>'
        '<item id="css" href="style.css" media-type="text/css"/>'
        '<item id="cover-item" href="images/cover.png" media-type="image/png"/>'
        '<item id="pic" href="images/pic.png" media-type="image/png"/>'
        "</manifest><spine>"
        '<itemref idref="ch1"/><itemref idref="ch2"/><itemref idref="ch3"/>'
        "</spine></package>"
    )

    nav = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Contents</title></head><body>'
        '<nav xmlns:epub="http://www.idpf.org/2007/ops" epub:type="toc"><ol>'
        '<li><a href="ch1.xhtml">The Lighthouse</a></li>'
        '<li><a href="ch2.xhtml">What the Lens Remembered</a></li>'
        '<li><a href="ch3.xhtml">Landfall</a></li>'
        "</ol></nav></body></html>"
    )

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("OEBPS/content.opf", opf)
        zf.writestr("OEBPS/style.css", CSS)
        zf.writestr("OEBPS/text/ch1.xhtml", ch1)
        zf.writestr("OEBPS/text/ch2.xhtml", ch2)
        zf.writestr("OEBPS/text/ch3.xhtml", ch3)
        zf.writestr("OEBPS/text/nav.xhtml", nav)
        zf.writestr("OEBPS/images/cover.png", COVER_PNG)
        zf.writestr("OEBPS/images/pic.png", PNG_1PX)
    return path


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample_book.epub"
    print(f"Sample book written to {out}")
