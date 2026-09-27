import json
import unittest

from opener.server import decide_payload


CATALOG = {
    "notes": {"say": "Notes", "criteria": "Notes.app"},
    "safari": {"say": "Safari", "criteria": "Safari.app"},
}


class DecidePayloadTests(unittest.TestCase):
    def test_always_forwards_utterance_to_laya(self):
        called = []

        def predict(text, catalog):
            called.append((text, list(catalog)))
            return {
                "intent": {"choice": "launch", "answer_confidence": 0.9},
                "app": {"choice": "notes", "answer_confidence": 0.88},
            }

        out = decide_payload(
            "open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="laya",
        )
        self.assertEqual(called[0][0], "open notes")
        self.assertEqual(out["action"], "open")
        self.assertEqual(out["app"], "notes")
        self.assertEqual(out["reason"], "laya")
        self.assertIn("Opening", out["spoken"])

    def test_empty_text_does_not_call_laya(self):
        def predict(text, catalog):
            raise AssertionError("no empty predict")

        out = decide_payload("  ", catalog=CATALOG, predict_fn=predict)
        self.assertEqual(out["action"], "ask")

    def test_reports_laya_timing(self):
        def predict(text, catalog):
            return {
                "app": {"choice": "notes", "answer_confidence": 0.9},
            }

        out = decide_payload(
            "open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="laya",
        )
        self.assertIn("timing", out)
        self.assertIn("total_ms", out["timing"])
        self.assertIsNotNone(out["timing"]["laya_ms"])

    def test_strips_wake_before_laya(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return {
                "intent": {"choice": "launch", "answer_confidence": 0.9},
                "app": {"choice": "notes", "answer_confidence": 0.88},
            }

        out = decide_payload(
            "hey mac open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="laya",
        )
        self.assertEqual(called, ["open notes"])
        self.assertEqual(out["app"], "notes")

    def test_unknown_backend_does_not_call_laya(self):
        def predict(text, catalog):
            raise AssertionError("unknown engine must not call a model")

        out = decide_payload(
            "open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="nope",
        )
        self.assertEqual(out["action"], "ask")
        self.assertEqual(out["reason"], "backend-unavailable")

    def test_jev_without_token_does_not_call_predict(self):
        def predict(text, catalog):
            raise AssertionError("missing key must not call Jev")

        out = decide_payload(
            "open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="jev",
        )
        self.assertEqual(out["action"], "ask")
        self.assertEqual(out["reason"], "backend-unavailable")
        self.assertIn("Jev", out["spoken"])

    def test_close_running_app_returns_close(self):
        def predict(text, catalog):
            return {
                "app": {"choice": "safari", "answer_confidence": 0.9},
            }

        out = decide_payload(
            "close safari",
            catalog=CATALOG,
            predict_fn=predict,
            running=["safari"],
        )
        self.assertEqual(out["action"], "close")
        self.assertEqual(out["app"], "safari")
        self.assertEqual(out["apps"], ["safari"])
        self.assertEqual(out["pending"], [])
        self.assertIn("Closed", out["spoken"])

    def test_close_not_running_returns_confirm(self):
        def predict(text, catalog):
            return {
                "app": {"choice": "safari", "answer_confidence": 0.9},
            }

        out = decide_payload(
            "close safari",
            catalog=CATALOG,
            predict_fn=predict,
            running=[],
        )
        self.assertEqual(out["action"], "confirm")
        self.assertEqual(out["app"], "safari")
        self.assertEqual(out["pending"], ["safari"])
        self.assertIn("isn't open", out["spoken"])

    def test_yes_on_pending_opens(self):
        def predict(text, catalog):
            raise AssertionError("yes must not call Laya")

        out = decide_payload(
            "yes",
            catalog=CATALOG,
            predict_fn=predict,
            pending=["notes"],
        )
        self.assertEqual(out["action"], "open")
        self.assertEqual(out["apps"], ["notes"])
        self.assertEqual(out["reason"], "confirm")

    def test_open_youtube_in_brave_returns_url(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return {
                "app": {"choice": "safari", "answer_confidence": 0.9},
            }

        catalog = {
            "safari": {"say": "Safari", "criteria": "Safari.app", "aliases": ["safari"]},
            "brave": {"say": "Brave", "criteria": "Brave.app", "aliases": ["brave"]},
        }
        out = decide_payload(
            "open youtube in brave",
            catalog=catalog,
            predict_fn=predict,
            backend="laya",
        )
        self.assertEqual(out["action"], "open_url")
        self.assertEqual(out["app"], "brave")
        self.assertEqual(out["url"], "https://www.youtube.com")
        self.assertEqual(called, ["open Brave"])
        self.assertIn("YouTube", out["spoken"])

    def test_open_clipboard_payload(self):
        def predict(text, catalog):
            raise AssertionError("clipboard must not call Laya")

        out = decide_payload("open clipboard", catalog=CATALOG, predict_fn=predict)
        self.assertEqual(out["action"], "open_url")
        self.assertEqual(out["url"], "clipboard")
        self.assertIsNone(out["app"])


if __name__ == "__main__":
    unittest.main()
