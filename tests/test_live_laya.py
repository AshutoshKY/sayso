import unittest

from opener.catalog import APPS, defaults_for, installed
from opener.client import predict
from opener.dockerutil import health_ok
from opener.loop import handle_utterance


@unittest.skipUnless(health_ok(), "laya-upstream is not up on :8001")
class LiveLayaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = installed()
        cls.defaults = defaults_for(cls.catalog)

    def _handle(self, text):
        return handle_utterance(
            text,
            self.catalog,
            self.defaults,
            lambda uttered, cat: predict(uttered, cat),
        )

    def test_named_app_goes_through_laya(self):
        d = self._handle("open notes")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.app, "notes")
        self.assertEqual(d.reason, "laya")

    def test_jot_something_down_is_notes(self):
        d = self._handle("jot something down")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.app, "notes")
        self.assertEqual(d.reason, "laya")

    def test_remind_me_later_is_reminders(self):
        d = self._handle("remind me later")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.app, "reminders")
        self.assertEqual(d.reason, "laya")

    def test_where_is_that_file_is_finder(self):
        d = self._handle("where is that file")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.app, "finder")
        self.assertEqual(d.reason, "laya")

    def test_video_call_is_facetime(self):
        d = self._handle("take a video call")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.app, "facetime")
        self.assertEqual(d.reason, "laya")

    def test_hello_does_not_open_anything(self):
        d = self._handle("hello there")
        self.assertNotEqual(d.action, "open")
        self.assertIsNone(d.app)

    def test_unknown_app_does_not_open(self):
        d = self._handle("open slack")
        self.assertNotEqual(d.action, "open")
        self.assertIsNone(d.app)

    def test_open_vs_code_is_vscode(self):
        if "vscode" not in self.catalog:
            self.skipTest("vscode not installed")
        d = self._handle("open vs code")
        self.assertEqual((d.action, d.app, d.reason), ("open", "vscode", "laya"))

    def test_open_hermes_is_hermes(self):
        if "hermes" not in self.catalog:
            self.skipTest("hermes not installed")
        d = self._handle("open hermes")
        self.assertEqual((d.action, d.app, d.reason), ("open", "hermes", "laya"))

    def test_open_her_mess_is_hermes(self):
        if "hermes" not in self.catalog:
            self.skipTest("hermes not installed")
        d = self._handle("open her mess")
        self.assertEqual((d.action, d.app, d.reason), ("open", "hermes", "laya"))

    def test_open_cloudflare_is_warp(self):
        if "cloudflarewarp" not in self.catalog:
            self.skipTest("Cloudflare WARP not installed")
        d = self._handle("open cloudflare")
        self.assertEqual((d.action, d.app, d.reason), ("open", "cloudflarewarp", "laya"))

    def test_open_cloud_flare_is_warp(self):
        if "cloudflarewarp" not in self.catalog:
            self.skipTest("Cloudflare WARP not installed")
        d = self._handle("open cloud flare")
        self.assertEqual((d.action, d.app, d.reason), ("open", "cloudflarewarp", "laya"))

    def test_open_text_editor_is_textedit(self):
        if "textedit" not in self.catalog:
            self.skipTest("TextEdit not installed")
        d = self._handle("open text editor")
        self.assertEqual((d.action, d.app, d.reason), ("open", "textedit", "laya"))

    def test_open_apple_tv_is_tv(self):
        if "tv" not in self.catalog:
            self.skipTest("TV not installed")
        d = self._handle("open apple tv")
        self.assertEqual((d.action, d.app, d.reason), ("open", "tv", "laya"))

    def test_open_podcast_is_podcasts(self):
        if "podcasts" not in self.catalog:
            self.skipTest("Podcasts not installed")
        d = self._handle("open podcast")
        self.assertEqual((d.action, d.app, d.reason), ("open", "podcasts", "laya"))

    def test_open_gear_club_is_game(self):
        if "gearclubstradale" not in self.catalog:
            self.skipTest("Gear Club Stradale not installed")
        d = self._handle("open gear club stradale")
        self.assertEqual((d.action, d.app, d.reason), ("open", "gearclubstradale", "laya"))

    def test_open_notes_and_safari(self):
        d = self._handle("open notes and safari")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["notes", "safari"])

    def test_open_podcast_and_notes(self):
        if "podcasts" not in self.catalog:
            self.skipTest("Podcasts not installed")
        d = self._handle("open podcast and notes")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["podcasts", "notes"])

    def test_open_calculator_antigravity_and_notes(self):
        needed = ("calculator", "antigravity", "notes")
        missing = [name for name in needed if name not in self.catalog]
        if missing:
            self.skipTest("%s not installed" % ", ".join(missing))
        d = self._handle("open calculator, antigravity and notes")
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["calculator", "antigravity", "notes"])

    def test_open_anti_gravity(self):
        if "antigravity" not in self.catalog:
            self.skipTest("Antigravity not installed")
        d = self._handle("open anti gravity")
        self.assertEqual((d.action, d.app, d.reason), ("open", "antigravity", "laya"))

    def test_open_arc_browser_is_arc(self):
        if "arc" not in self.catalog:
            self.skipTest("arc not installed")
        d = self._handle("open arc browser")
        self.assertEqual((d.action, d.app, d.reason), ("open", "arc", "laya"))

    def test_ark_browser_is_arc(self):
        if "arc" not in self.catalog:
            self.skipTest("arc not installed")
        d = self._handle("ark browser")
        self.assertEqual((d.action, d.app, d.reason), ("open", "arc", "laya"))

    def test_art_browser_is_arc(self):
        if "arc" not in self.catalog:
            self.skipTest("arc not installed")
        d = self._handle("art browser")
        self.assertEqual((d.action, d.app, d.reason), ("open", "arc", "laya"))

    def test_close_notes_when_running(self):
        d = handle_utterance(
            "close notes",
            self.catalog,
            self.defaults,
            lambda uttered, cat: predict(uttered, cat),
            running={"notes"},
        )
        self.assertEqual((d.action, d.app, d.reason), ("close", "notes", "laya"))

    def test_close_notes_when_not_running_asks_to_open(self):
        d = handle_utterance(
            "close notes",
            self.catalog,
            self.defaults,
            lambda uttered, cat: predict(uttered, cat),
            running=set(),
        )
        self.assertEqual((d.action, d.app, d.reason), ("confirm", "notes", "not-running"))

    def test_quit_safari_when_running(self):
        d = handle_utterance(
            "quit safari",
            self.catalog,
            self.defaults,
            lambda uttered, cat: predict(uttered, cat),
            running={"safari"},
        )
        self.assertEqual((d.action, d.app), ("quit", "safari"))

    def test_open_google_chrome_is_still_the_app(self):
        if "chrome" not in self.catalog:
            self.skipTest("Chrome not installed")
        d = self._handle("open google chrome")
        self.assertEqual((d.action, d.app), ("open", "chrome"))

    def test_open_youtube_in_brave_is_url(self):
        if "brave" not in self.catalog:
            self.skipTest("Brave not installed")
        d = self._handle("open youtube in brave")
        self.assertEqual(d.action, "open_url")
        self.assertEqual(d.app, "brave")
        self.assertEqual(d.url, "https://www.youtube.com")

    def test_open_youtube_dot_com_in_safari_is_url(self):
        if "safari" not in self.catalog:
            self.skipTest("Safari not installed")
        d = self._handle("open youtube.com in safari")
        self.assertEqual((d.action, d.app, d.url), ("open_url", "safari", "https://www.youtube.com"))


if __name__ == "__main__":
    unittest.main()
