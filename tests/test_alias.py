import unittest

from opener.alias import resolve_alias


CATALOG = {
    "safari": {"aliases": ["safari"]},
    "chrome": {"aliases": ["chrome", "google chrome"]},
    "spotify": {"aliases": ["spotify"]},
    "mail": {"aliases": ["mail", "email", "e-mail"]},
    "brave": {"aliases": ["brave"]},
    "vscode": {"aliases": ["vscode", "vs code", "visual studio code"]},
}


class ResolveAliasTests(unittest.TestCase):
    def test_named_app_in_open_phrase(self):
        self.assertEqual(resolve_alias("open safari", CATALOG), "safari")

    def test_longest_alias_wins_over_shorter_overlap(self):
        self.assertEqual(resolve_alias("open google chrome", CATALOG), "chrome")

    def test_product_name_inside_a_sentence(self):
        self.assertEqual(resolve_alias("play some music on spotify", CATALOG), "spotify")

    def test_synonym_maps_to_app(self):
        self.assertEqual(resolve_alias("I need to send an email", CATALOG), "mail")

    def test_no_product_name_returns_none(self):
        self.assertIsNone(resolve_alias("hey how are you", CATALOG))

    def test_generic_browser_uses_system_default(self):
        self.assertEqual(
            resolve_alias(
                "open the browser",
                CATALOG,
                defaults={"browser": "brave"},
            ),
            "brave",
        )

    def test_generic_browser_ignored_when_a_browser_is_named(self):
        self.assertEqual(
            resolve_alias(
                "open safari in the browser",
                CATALOG,
                defaults={"browser": "brave"},
            ),
            "safari",
        )

    def test_generic_music_uses_default(self):
        self.assertEqual(
            resolve_alias(
                "play some music",
                CATALOG,
                defaults={"music": "spotify"},
            ),
            "spotify",
        )

    def test_named_spotify_beats_generic_music(self):
        self.assertEqual(
            resolve_alias(
                "play some music on spotify",
                CATALOG,
                defaults={"music": "safari"},
            ),
            "spotify",
        )

    def test_spaced_spoken_name_matches_compact_id(self):
        catalog = {
            "antigravity": {"aliases": ["antigravity"]},
        }
        self.assertEqual(resolve_alias("open anti gravity", catalog), "antigravity")
        self.assertEqual(resolve_alias("antigravity", catalog), "antigravity")

    def test_trailing_app_word_does_not_steal_named_app(self):
        from opener.alias import spoken_key

        catalog = {
            "antigravity": {"aliases": ["antigravity"]},
            "apps": {"aliases": ["apps", "app"]},
        }
        self.assertEqual(spoken_key("open anti gravity app"), "antigravity")
        self.assertEqual(spoken_key("open antigravity app"), "antigravity")
        self.assertEqual(
            resolve_alias("open anti gravity app", catalog),
            "antigravity",
        )
        self.assertEqual(resolve_alias("open apps", catalog), "apps")

    def test_close_quit_kill_prefixes_strip_like_open(self):
        from opener.alias import spoken_key

        self.assertEqual(spoken_key("close brave"), "brave")
        self.assertEqual(spoken_key("quit brave"), "brave")
        self.assertEqual(spoken_key("kill brave"), "brave")
        self.assertEqual(spoken_key("force quit brave"), "brave")
        self.assertEqual(spoken_key("close brave app"), "brave")
        self.assertEqual(resolve_alias("close brave", CATALOG), "brave")
        self.assertEqual(resolve_alias("quit google chrome", CATALOG), "chrome")

    def test_open_youtube_in_brave_strips_site_for_app_key(self):
        from opener.alias import spoken_key

        self.assertEqual(spoken_key("open youtube in brave"), "brave")
        self.assertEqual(spoken_key("open youtube.com in safari"), "safari")
        self.assertEqual(spoken_key("youtube in brave"), "brave")
        self.assertEqual(resolve_alias("open youtube in brave", CATALOG), "brave")
        self.assertEqual(resolve_alias("open github.com in safari", CATALOG), "safari")

    def test_open_clipboard_is_not_an_app(self):
        from opener.alias import spoken_key

        self.assertEqual(spoken_key("open clipboard"), "")
        self.assertIsNone(resolve_alias("open clipboard", CATALOG))

    def test_cloudflare_speech_forms_map_to_warp(self):
        catalog = {
            "cloudflarewarp": {
                "aliases": [
                    "cloudflare warp",
                    "cloudflarewarp",
                    "cloudflare",
                    "cloud flare",
                    "cloud flare warp",
                ]
            },
            "notes": {"aliases": ["notes"]},
        }
        self.assertEqual(resolve_alias("open cloudflare", catalog), "cloudflarewarp")
        self.assertEqual(resolve_alias("open cloud flare", catalog), "cloudflarewarp")
        self.assertEqual(
            resolve_alias("open cloud flare warp", catalog),
            "cloudflarewarp",
        )

    def test_hermes_asr_confusions_map_to_hermes(self):
        catalog = {
            "hermes": {
                "aliases": [
                    "hermes",
                    "her mes",
                    "her mess",
                    "hermits",
                    "hurmez",
                ]
            }
        }
        self.assertEqual(resolve_alias("open hermes", catalog), "hermes")
        self.assertEqual(resolve_alias("open her mess", catalog), "hermes")
        self.assertEqual(resolve_alias("open hermits", catalog), "hermes")

    def test_prefer_catalog_transcript_picks_named_hypothesis(self):
        from opener.alias import prefer_catalog_transcript

        catalog = {
            "hermes": {"aliases": ["hermes", "her mess", "hermits"]},
            "notes": {"aliases": ["notes"]},
        }
        self.assertEqual(
            prefer_catalog_transcript(
                ["open hermits", "open Hermes", "open notes"],
                catalog,
            ),
            "open Hermes",
        )
        self.assertEqual(
            prefer_catalog_transcript(["open the weather"], catalog),
            "open the weather",
        )


if __name__ == "__main__":
    unittest.main()
