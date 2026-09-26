import unittest

from opener.catalog import APPS, defaults_for, installed


class InstalledTests(unittest.TestCase):
    def test_keeps_only_paths_that_exist(self):
        apps = {
            "notes": {"paths": ["/nope.app", "/yes/Notes.app"], "open": "Notes"},
            "ghost": {"paths": ["/missing.app"], "open": "Ghost"},
        }
        got = installed(apps, exists=lambda p: p.endswith("Notes.app"))
        self.assertEqual(set(got), {"notes"})
        self.assertEqual(got["notes"]["path"], "/yes/Notes.app")

    def test_real_catalog_finds_notes_and_safari(self):
        got = installed(APPS)
        self.assertIn("notes", got)
        self.assertIn("safari", got)
        self.assertIn("brave", got)

    def test_startup_scan_includes_textedit_and_tv(self):
        got = installed()
        self.assertIn("textedit", got)
        self.assertIn("tv", got)
        self.assertGreater(len(got), 20)


class DefaultsForTests(unittest.TestCase):
    def test_browser_from_handlers(self):
        catalog = {
            "safari": {"bundle": "com.apple.Safari"},
            "brave": {"bundle": "com.brave.Browser"},
        }
        d = defaults_for(
            catalog,
            handlers=[{"scheme": "http", "bundle": "com.brave.Browser"}],
        )
        self.assertEqual(d["browser"], "brave")

    def test_music_prefers_spotify_when_installed(self):
        catalog = {
            "music": {"bundle": "com.apple.Music"},
            "spotify": {"bundle": "com.spotify.client"},
        }
        d = defaults_for(catalog, handlers=[])
        self.assertEqual(d["music"], "spotify")


if __name__ == "__main__":
    unittest.main()
