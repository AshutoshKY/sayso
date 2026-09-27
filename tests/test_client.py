import json
import unittest
from io import BytesIO
from urllib.error import URLError

from opener.client import build_questions, parse_answers, predict


MINI = {
    "safari": {"criteria": "Safari.app. The word safari."},
    "notes": {"criteria": "Notes.app. Apple Notes."},
}


class BuildQuestionsTests(unittest.TestCase):
    def test_has_intent_and_app_heads(self):
        q = build_questions(MINI)
        self.assertEqual(set(q), {"intent", "app"})
        self.assertEqual(q["intent"]["type"], "choice")
        self.assertEqual(q["app"]["type"], "choice")
        self.assertIn("safari", q["app"]["criteria"])
        self.assertIn("notes", q["app"]["criteria"])
        self.assertIn("unspecified", q["app"]["criteria"])
        self.assertIn("launch", q["intent"]["criteria"])
        self.assertIn("chat", q["intent"]["criteria"])


class ParseAnswersTests(unittest.TestCase):
    def test_keeps_choice_and_answer_confidence(self):
        parsed = parse_answers(
            {
                "answers": {
                    "intent": {
                        "type": "choice",
                        "choice": "launch",
                        "answer_confidence": 0.94,
                    },
                    "app": {
                        "type": "choice",
                        "choice": "safari",
                        "answer_confidence": 1.0,
                    },
                }
            }
        )
        self.assertEqual(parsed["intent"]["choice"], "launch")
        self.assertEqual(parsed["app"]["choice"], "safari")
        self.assertEqual(parsed["app"]["answer_confidence"], 1.0)


class PredictTests(unittest.TestCase):
    def test_posts_state_and_english_model(self):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {
                        "answers": {
                            "intent": {"choice": "launch", "answer_confidence": 0.9},
                            "app": {"choice": "notes", "answer_confidence": 1.0},
                        }
                    }
                ).encode()

        def opener(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data.decode())
            captured["timeout"] = timeout
            return FakeResp()

        parsed = predict(
            "fire up notes",
            MINI,
            url="http://127.0.0.1:8001/v1/systemone",
            opener=opener,
        )
        self.assertEqual(captured["body"]["state"], "fire up notes")
        self.assertEqual(captured["body"]["model"], "english")
        self.assertNotIn("intent", captured["body"]["questions"])
        criteria = captured["body"]["questions"]["app"]["criteria"]
        self.assertIn("notes", criteria)
        self.assertIn("safari", criteria)
        self.assertIn("unspecified", criteria)
        self.assertNotIn("calendar", criteria)
        self.assertEqual(parsed["app"]["choice"], "notes")

    def test_predict_adds_named_extra_from_catalog(self):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {"answers": {"app": {"choice": "hermes", "answer_confidence": 1.0}}}
                ).encode()

        def opener(req, timeout=0):
            captured["body"] = json.loads(req.data.decode())
            return FakeResp()

        catalog = dict(MINI)
        catalog["hermes"] = {"criteria": "the word hermes only", "aliases": ["hermes"]}
        predict("open hermes", catalog, opener=opener)
        criteria = captured["body"]["questions"]["app"]["criteria"]
        self.assertIn("hermes", criteria)
        self.assertNotIn("calendar", criteria)

    def test_named_extra_uses_short_criteria(self):
        from opener.client import questions_for

        catalog = dict(MINI)
        catalog["vscode"] = {
            "criteria": "Visual Studio Code.app. vscode, vs code, visual studio code, or the code editor.",
            "aliases": ["vscode", "vs code", "visual studio code"],
        }
        criteria = questions_for("open vs code", catalog)["app"]["criteria"]
        self.assertIn("vscode", criteria)
        self.assertNotIn("code editor", criteria["vscode"])

    def test_ark_browser_includes_arc_not_notes(self):
        from opener.client import questions_for

        catalog = {
            "notes": {"criteria": "notes", "aliases": ["notes"]},
            "chrome": {"criteria": "chrome", "aliases": ["chrome"]},
            "safari": {"criteria": "safari", "aliases": ["safari"]},
            "arc": {"criteria": "the word arc only", "aliases": ["arc", "ark", "art"]},
        }
        criteria = questions_for("ark browser", catalog)["app"]["criteria"]
        self.assertIn("arc", criteria)
        self.assertIn("chrome", criteria)
        self.assertNotIn("notes", criteria)

    def test_art_browser_includes_arc(self):
        from opener.client import questions_for

        catalog = {
            "chrome": {"aliases": ["chrome"]},
            "arc": {"aliases": ["arc", "ark", "art"]},
        }
        criteria = questions_for("open art browser", catalog)["app"]["criteria"]
        self.assertIn("arc", criteria)

    def test_spaced_app_name_includes_compact_id(self):
        from opener.client import questions_for

        catalog = {
            "notes": {"aliases": ["notes"]},
            "antigravity": {"aliases": ["antigravity"], "criteria": "antigravity"},
        }
        criteria = questions_for("open anti gravity", catalog)["app"]["criteria"]
        self.assertIn("antigravity", criteria)

    def test_named_app_uses_small_choice_set(self):
        from opener.client import DAILY_IDS, questions_for

        catalog = {app_id: {"aliases": [app_id], "criteria": app_id} for app_id in DAILY_IDS}
        catalog["antigravity"] = {"aliases": ["antigravity"], "criteria": "antigravity"}
        catalog["chess"] = {"aliases": ["chess"], "criteria": "chess"}
        criteria = questions_for("open anti gravity", catalog)["app"]["criteria"]
        self.assertIn("antigravity", criteria)
        self.assertIn("unspecified", criteria)
        self.assertNotIn("chess", criteria)
        self.assertGreaterEqual(len(criteria), 3)
        self.assertLessEqual(len(criteria), 6)

    def test_paraphrase_keeps_daily_choice_set(self):
        from opener.client import questions_for

        catalog = {
            "notes": {"aliases": ["notes"], "criteria": "notes"},
            "reminders": {"aliases": ["reminders"], "criteria": "reminders"},
            "safari": {"aliases": ["safari"], "criteria": "safari"},
        }
        criteria = questions_for("jot something down", catalog)["app"]["criteria"]
        self.assertIn("notes", criteria)
        self.assertIn("reminders", criteria)

    def test_trailing_app_word_includes_compact_id_not_apps(self):
        from opener.client import questions_for

        catalog = {
            "notes": {"aliases": ["notes"]},
            "antigravity": {"aliases": ["antigravity"], "criteria": "antigravity"},
            "apps": {"aliases": ["apps", "app"], "criteria": "apps"},
        }
        criteria = questions_for("open anti gravity app", catalog)["app"]["criteria"]
        self.assertIn("antigravity", criteria)
        self.assertNotIn("apps", criteria)

    def test_asr_confusion_includes_hermes(self):
        from opener.client import questions_for

        catalog = {
            "notes": {"aliases": ["notes"]},
            "hermes": {
                "aliases": ["hermes", "her mess", "hermits"],
                "criteria": "hermes",
            },
        }
        criteria = questions_for("open her mess", catalog)["app"]["criteria"]
        self.assertIn("hermes", criteria)

    def test_cloudflare_speech_includes_warp(self):
        from opener.client import questions_for

        catalog = {
            "notes": {"aliases": ["notes"]},
            "cloudflarewarp": {
                "aliases": ["cloudflare warp", "cloudflare", "cloud flare"],
                "criteria": "cloudflare warp",
            },
        }
        criteria = questions_for("open cloud flare", catalog)["app"]["criteria"]
        self.assertIn("cloudflarewarp", criteria)

    def test_network_error_returns_empty_answers(self):
        def opener(req, timeout=0):
            raise URLError("down")

        parsed = predict("open safari", MINI, opener=opener)
        self.assertEqual(parsed["intent"]["choice"], None)
        self.assertEqual(parsed["app"]["choice"], None)

    def test_predict_sends_authorization_when_token_given(self):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps(
                    {"answers": {"app": {"choice": "notes", "confidence": 0.95}}}
                ).encode()

        def opener(req, timeout=0):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            captured["body"] = json.loads(req.data.decode())
            return FakeResp()

        parsed = predict(
            "open notes",
            MINI,
            url="https://api.typesafe.ai/v1/systemone",
            model="jev-latest",
            token="secret-token",
            opener=opener,
        )
        self.assertEqual(captured["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(captured["body"]["model"], "jev-latest")
        headers = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertEqual(headers.get("authorization"), "Bearer secret-token")
        self.assertEqual(parsed["app"]["choice"], "notes")
        self.assertEqual(parsed["app"]["answer_confidence"], 0.95)

    def test_predict_omits_authorization_without_token(self):
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"answers": {"app": {"choice": "notes"}}}).encode()

        def opener(req, timeout=0):
            captured["headers"] = dict(req.header_items())
            return FakeResp()

        predict("open notes", MINI, opener=opener)
        headers = {k.lower(): v for k, v in captured["headers"].items()}
        self.assertNotIn("authorization", headers)


if __name__ == "__main__":
    unittest.main()
