"""Tests for the EPUB parser."""
import zipfile

import pytest

from epub_reader import Epub, EpubError


class TestParsing:
    def test_metadata(self, epub_path):
        book = Epub(epub_path)
        assert book.title == "Test Book"
        assert book.author == "Test Author"

    def test_chapters_from_nav(self, epub_path):
        book = Epub(epub_path)
        assert [c.title for c in book.chapters] == ["One", "Two"]
        assert [c.href for c in book.chapters] == ["ch1.xhtml", "ch2.xhtml"]

    def test_chapters_from_ncx(self, epub_factory):
        book = Epub(epub_factory(with_nav=False, with_ncx=True))
        assert [c.title for c in book.chapters] == ["One", "Two"]

    def test_no_toc_falls_back_to_spine(self, epub_factory):
        book = Epub(epub_factory(with_nav=False))
        assert len(book.chapters) == 2
        assert book.chapters[0].href == "ch1.xhtml"
        assert "Chapter" in book.chapters[0].title

    def test_nav_entries_not_in_spine_are_dropped(self, epub_factory):
        # nav.xhtml itself is in the manifest but must not become a chapter.
        book = Epub(epub_factory())
        assert all(c.href not in ("nav.xhtml", "toc.ncx") for c in book.chapters)

    def test_explicit_cover(self, epub_path):
        book = Epub(epub_path)
        assert book.cover_href == "images/cover.png"

    def test_cover_fallback_first_image_in_spine(self, epub_factory):
        book = Epub(epub_factory(cover_meta=False))
        assert book.cover_href == "images/img1.png"

    def test_cover_data_uri(self, epub_path):
        book = Epub(epub_path)
        uri = book.get_cover_data_uri()
        assert uri and uri.startswith("data:image/png;base64,")


class TestChapterContent:
    def test_images_inlined(self, epub_path):
        ch = Epub(epub_path).get_chapter(0)
        assert "data:image/png;base64," in ch["html"]
        assert 'src="images/' not in ch["html"]

    def test_stylesheet_inlined(self, epub_path):
        book = Epub(epub_path)
        ch = book.get_chapter(0)
        assert any("body { color: #111; }" in s for s in ch["styles"])
        assert "rel=\"stylesheet\"" not in ch["html"] and "rel='stylesheet'" not in ch["html"]

    def test_stylesheet_missing_file_is_ignored(self, epub_factory):
        # ch1 links a stylesheet that does not exist in the package
        book = Epub(epub_factory(with_css=False))
        ch = book.get_chapter(0)  # must not raise
        assert ch["styles"] == []
        assert "First chapter text." in ch["html"]

    def test_links_neutralized(self, epub_path):
        ch = Epub(epub_path).get_chapter(0)
        assert 'href="ch2.xhtml"' not in ch["html"]
        assert "data-orig-href" in ch["html"]

    def test_body_extracted(self, epub_path):
        ch = Epub(epub_path).get_chapter(0)
        assert "<body" not in ch["html"] and "<head" not in ch["html"]
        assert "First chapter text." in ch["html"]

    def test_nested_layout_with_dotdot_paths(self, tmp_path):
        # common real-world layout: chapters in a subfolder, assets one level up
        from epub_reader.sample import build_sample_book
        path = str(tmp_path / "nested.epub")
        build_sample_book(path)
        book = Epub(path)
        ch = book.get_chapter(0)
        assert "data:image/png;base64," in ch["html"]
        assert any("line-height: 1.6" in s for s in ch["styles"])
        assert book.get_cover_data_uri() is not None

    def test_text_length(self, epub_path):
        book = Epub(epub_path)
        assert book.text_length(0) > 5
        assert book.text_length(1) > 5


class TestErrors:
    def test_missing_file(self, tmp_path):
        with pytest.raises(EpubError):
            Epub(str(tmp_path / "nope.epub"))

    def test_not_a_zip(self, tmp_path):
        p = tmp_path / "fake.epub"
        p.write_bytes(b"this is not a zip file")
        with pytest.raises(EpubError):
            Epub(str(p))

    def test_zip_without_container(self, tmp_path):
        p = tmp_path / "empty.epub"
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("readme.txt", "hi")
        with pytest.raises(EpubError):
            Epub(str(p))

    def test_empty_spine_falls_back_to_manifest(self, epub_factory):
        # invalid package, but the manifest still lists the documents -> rescue
        book = Epub(epub_factory(empty_spine=True))
        assert [c.href for c in book.chapters] == ["ch1.xhtml", "ch2.xhtml"]

    def test_package_without_documents_raises(self, tmp_path):
        container = ('<?xml version="1.0"?>'
                    '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                    '<rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/>'
                    '</rootfiles></container>')
        opf = ('<?xml version="1.0"?>'
               '<package xmlns="http://www.idpf.org/2007/opf">'
               '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
               '<dc:title>Empty</dc:title></metadata>'
               '<manifest/><spine/></package>')
        p = str(tmp_path / "nodocs.epub")
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("META-INF/container.xml", container)
            zf.writestr("content.opf", opf)
        with pytest.raises(EpubError):
            Epub(p)

    def test_index_out_of_range(self, epub_path):
        book = Epub(epub_path)
        with pytest.raises(IndexError):
            book.get_chapter(99)
        with pytest.raises(IndexError):
            book.get_chapter(-1)
