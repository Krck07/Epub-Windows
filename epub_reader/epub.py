"""Minimal EPUB 2/3 parser.

Extracts metadata, table of contents, chapters and the cover image from an
EPUB file (a zip container). No external dependencies; chapters are returned
as self-contained HTML (images inlined as data URIs, linked CSS inlined) so
the front-end can render them without any network or file access.
"""
from __future__ import annotations

import base64
import mimetypes
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html import unescape
from typing import Dict, List, Optional
from urllib.parse import unquote

OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
NCX_NS = "http://www.daisy.org/z3986/2005/ncx/"

NAV_MEDIA_TYPE = "application/vnd.epub+xml"
NCX_MEDIA_TYPE = "application/x-dtbncx+xml"
OPF_MEDIA_TYPE = "application/oebps-package+xml"
IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml", "image/bmp")

_TAG_RE = re.compile(r"<[^>]+>")
_IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_LINK_RE = re.compile(r'<link\b[^>]*rel\s*=\s*["\']stylesheet["\'][^>]*>', re.IGNORECASE)
_HREF_RE = re.compile(r"""href\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_SRC_RE = re.compile(r"""src\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


class EpubError(ValueError):
    """Raised when a file is not a readable EPUB."""


@dataclass
class Chapter:
    title: str
    href: str  # normalized zip-relative path, forward slashes


@dataclass
class Epub:
    path: str
    title: str = "Untitled"
    author: str = ""
    chapters: List[Chapter] = field(default_factory=list)
    cover_href: Optional[str] = None

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)

    def __init__(self, path: str):
        self.path = path
        try:
            zf = zipfile.ZipFile(path)
        except (FileNotFoundError, zipfile.BadZipFile, OSError) as exc:
            raise EpubError(f"Not a readable EPUB file: {path}") from exc
        try:
            with zf:
                self._parse(zf)
        except EpubError:
            raise
        except ET.ParseError as exc:
            raise EpubError("EPUB metadata is malformed") from exc
        except Exception as exc:  # defensive: never crash the app on weird files
            raise EpubError(f"Could not parse EPUB ({exc})") from exc

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #
    def _parse(self, zf: zipfile.ZipFile) -> None:
        opf_path = self._find_opf(zf)
        opf_dir = posixpath.dirname(opf_path)

        opf = ET.fromstring(zf.read(opf_path))
        self._read_metadata(opf)

        manifest = self._read_manifest(opf)
        spine = self._read_spine(opf, manifest)
        if not spine:
            raise EpubError("EPUB has an empty spine")
        spine = [_resolve(opf_dir, h) for h in spine]

        toc = self._read_toc(zf, opf_dir, manifest)
        self.chapters = self._build_chapters(toc, spine)
        if not self.chapters:
            raise EpubError("EPUB contains no chapters")

        self.cover_href = self._find_cover(zf, opf_path, opf_dir, manifest, spine)

    @staticmethod
    def _find_opf(zf: zipfile.ZipFile) -> str:
        names = set(zf.namelist())
        candidate = None
        for n in sorted(names, key=lambda s: (s.lower() != "meta-inf/container.xml", s)):
            if n.lower() == "meta-inf/container.xml" or n.lower().endswith("/container.xml"):
                candidate = n
                break
        if candidate is None:
            raise EpubError("Not a valid EPUB (missing META-INF/container.xml)")
        try:
            container = ET.fromstring(zf.read(candidate))
        except ET.ParseError as exc:
            raise EpubError("Malformed container.xml") from exc
        # container.xml elements are namespaced; match on the local tag name
        rootfiles = [e for e in container.iter() if e.tag.rsplit("}", 1)[-1] == "rootfile"]
        for rf in rootfiles:
            full = rf.get("full-path")
            media = (rf.get("media-type") or "").lower()
            if full and (OPF_MEDIA_TYPE in media or full.lower().endswith(".opf")):
                return _normpath(full)
        for rf in rootfiles:
            if rf.get("full-path"):
                return _normpath(rf.get("full-path"))
        raise EpubError("No package document (OPF) listed in container.xml")

    def _read_metadata(self, opf: ET.Element) -> None:
        title_el = opf.find(f"{{{OPF_NS}}}metadata/{{{DC_NS}}}title")
        if title_el is not None and (title_el.text or "").strip():
            self.title = (title_el.text or "").strip()
        creator_el = opf.find(f"{{{OPF_NS}}}metadata/{{{DC_NS}}}creator")
        if creator_el is not None and (creator_el.text or "").strip():
            self.author = (creator_el.text or "").strip()

    @staticmethod
    def _read_manifest(opf: ET.Element) -> Dict[str, Dict[str, str]]:
        manifest: Dict[str, Dict[str, str]] = {}
        m_el = opf.find(f"{{{OPF_NS}}}manifest")
        if m_el is None:
            return manifest
        for item in m_el.findall(f"{{{OPF_NS}}}item"):
            href = item.get("href")
            if not href:
                continue
            manifest[_normpath(href)] = {
                "id": item.get("id") or "",
                "media-type": (item.get("media-type") or "").lower(),
            }
        return manifest

    @staticmethod
    def _read_spine(opf: ET.Element, manifest: Dict[str, Dict[str, str]]) -> List[str]:
        spine_el = opf.find(f"{{{OPF_NS}}}spine")
        hrefs: List[str] = []
        if spine_el is not None:
            for itemref in spine_el.findall(f"{{{OPF_NS}}}itemref"):
                href = itemref.get("href")
                if href:
                    hrefs.append(_normpath(href))
        if hrefs:
            return hrefs
        fallback = [h for h, v in manifest.items() if v["media-type"] in ("application/xhtml+xml", "text/html")]
        return sorted(fallback)

    def _read_toc(self, zf, opf_dir: str, manifest: Dict[str, Dict[str, str]]) -> List[Chapter]:
        # EPUB3 nav document.
        nav_href = next((h for h, v in manifest.items() if v["media-type"] == NAV_MEDIA_TYPE), None)
        if nav_href:
            full = _resolve(opf_dir, nav_href)
            try:
                html = zf.read(full).decode("utf-8", errors="replace")
                chapters = self._toc_from_nav_html(html, posixpath.dirname(full))
            except (KeyError, UnicodeDecodeError):
                chapters = []
            if chapters:
                return chapters
        # EPUB2 NCX.
        ncx_href = next((h for h, v in manifest.items() if v["media-type"] == NCX_MEDIA_TYPE), None)
        if ncx_href:
            full = _resolve(opf_dir, ncx_href)
            try:
                chapters = self._toc_from_ncx(zf.read(full), posixpath.dirname(full))
            except (KeyError, ET.ParseError):
                chapters = []
            if chapters:
                return chapters
        return []

    @staticmethod
    def _toc_from_nav_html(html: str, base_dir: str) -> List[Chapter]:
        result: List[Chapter] = []
        toc_match = re.search(
            r'<nav\b[^>]*epub:type\s*=\s*["\']toc["\'][^>]*>(.*?)</nav>',
            html, re.IGNORECASE | re.DOTALL)
        scope = toc_match.group(1) if toc_match else html
        for a_tag, inner in re.findall(r"(<a\b[^>]*>)(.*?)</a>", scope, re.IGNORECASE | re.DOTALL):
            m = _HREF_RE.search(a_tag)
            if not m:
                continue
            href = _strip_fragment(_normpath(unescape(m.group(1))))
            if not href or not _looks_like_doc(href):
                continue
            href = _resolve(base_dir, href)
            title = unescape(_TAG_RE.sub("", inner)).strip() or posixpath.basename(href)
            if not any(c.href == href for c in result):
                result.append(Chapter(title=title, href=href))
        return result

    @staticmethod
    def _toc_from_ncx(data: bytes, base_dir: str) -> List[Chapter]:
        root = ET.fromstring(data)
        result: List[Chapter] = []
        for point in root.iter(f"{{{NCX_NS}}}navPoint"):
            text_el = point.find(f".//{{{NCX_NS}}}text")
            content_el = point.find(f"{{{NCX_NS}}}content")
            src = content_el.get("src") if content_el is not None else None
            if not src:
                continue
            href = _strip_fragment(_normpath(src))
            if not href or not _looks_like_doc(href):
                continue
            href = _resolve(base_dir, href)
            title = (text_el.text or "").strip() if text_el is not None else ""
            title = title or posixpath.basename(href)
            if not any(c.href == href for c in result):
                result.append(Chapter(title=title, href=href))
        return result

    @staticmethod
    def _build_chapters(toc: List[Chapter], spine: List[str]) -> List[Chapter]:
        chapters: List[Chapter] = []
        seen = set()
        for ch in toc:
            if ch.href in set(spine) and ch.href not in seen:
                seen.add(ch.href)
                chapters.append(ch)
        for href in spine:  # spine documents missing from the TOC
            if href not in seen:
                seen.add(href)
                chapters.append(Chapter(title=f"Chapter {len(chapters) + 1}", href=href))
        return chapters

    # ------------------------------------------------------------------ #
    # Cover
    # ------------------------------------------------------------------ #
    def _find_cover(self, zf, opf_path: str, opf_dir: str, manifest: Dict[str, Dict[str, str]], spine: List[str]) -> Optional[str]:
        # 1) Explicit cover id in OPF metadata.
        try:
            opf = ET.fromstring(zf.read(opf_path))
        except (KeyError, ET.ParseError):
            opf = None
        if opf is not None:
            meta_el = opf.find(f"{{{OPF_NS}}}metadata")
            if meta_el is not None:
                for meta in meta_el:
                    if meta.tag == f"{{{OPF_NS}}}meta" and meta.get("name") == "cover":
                        cover_id = meta.get("content")
                        if cover_id:
                            for href, info in manifest.items():
                                if info["id"] == cover_id:
                                    full = _resolve(opf_dir, href)
                                    if info["media-type"] in IMAGE_TYPES:
                                        return full
                                    img = self._first_img_href(zf, full)
                                    if img:
                                        return _resolve(posixpath.dirname(full), img)
        # 2) First image referenced by spine documents, in reading order.
        for href in spine:
            img = self._first_img_href(zf, href)
            if img:
                return _resolve(posixpath.dirname(href), img)
        # 3) First image item in the manifest, preferring spine order.
        for href in spine:
            info = manifest.get(href)
            if info and info["media-type"] in IMAGE_TYPES:
                return _resolve(opf_dir, href)
        for href, info in manifest.items():
            if info["media-type"] in IMAGE_TYPES:
                return _resolve(opf_dir, href)
        return None

    def _first_img_href(self, zf, doc_full_path: str) -> Optional[str]:
        try:
            html = zf.read(doc_full_path).decode("utf-8", errors="replace")
        except (KeyError, UnicodeDecodeError):
            return None
        m = _IMG_TAG_RE.search(html)
        if not m:
            return None
        sm = _SRC_RE.search(m.group(0))
        return sm.group(1) if sm else None

    # ------------------------------------------------------------------ #
    # Content
    # ------------------------------------------------------------------ #
    def get_chapter(self, index: int) -> dict:
        if index < 0 or index >= len(self.chapters):
            raise IndexError("Chapter index out of range")
        chapter = self.chapters[index]
        with zipfile.ZipFile(self.path) as zf:
            data = self._read_name(zf, chapter.href)
            html, styles = self._make_self_contained(zf, chapter.href, data)
        return {"index": index, "title": chapter.title, "html": html, "styles": styles}

    @staticmethod
    def _read_name(zf, name: str) -> bytes:
        try:
            return zf.read(name)
        except KeyError:
            lowered = name.lower()
            for n in zf.namelist():
                if n.lower() == lowered:
                    return zf.read(n)
            raise

    def _make_self_contained(self, zf, doc_path: str, data: bytes):
        html = data.decode("utf-8", errors="replace")
        styles: List[str] = []

        def _inline_link(m):
            tag = m.group(0)
            hm = _HREF_RE.search(tag)
            if not hm:
                return tag
            css = self._try_read_css(zf, _resolve(posixpath.dirname(doc_path), hm.group(1)))
            if css:
                styles.append(css)
                return ""
            return tag

        html = _LINK_RE.sub(_inline_link, html)

        def _inline_img(m):
            tag = m.group(0)
            sm = _SRC_RE.search(tag)
            if not sm or sm.group(1).startswith("data:"):
                return tag
            uri = self._try_read_data_uri(zf, _resolve(posixpath.dirname(doc_path), sm.group(1)))
            if uri:
                return tag[: sm.start(1)] + uri + tag[sm.end(1):]
            return tag

        html = _IMG_TAG_RE.sub(_inline_img, html)

        # Neutralize hyperlinks so taps never navigate out of the reader.
        html = re.sub(r"""\s+href\s*=\s*["'][^"']*["']""", " data-orig-href=\"#\"", html, flags=re.IGNORECASE)

        body_m = re.search(r"<body\b[^>]*>(.*)</body>", html, re.IGNORECASE | re.DOTALL)
        if body_m:
            html = body_m.group(1)
        else:
            head_m = re.search(r"</head>", html, re.IGNORECASE)
            if head_m:
                html = html[head_m.end():]
        return html, styles

    def _try_read_css(self, zf, full_path: str) -> Optional[str]:
        try:
            return zf.read(full_path).decode("utf-8", errors="replace")
        except (KeyError, UnicodeDecodeError, OSError):
            return None

    def _try_read_data_uri(self, zf, full_path: str) -> Optional[str]:
        try:
            data = zf.read(full_path)
        except (KeyError, OSError):
            return None
        mime = mimetypes.guess_type(full_path)[0]
        if mime not in IMAGE_TYPES:
            mime = "image/png"
        return "data:%s;base64,%s" % (mime, base64.b64encode(data).decode("ascii"))

    def get_cover_data_uri(self) -> Optional[str]:
        if not self.cover_href:
            return None
        with zipfile.ZipFile(self.path) as zf:
            uri = self._try_read_data_uri(zf, self.cover_href)
        if uri:
            return uri
        return None

    def text_length(self, index: int) -> int:
        """Visible text length of a chapter (for cover-page detection)."""
        try:
            ch = self.get_chapter(index)
        except (EpubError, IndexError):
            return 0
        return len(_TAG_RE.sub("", ch["html"]).strip())


# ---------------------------------------------------------------------- #
# Path helpers (EPUB paths are POSIX-style inside the zip)
# ---------------------------------------------------------------------- #
def _normpath(href: str) -> str:
    href = unquote(href).strip().replace("\\", "/")
    return posixpath.normpath(href).lstrip("/")


def _strip_fragment(href: str) -> str:
    return href.split("#", 1)[0]


def _looks_like_doc(href: str) -> bool:
    return bool(re.search(r"\.(x?html?|xml)$", href, re.IGNORECASE))


def _resolve(base_dir: str, href: str) -> str:
    href = _normpath(href)
    if href.startswith("/"):
        return href[1:]
    if base_dir in (None, "", "."):
        return href
    base = posixpath.normpath(base_dir).strip("/")
    return posixpath.normpath("/".join(p for p in (base, href) if p)).lstrip("/")
