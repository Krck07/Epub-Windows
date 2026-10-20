"""Tests for library management (add / remove / series)."""
import os

import pytest

from epub_reader import EpubError, Library, Store


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path))


@pytest.fixture
def library(store):
    return Library(store)


class TestAddBook:
    def test_add_copies_file_and_registers(self, library, epub_path, tmp_path):
        entry = library.add_book(epub_path)
        assert entry["title"] == "Test Book"
        assert entry["author"] == "Test Author"
        dest = os.path.join(library.store.library_dir, entry["relpath"])
        assert os.path.isfile(dest)
        assert os.path.abspath(dest) != os.path.abspath(epub_path)  # really copied
        # original untouched
        assert os.path.isfile(epub_path)

    def test_add_missing_file_raises(self, library, tmp_path):
        with pytest.raises(EpubError):
            library.add_book(str(tmp_path / "missing.epub"))

    def test_add_invalid_file_raises(self, library, tmp_path):
        bad = tmp_path / "bad.epub"
        bad.write_bytes(b"no zip here")
        with pytest.raises(EpubError):
            library.add_book(str(bad))
        assert library.store.library_entries() == []  # nothing registered

    def test_add_twice_creates_two_books(self, library, epub_path):
        e1 = library.add_book(epub_path)
        e2 = library.add_book(epub_path)
        assert e1["id"] != e2["id"]
        assert e1["relpath"] != e2["relpath"]
        assert len(library.store.library_entries()) == 2

    def test_add_with_series_and_volume(self, library, epub_path):
        entry = library.add_book(epub_path, series="Saga", volume=2)
        assert entry["series"] == "Saga"
        assert entry["volume"] == 2

    def test_progress_initialized_on_add(self, library, epub_path):
        entry = library.add_book(epub_path)
        p = library.store.get_progress(entry["id"])
        assert p["chapter"] == 0


class TestRemoveBook:
    def test_remove_deletes_file_and_state(self, library, epub_path):
        entry = library.add_book(epub_path)
        library.store.save_progress(entry["id"], 2, 0.5)
        dest = os.path.join(library.store.library_dir, entry["relpath"])

        library.remove_book(entry["id"])

        assert library.store.find_entry(entry["id"]) is None
        assert not os.path.exists(dest)
        assert library.store.get_progress(entry["id"]) == {}

    def test_remove_missing_is_noop(self, library):
        library.remove_book("does-not-exist")  # must not raise

    def test_remove_only_touches_that_book(self, library, epub_path):
        e1 = library.add_book(epub_path)
        e2 = library.add_book(epub_path)
        library.remove_book(e1["id"])
        assert library.store.find_entry(e2["id"]) is not None
        assert os.path.isfile(os.path.join(library.store.library_dir, e2["relpath"]))


class TestSeries:
    def test_set_series(self, library, epub_path):
        entry = library.add_book(epub_path)
        out = library.set_series(entry["id"], "My Series", 3)
        assert out["series"] == "My Series"
        assert out["volume"] == 3
        # persisted for a "restart"
        again = Library(Store(library.store.data_dir))
        assert again.store.find_entry(entry["id"])["series"] == "My Series"

    def test_set_series_unknown_book(self, library):
        assert library.set_series("nope", "X") is None
