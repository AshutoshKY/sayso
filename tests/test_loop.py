import unittest

from opener.loop import handle_utterance, newly_named_apps, spoken
from opener.policy import Decision


CATALOG = {
    "safari": {"say": "Safari", "open": "Safari", "aliases": ["safari"]},
    "notes": {"say": "Notes", "open": "Notes", "aliases": ["notes"]},
    "brave": {"say": "Brave", "open": "Brave Browser", "aliases": ["brave"]},
}


def _laya(app, app_p=0.9, intent="launch", intent_p=0.9):
    return {
        "intent": {"choice": intent, "answer_confidence": intent_p},
        "app": {"choice": app, "answer_confidence": app_p},
    }


class HandleUtteranceTests(unittest.TestCase):
    def test_stop_phrase_does_not_call_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            raise AssertionError("Laya should not run on goodbye")

        d = handle_utterance("goodbye", CATALOG, {}, predict)
        self.assertEqual(d.action, "stop")
        self.assertEqual(called, [])

    def test_named_app_calls_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("safari")

        d = handle_utterance("open safari", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app, d.reason), ("open", "safari", "laya"))
        self.assertEqual(called, ["open safari"])

    def test_greeting_calls_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("unspecified", intent="chat")

        d = handle_utterance("hello there", CATALOG, {}, predict)
        self.assertEqual(d.action, "chat")
        self.assertEqual(called, ["hello there"])

    def test_negation_calls_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("chrome", intent="refuse")

        d = handle_utterance("don't open chrome", CATALOG, {}, predict)
        self.assertEqual(d.action, "refuse")
        self.assertEqual(called, ["don't open chrome"])

    def test_generic_browser_calls_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("brave")

        d = handle_utterance(
            "open the browser",
            CATALOG,
            {"browser": "brave"},
            predict,
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "brave", "laya"))
        self.assertEqual(called, ["open the browser"])

    def test_paraphrase_calls_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return {
                "app": {"choice": "notes", "answer_confidence": 0.80},
            }

        d = handle_utterance("jot something down", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app, d.reason), ("open", "notes", "laya"))
        self.assertEqual(called, ["jot something down"])

    def test_uses_laya_choice_not_alias(self):
        def predict(text, catalog):
            return _laya("notes")

        d = handle_utterance("open safari", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app, d.reason), ("open", "notes", "laya"))

    def test_laya_unknown_app_does_not_open(self):
        def predict(text, catalog):
            return _laya("slack", app_p=0.99)

        d = handle_utterance("open slack", CATALOG, {}, predict)
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)

    def test_bare_installed_name_opens_if_laya_unspecified(self):
        catalog = dict(CATALOG)
        catalog["antigravity"] = {"aliases": ["antigravity"], "say": "Antigravity"}

        def predict(text, catalog):
            return _laya("unspecified", app_p=0.24, intent="chat")

        d = handle_utterance("antigravity", catalog, {}, predict)
        self.assertEqual((d.action, d.app), ("open", "antigravity"))
        self.assertEqual(d.reason, "laya")

    def test_trailing_app_word_recovers_installed_id(self):
        from opener.loop import exact_installed_id

        catalog = dict(CATALOG)
        catalog["antigravity"] = {"aliases": ["antigravity"], "say": "Antigravity"}
        self.assertEqual(
            exact_installed_id("open anti gravity app", catalog),
            "antigravity",
        )
        self.assertEqual(
            exact_installed_id("open antigravity app", catalog),
            "antigravity",
        )

    def test_alias_recovers_when_laya_unspecified(self):
        catalog = dict(CATALOG)
        catalog["hermes"] = {
            "aliases": ["hermes", "her mess", "hermits"],
            "say": "Hermes",
        }

        def predict(text, catalog):
            return _laya("unspecified", app_p=0.4, intent="chat")

        d = handle_utterance("open her mess", catalog, {}, predict)
        self.assertEqual((d.action, d.app), ("open", "hermes"))
        self.assertEqual(d.reason, "laya")

    def test_cloudflare_alias_recovers_when_laya_unspecified(self):
        catalog = dict(CATALOG)
        catalog["cloudflarewarp"] = {
            "aliases": ["cloudflare warp", "cloudflare", "cloud flare"],
            "say": "Cloudflare WARP",
        }

        def predict(text, catalog):
            return _laya("unspecified", app_p=0.3, intent="chat")

        d = handle_utterance("open cloudflare", catalog, {}, predict)
        self.assertEqual((d.action, d.app), ("open", "cloudflarewarp"))

    def test_two_named_apps_opens_both_via_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            if "safari" in text:
                return _laya("safari")
            return _laya("notes")

        d = handle_utterance("open notes and safari", CATALOG, {}, predict)
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["notes", "safari"])
        self.assertEqual(called, ["open notes", "open safari"])

    def test_podcast_and_notes_opens_both(self):
        catalog = dict(CATALOG)
        catalog["podcasts"] = {"say": "Podcasts", "aliases": ["podcasts", "podcast"]}

        def predict(text, catalog):
            if "podcast" in text:
                return _laya("podcasts")
            return _laya("notes")

        d = handle_utterance("open podcast and notes", catalog, {}, predict)
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["podcasts", "notes"])

    def test_three_named_apps_with_commas_opens_all(self):
        catalog = dict(CATALOG)
        catalog["calculator"] = {"say": "Calculator", "aliases": ["calculator"]}
        catalog["antigravity"] = {"say": "Antigravity", "aliases": ["antigravity"]}

        called = []

        def predict(text, catalog):
            called.append(text)
            for name in ("calculator", "antigravity", "notes"):
                if name in text.lower():
                    return _laya(name)
            return _laya("unspecified", intent="chat")

        d = handle_utterance(
            "open calculator, antigravity and notes", catalog, {}, predict
        )
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["calculator", "antigravity", "notes"])
        self.assertEqual(
            called, ["open calculator", "open antigravity", "open notes"]
        )

    def test_streaming_partials_open_each_new_name(self):
        from opener.loop import newly_named_apps

        catalog = dict(CATALOG)
        catalog["calculator"] = {"say": "Calculator", "aliases": ["calculator"]}
        catalog["antigravity"] = {"say": "Antigravity", "aliases": ["antigravity"]}

        self.assertEqual(
            newly_named_apps("open calculator", catalog),
            ["calculator"],
        )
        self.assertEqual(
            newly_named_apps(
                "open calculator, antigravity", catalog, already=["calculator"]
            ),
            ["antigravity"],
        )
        self.assertEqual(
            newly_named_apps(
                "open calculator, antigravity and notes",
                catalog,
                already=["calculator", "antigravity"],
            ),
            ["notes"],
        )

    def test_spoken_list_without_commas_opens_all(self):
        # Apple Speech has punctuation off. The live phrase is
        # "open calculator antigravity and notes" — still three apps.
        catalog = dict(CATALOG)
        catalog["calculator"] = {"say": "Calculator", "aliases": ["calculator"]}
        catalog["antigravity"] = {"say": "Antigravity", "aliases": ["antigravity"]}

        called = []

        def predict(text, catalog):
            called.append(text)
            for name in ("calculator", "antigravity", "notes"):
                if name in text.lower():
                    return _laya(name)
            return _laya("unspecified", intent="chat")

        d = handle_utterance(
            "open calculator antigravity and notes", catalog, {}, predict
        )
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["calculator", "antigravity", "notes"])
        self.assertEqual(
            newly_named_apps("open calculator antigravity", catalog),
            ["calculator", "antigravity"],
        )

    def test_close_named_app_calls_laya_and_closes_when_running(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("brave")

        d = handle_utterance(
            "close brave", CATALOG, {}, predict, running={"brave"}
        )
        self.assertEqual((d.action, d.app, d.reason), ("close", "brave", "laya"))
        self.assertEqual(d.apps, ["brave"])
        self.assertEqual(called, ["close brave"])

    def test_close_named_app_asks_to_open_when_not_running(self):
        def predict(text, catalog):
            return _laya("brave")

        d = handle_utterance("close brave", CATALOG, {}, predict, running=set())
        self.assertEqual((d.action, d.app), ("confirm", "brave"))
        self.assertEqual(d.reason, "not-running")

    def test_quit_named_app_quits_when_running(self):
        def predict(text, catalog):
            return _laya("brave")

        d = handle_utterance(
            "quit brave", CATALOG, {}, predict, running={"brave"}
        )
        self.assertEqual((d.action, d.app), ("quit", "brave"))

    def test_kill_named_app_force_quits_when_running(self):
        def predict(text, catalog):
            return _laya("brave")

        d = handle_utterance(
            "kill brave", CATALOG, {}, predict, running={"brave"}
        )
        self.assertEqual((d.action, d.app), ("kill", "brave"))

    def test_force_quit_named_app_is_kill(self):
        def predict(text, catalog):
            return _laya("brave")

        d = handle_utterance(
            "force quit brave", CATALOG, {}, predict, running={"brave"}
        )
        self.assertEqual((d.action, d.app), ("kill", "brave"))

    def test_quit_not_running_asks_to_open(self):
        def predict(text, catalog):
            return _laya("brave")

        d = handle_utterance("quit brave", CATALOG, {}, predict, running=set())
        self.assertEqual((d.action, d.app, d.reason), ("confirm", "brave", "not-running"))

    def test_close_without_app_asks_which(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("unspecified", intent="chat")

        d = handle_utterance("close", CATALOG, {}, predict, running=set())
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)
        self.assertEqual(d.reason, "which-app")
        self.assertEqual(called, ["close"])

    def test_close_two_apps_closes_running_and_confirms_rest(self):
        def predict(text, catalog):
            if "brave" in text:
                return _laya("brave")
            return _laya("notes")

        d = handle_utterance(
            "close brave and notes",
            CATALOG,
            {},
            predict,
            running={"brave"},
        )
        self.assertEqual(d.action, "close")
        self.assertEqual(d.apps, ["brave"])
        self.assertEqual(d.pending, ["notes"])
        self.assertIn("Closed Brave.", spoken(d, CATALOG))
        self.assertIn("Notes isn't open", spoken(d, CATALOG))

    def test_yes_on_pending_open_opens(self):
        def predict(text, catalog):
            raise AssertionError("yes/no must not call Laya")

        d = handle_utterance(
            "yes",
            CATALOG,
            {},
            predict,
            pending=["brave"],
        )
        self.assertEqual((d.action, d.app), ("open", "brave"))
        self.assertEqual(d.apps, ["brave"])
        self.assertEqual(d.reason, "confirm")

    def test_no_on_pending_open_refuses(self):
        def predict(text, catalog):
            raise AssertionError("yes/no must not call Laya")

        d = handle_utterance(
            "no",
            CATALOG,
            {},
            predict,
            pending=["brave"],
        )
        self.assertEqual(d.action, "refuse")
        self.assertEqual(d.reason, "confirm")
        self.assertEqual(d.apps, [])

    def test_open_google_chrome_is_still_the_app(self):
        def predict(text, catalog):
            return _laya("chrome")

        catalog = dict(CATALOG)
        catalog["chrome"] = {"say": "Chrome", "open": "Google Chrome", "aliases": ["chrome", "google chrome"]}
        d = handle_utterance("open google chrome", catalog, {}, predict)
        self.assertEqual((d.action, d.app), ("open", "chrome"))
        self.assertIsNone(d.url)

    def test_open_youtube_in_brave_calls_laya_and_returns_url(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("brave")

        d = handle_utterance("open youtube in brave", CATALOG, {}, predict)
        self.assertEqual(d.action, "open_url")
        self.assertEqual(d.app, "brave")
        self.assertEqual(d.apps, ["brave"])
        self.assertEqual(d.url, "https://www.youtube.com")
        self.assertEqual(called, ["open Brave"])

    def test_open_youtube_dot_com_in_safari(self):
        def predict(text, catalog):
            return _laya("safari")

        d = handle_utterance("open youtube.com in safari", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app, d.url), ("open_url", "safari", "https://www.youtube.com"))

    def test_open_github_dot_com_uses_default_browser_when_unnamed(self):
        def predict(text, catalog):
            return _laya("unspecified", intent="chat")

        d = handle_utterance("open github.com", CATALOG, {}, predict)
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)
        self.assertIsNone(d.url)

    def test_open_clipboard_does_not_call_laya(self):
        def predict(text, catalog):
            raise AssertionError("clipboard must not call Laya")

        d = handle_utterance("open clipboard", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app), ("open_url", None))
        self.assertEqual(d.url, "clipboard")
        self.assertEqual(d.reason, "clipboard")

    def test_open_clipboard_in_brave_calls_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("brave")

        d = handle_utterance("open clipboard in brave", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app, d.url), ("open_url", "brave", "clipboard"))
        self.assertEqual(called, ["open Brave"])

    def test_close_does_not_target_finder_or_self(self):
        catalog = dict(CATALOG)
        catalog["finder"] = {"say": "Finder", "aliases": ["finder"]}
        catalog["layaopener"] = {"say": "Laya Opener", "aliases": ["laya opener"]}

        def predict(text, catalog):
            if "finder" in text:
                return _laya("finder")
            return _laya("layaopener")

        d = handle_utterance(
            "quit finder", catalog, {}, predict, running={"finder"}
        )
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)
        self.assertEqual(d.reason, "protected")

    def test_close_does_not_target_sayso(self):
        catalog = dict(CATALOG)
        catalog["sayso"] = {"say": "Sayso", "aliases": ["sayso", "say so"]}

        def predict(text, catalog):
            return _laya("sayso")

        d = handle_utterance(
            "quit sayso", catalog, {}, predict, running={"sayso"}
        )
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)
        self.assertEqual(d.reason, "protected")


class SpokenTests(unittest.TestCase):
    def test_open_uses_spoken_name(self):
        self.assertEqual(
            spoken(Decision("open", app="notes"), CATALOG),
            "Opening Notes.",
        )

    def test_refuse(self):
        self.assertEqual(spoken(Decision("refuse"), CATALOG), "Okay, I won't.")

    def test_ask(self):
        self.assertEqual(
            spoken(Decision("ask"), CATALOG),
            "Which app should I open?",
        )

    def test_chat_hints_examples(self):
        text = spoken(Decision("chat"), CATALOG)
        self.assertIn("open", text.lower())

    def test_stop(self):
        self.assertEqual(spoken(Decision("stop"), CATALOG), "Goodbye.")

    def test_close_uses_spoken_name(self):
        self.assertEqual(
            spoken(Decision("close", app="brave"), CATALOG),
            "Closed Brave.",
        )

    def test_quit_uses_spoken_name(self):
        self.assertEqual(
            spoken(Decision("quit", app="brave"), CATALOG),
            "Quit Brave.",
        )

    def test_kill_uses_spoken_name(self):
        self.assertEqual(
            spoken(Decision("kill", app="brave"), CATALOG),
            "Force quit Brave.",
        )

    def test_confirm_asks_to_open(self):
        self.assertEqual(
            spoken(Decision("confirm", app="brave", reason="not-running"), CATALOG),
            "Brave isn't open. Open it?",
        )

    def test_ask_which_app_to_close(self):
        self.assertEqual(
            spoken(Decision("ask", reason="which-app"), CATALOG),
            "Which app should I close?",
        )

    def test_protected_app(self):
        self.assertEqual(
            spoken(Decision("ask", reason="protected"), CATALOG),
            "I won't quit that.",
        )

    def test_open_url_uses_site_and_app(self):
        self.assertEqual(
            spoken(
                Decision("open_url", app="brave", url="https://www.youtube.com"),
                CATALOG,
            ),
            "Opening YouTube in Brave.",
        )

    def test_open_clipboard_line(self):
        self.assertEqual(
            spoken(Decision("open_url", url="clipboard", reason="clipboard"), CATALOG),
            "Opening the clipboard.",
        )

    def test_open_clipboard_in_app_line(self):
        self.assertEqual(
            spoken(
                Decision("open_url", app="safari", url="clipboard", reason="clipboard"),
                CATALOG,
            ),
            "Opening the clipboard in Safari.",
        )


class WakeStripTests(unittest.TestCase):
    def test_hey_mac_open_notes_calls_laya_on_remainder(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("notes")

        d = handle_utterance("hey mac open notes", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app), ("open", "notes"))
        self.assertEqual(called, ["open notes"])

    def test_bhai_mac_alone_does_not_call_laya(self):
        def predict(text, catalog):
            raise AssertionError("bare wake must not call Laya")

        d = handle_utterance("Bhai mac", CATALOG, {}, predict)
        self.assertEqual(d.action, "chat")
        self.assertEqual(d.reason, "wake")

    def test_asr_bye_mac_open_safari_strips(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("safari")

        d = handle_utterance("bye mac open safari", CATALOG, {}, predict)
        self.assertEqual((d.action, d.app), ("open", "safari"))
        self.assertEqual(called, ["open safari"])

    def test_wake_disabled_keeps_full_text(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return _laya("unspecified", intent="chat")

        d = handle_utterance(
            "hey mac open notes",
            CATALOG,
            {},
            predict,
            settings={"wake_enabled": False},
        )
        self.assertEqual(called, ["hey mac open notes"])

    def test_hey_mac_open_notes_and_safari_opens_both(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            if "safari" in text:
                return _laya("safari")
            return _laya("notes")

        d = handle_utterance("hey mac open notes and safari", CATALOG, {}, predict)
        self.assertEqual(d.action, "open")
        self.assertEqual(d.apps, ["notes", "safari"])
        self.assertEqual(called, ["open notes", "open safari"])


if __name__ == "__main__":
    unittest.main()
