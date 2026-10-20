"""Tests for settings + progress persistence."""
from epub_reader import DEFAULT_SETTINGS, Store


class TestSettings:
    def test_defaults_for_new_store(self, tmp_path):
        s = Store(str(tmp_path))
        assert s.get_settings() == DEFAULT_SETTINGS

    def test_update_valid(self, tmp_path):
        s = Store(str(tmp_path))
        out = s.update_settings({"theme": "light", "font_size": 24, "para_spacing": 2.0})
        assert out["theme"] == "light"
        assert out["font_size"] == 24
        assert out["para_spacing"] == 2.0

    def test_invalid_values_rejected(self, tmp_path):
        s = Store(str(tmp_path))
        out = s.update_settings({
            "theme": "neon",          # not allowed
            "font_size": 999,         # out of range
            "font_size_x": 5,         # unknown key
            "para_spacing": "big",    # not a number
        })
        assert out == DEFAULT_SETTINGS

    def test_settings_survive_restart(self, tmp_path):
        s1 = Store(str(tmp_path))
        s1.update_settings({"theme": "light", "font_size": 22})
        s2 = Store(str(tmp_path))  # fresh instance = simulated app restart
        assert s2.get_settings()["theme"] == "light"
        assert s2.get_settings()["font_size"] == 22

    def test_corrupt_settings_recover_to_defaults(self, tmp_path):
        (tmp_path / "settings.json").write_text("{{{ not json", encoding="utf-8")
        s = Store(str(tmp_path))
        assert s.get_settings() == DEFAULT_SETTINGS

    def test_partial_custom_settings_merged_with_defaults(self, tmp_path):
        (tmp_path / "settings.json").write_text('{"font_size": 30}', encoding="utf-8")
        s = Store(str(tmp_path))
        got = s.get_settings()
        assert got["font_size"] == 30
        assert got["theme"] == DEFAULT_SETTINGS["theme"]


class TestProgress:
    def test_save_and_restore(self, tmp_path):
        s = Store(str(tmp_path))
        s.save_progress("b1", 3, 0.42, "Chapter Four")
        s2 = Store(str(tmp_path))
        p = s2.get_progress("b1")
        assert p["chapter"] == 3
        assert abs(p["pct"] - 0.42) < 1e-9
        assert p["title"] == "Chapter Four"

    def test_values_clamped(self, tmp_path):
        s = Store(str(tmp_path))
        assert s.save_progress("b1", -5, 5.0)["chapter"] == 0
        assert s.save_progress("b1", 5, -1.0)["pct"] == 0.0
        assert s.save_progress("b1", 5, 7)["pct"] == 1.0

    def test_garbage_input_ignored(self, tmp_path):
        s = Store(str(tmp_path))
        before = s.get_progress("b1")
        assert s.save_progress("b1", "abc", "xyz") == before
        assert s.get_progress("b1") == {}

    def test_all_progress_map(self, tmp_path):
        s = Store(str(tmp_path))
        s.save_progress("b1", 0, 0.1)
        s.save_progress("b2", 1, 0.2)
        got = Store(str(tmp_path)).all_progress()
        assert set(got) == {"b1", "b2"}

    def test_missing_book_returns_empty(self, tmp_path):
        assert Store(str(tmp_path)).get_progress("nope") == {}

    def test_corrupt_progress_recovered(self, tmp_path):
        (tmp_path / "progress.json").write_text("[1,2,3", encoding="utf-8")
        s = Store(str(tmp_path))
        assert s.all_progress() == {}
        s.save_progress("b1", 1, 0.5)  # still writable afterwards
        assert Store(str(tmp_path)).get_progress("b1")["chapter"] == 1

    def test_clear_progress(self, tmp_path):
        s = Store(str(tmp_path))
        s.save_progress("b1", 1, 0.5)
        s.clear_progress("b1")
        assert s.get_progress("b1") == {}
