"""Shared fixtures: builds small, valid EPUB files on the fly."""
import base64
import zipfile

import pytest

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

CONTAINER = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>"""

CSS = "body { color: #111; } p { margin: 0.5em 0; }"

CH1 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>One</title><link rel="stylesheet" href="style.css"/></head>
<body><h1>One</h1><p>First chapter text.</p><img src="images/img1.png"/><a href="ch2.xhtml">next</a></body>
</html>"""

CH2 = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Two</title></head>
<body><h1>Two</h1><p>Second chapter text.</p><p>More text.</p></body>
</html>"""

NAV = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>toc</title></head>
<body><nav epub:type="toc" xmlns:epub="http://www.idpf.org/2007/ops">
<ol><li><a href="ch1.xhtml">One</a></li><li><a href="ch2.xhtml">Two</a></li></ol>
</nav></body></html>"""

NCX = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/">
<head><meta name="dtb:uid" content="t1"/></head>
<docTitle><text>Test Book</text></docTitle>
<navMap>
  <navPoint id="n1" playOrder="1"><navLabel><text>One</text></navLabel><content src="ch1.xhtml"/></navPoint>
  <navPoint id="n2" playOrder="2"><navLabel><text>Two</text></navLabel><content src="ch2.xhtml"/></navPoint>
</navMap></ncx>"""


def build_epub(
    path,
    *,
    title="Test Book",
    author="Test Author",
    with_nav=True,
    with_ncx=False,
    cover_meta=True,
    empty_spine=False,
    with_css=True,
):
    """Write a minimal but valid EPUB and return its path."""
    opf_parts = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">',
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
        f"<dc:title>{title}</dc:title>",
        f"<dc:creator>{author}</dc:creator>",
    ]
    if cover_meta:
        opf_parts.append('<meta name="cover" content="cover-item"/>')
    opf_parts.append("</metadata><manifest>")
    opf_parts.append('<item id="ch1" href="ch1.xhtml" media-type="application/xhtml+xml"/>')
    opf_parts.append('<item id="ch2" href="ch2.xhtml" media-type="application/xhtml+xml"/>')
    opf_parts.append('<item id="css" href="style.css" media-type="text/css"/>')
    opf_parts.append('<item id="cover-item" href="images/cover.png" media-type="image/png"/>')
    opf_parts.append('<item id="img1" href="images/img1.png" media-type="image/png"/>')
    if with_nav:
        opf_parts.append('<item id="nav" href="nav.xhtml" media-type="application/vnd.epub+xml"/>')
    if with_ncx:
        opf_parts.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    opf_parts.append("</manifest><spine>")
    if not empty_spine:
        opf_parts.append('<itemref idref="ch1"/><itemref idref="ch2"/>')
    opf_parts.append("</spine></package>")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", CONTAINER)
        zf.writestr("content.opf", "".join(opf_parts))
        zf.writestr("ch1.xhtml", CH1)
        zf.writestr("ch2.xhtml", CH2)
        if with_css:
            zf.writestr("style.css", CSS)
        zf.writestr("images/cover.png", PNG_1PX)
        zf.writestr("images/img1.png", PNG_1PX)
        if with_nav:
            zf.writestr("nav.xhtml", NAV)
        if with_ncx:
            zf.writestr("toc.ncx", NCX)
    return path


@pytest.fixture
def epub_factory(tmp_path):
    counter = {"n": 0}

    def _make(**kwargs):
        counter["n"] += 1
        path = str(tmp_path / f"book{counter['n']}.epub")
        return build_epub(path, **kwargs)

    return _make


@pytest.fixture
def epub_path(epub_factory):
    return epub_factory()
