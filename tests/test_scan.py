import unittest

from opener.scan import aliases_for, merge_scanned, scan_apps, slug


class AliasTests(unittest.TestCase):
    def test_textedit_includes_spoken_names(self):
        aliases = aliases_for("TextEdit")
        self.assertIn("textedit", aliases)
        self.assertIn("text edit", aliases)
        self.assertIn("text editor", aliases)

    def test_tv_includes_apple_tv(self):
        aliases = aliases_for("TV")
        self.assertIn("tv", aliases)
        self.assertIn("apple tv", aliases)

    def test_podcasts_includes_singular(self):
        aliases = aliases_for("Podcasts")
        self.assertIn("podcasts", aliases)
        self.assertIn("podcast", aliases)

    def test_gear_club_splits_punctuation(self):
        aliases = aliases_for("Gear.Club-Stradale")
        self.assertIn("gear club stradale", aliases)
        self.assertIn("gear club", aliases)
        self.assertIn("stradale", aliases)

    def test_generic_last_tokens_are_not_aliases(self):
        self.assertNotIn("video", aliases_for("Prime Video"))
        self.assertNotIn("editor", aliases_for("Script Editor"))

    def test_cloudflare_warp_includes_spoken_brand(self):
        aliases = aliases_for("Cloudflare WARP")
        self.assertIn("cloudflare warp", aliases)
        self.assertIn("cloudflare", aliases)
        self.assertIn("cloud flare", aliases)
        self.assertIn("cloud flare warp", aliases)

    def test_hermes_is_not_stripped_to_herme(self):
        aliases = aliases_for("Hermes")
        self.assertIn("hermes", aliases)
        self.assertNotIn("herme", aliases)

    def test_short_first_token_is_not_an_alias(self):
        self.assertNotIn("google", aliases_for("Google Chrome"))
        self.assertNotIn("visual", aliases_for("Visual Studio Code"))

    def test_hermes_includes_asr_confusions(self):
        aliases = aliases_for("Hermes")
        self.assertIn("her mess", aliases)
        self.assertIn("hermits", aliases)

    def test_speech_phrases_cap_and_include_brands(self):
        from opener.scan import speech_phrases

        catalog = {
            "hermes": {
                "say": "Hermes",
                "bundle": "com.nousresearch.hermes",
                "aliases": ["hermes", "her mess"],
            },
            "cloudflarewarp": {
                "say": "Cloudflare WARP",
                "bundle": "com.cloudflare.1dot1dot1dot1.macos",
                "aliases": ["cloudflare", "cloud flare"],
            },
        }
        phrases = speech_phrases(catalog, limit=8)
        self.assertLessEqual(len(phrases), 8)
        lowered = [item.lower() for item in phrases]
        self.assertIn("hermes", lowered)
        self.assertIn("cloudflare", lowered)

    def test_speech_phrases_keep_unusual_brands_under_cap(self):
        from opener.scan import speech_phrases

        catalog = {
            "notes": {"say": "Notes", "bundle": "com.apple.Notes", "aliases": ["notes"]},
            "hermes": {
                "say": "Hermes",
                "bundle": "com.nousresearch.hermes",
                "aliases": ["hermes", "her mess"],
            },
            "cloudflarewarp": {
                "say": "Cloudflare WARP",
                "bundle": "com.cloudflare.1dot1dot1dot1.macos",
                "aliases": ["cloudflare", "cloud flare"],
            },
        }
        for index in range(80):
            catalog["aaa%s" % index] = {
                "say": "Aaa %s" % index,
                "bundle": "com.aaa.%s" % index,
                "aliases": ["aaa %s" % index, "aaaa %s" % index],
            }
        phrases = speech_phrases(catalog, limit=12)
        lowered = [item.lower() for item in phrases]
        self.assertIn("hermes", lowered)
        self.assertIn("cloudflare", lowered)
        self.assertIn("her mess", lowered)


class ScanAppsTests(unittest.TestCase):
    def test_discovers_apps_from_roots(self):
        tree = {
            "/Applications": ["TextEdit.app", "Ignore.txt", "TV.app"],
        }

        def listdir(path):
            return list(tree.get(path, []))

        def is_dir(path):
            return path.endswith(".app") or path in tree

        got = scan_apps(roots=["/Applications"], listdir=listdir, is_dir=is_dir)
        self.assertIn("textedit", got)
        self.assertIn("tv", got)
        self.assertEqual(got["textedit"]["paths"], ["/Applications/TextEdit.app"])
        self.assertIn("text editor", got["textedit"]["aliases"])
        self.assertIn("apple tv", got["tv"]["aliases"])


class MergeScannedTests(unittest.TestCase):
    def test_keeps_curated_and_adds_unknown(self):
        curated = {
            "notes": {
                "open": "Notes",
                "say": "Notes",
                "bundle": "com.apple.Notes",
                "paths": ["/System/Applications/Notes.app"],
                "aliases": ["notes"],
            }
        }
        scanned = {
            "textedit": {
                "open": "TextEdit",
                "say": "TextEdit",
                "paths": ["/System/Applications/TextEdit.app"],
                "aliases": ["textedit", "text editor"],
                "criteria": "the words textedit or text editor",
            }
        }
        got = merge_scanned(curated, scanned)
        self.assertIn("notes", got)
        self.assertIn("textedit", got)
        self.assertEqual(got["notes"]["aliases"], ["notes"])


class QuestionsUseScannedTests(unittest.TestCase):
    def test_text_editor_prompt_includes_textedit_not_whole_catalog(self):
        from opener.client import questions_for

        catalog = {
            "notes": {"aliases": ["notes"], "criteria": "notes"},
            "safari": {"aliases": ["safari"], "criteria": "safari"},
            "textedit": {
                "aliases": ["textedit", "text editor"],
                "criteria": "textedit, text editor",
            },
            "tv": {"aliases": ["tv", "apple tv"], "criteria": "apple tv, tv"},
            "chess": {"aliases": ["chess"], "criteria": "chess"},
        }
        criteria = questions_for("open text editor", catalog)["app"]["criteria"]
        self.assertIn("textedit", criteria)
        self.assertNotIn("tv", criteria)
        self.assertNotIn("chess", criteria)

    def test_apple_tv_prompt_includes_tv(self):
        from opener.client import questions_for

        catalog = {
            "tv": {"aliases": ["tv", "apple tv"], "criteria": "apple tv"},
        }
        criteria = questions_for("open apple tv", catalog)["app"]["criteria"]
        self.assertIn("tv", criteria)

    def test_podcast_prompt_includes_podcasts(self):
        from opener.client import questions_for

        catalog = {
            "podcasts": {
                "aliases": ["podcasts", "podcast", "apple podcasts"],
                "criteria": "podcasts",
            }
        }
        criteria = questions_for("open podcast", catalog)["app"]["criteria"]
        self.assertIn("podcasts", criteria)

    def test_gear_club_prompt_includes_game(self):
        from opener.client import questions_for

        catalog = {
            "gearclubstradale": {
                "aliases": ["gear club stradale", "gear club", "stradale"],
                "criteria": "gear club",
            }
        }
        criteria = questions_for("open gear club stradale", catalog)["app"]["criteria"]
        self.assertIn("gearclubstradale", criteria)


if __name__ == "__main__":
    unittest.main()
