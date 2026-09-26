import unittest

from opener.policy import decide


def _laya(intent="launch", intent_p=0.9, app="safari", app_p=0.95):
    return {
        "intent": {"choice": intent, "answer_confidence": intent_p},
        "app": {"choice": app, "answer_confidence": app_p},
    }


class DecideTests(unittest.TestCase):
    def test_laya_app_opens(self):
        d = decide("open safari", laya=_laya())
        self.assertEqual((d.action, d.app, d.reason), ("open", "safari", "laya"))

    def test_app_choice_opens_even_if_intent_is_chat(self):
        d = decide(
            "open notes",
            laya=_laya(intent="chat", intent_p=0.9, app="notes", app_p=0.8),
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "notes", "laya"))

    def test_laya_refuse_intent(self):
        d = decide(
            "don't open chrome",
            laya=_laya(intent="refuse", app="chrome"),
        )
        self.assertEqual(d.action, "refuse")
        self.assertIsNone(d.app)

    def test_greeting_is_chat(self):
        d = decide(
            "hey how are you",
            laya=_laya(intent="chat", intent_p=0.88, app="unspecified", app_p=0.7),
        )
        self.assertEqual(d.action, "chat")
        self.assertIsNone(d.app)

    def test_laya_picks_app(self):
        d = decide(
            "show my reminders",
            laya=_laya(app="reminders", app_p=1.0, intent_p=0.73),
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "reminders", "laya"))

    def test_app_only_laya_opens_without_intent_head(self):
        d = decide(
            "jot something down",
            laya={"app": {"choice": "notes", "answer_confidence": 0.80}},
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "notes", "laya"))

    def test_app_only_low_confidence_asks(self):
        d = decide(
            "do the thing",
            laya={"app": {"choice": "notes", "answer_confidence": 0.40}},
        )
        self.assertEqual(d.action, "ask")

    def test_unspecified_app_asks(self):
        d = decide(
            "open the thing",
            laya=_laya(app="unspecified", app_p=0.9),
        )
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)

    def test_low_intent_confidence_is_chat(self):
        d = decide(
            "good morning",
            laya=_laya(intent="launch", intent_p=0.51, app="unspecified", app_p=0.7),
        )
        self.assertEqual(d.action, "chat")

    def test_laya_choice_beats_alias(self):
        d = decide(
            "play some music on spotify",
            alias="spotify",
            laya=_laya(app="safari", app_p=0.80),
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "safari", "laya"))

    def test_alias_is_ignored_when_laya_answers(self):
        d = decide("open notes", alias="notes", laya=_laya(app="notes"))
        self.assertEqual(d.reason, "laya")

    def test_unknown_app_not_in_catalog_does_not_open(self):
        d = decide(
            "open slack",
            laya=_laya(app="slack", app_p=0.99),
            catalog={"notes": {}, "safari": {}},
        )
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)

    def test_close_scores_do_not_open(self):
        d = decide(
            "do the thing",
            laya={
                "app": {
                    "choice": "calendar",
                    "answer_confidence": 0.62,
                    "probabilities": {"calendar": 0.62, "notes": 0.55},
                }
            },
            catalog={"calendar": {}, "notes": {}},
        )
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)

    def test_low_confidence_calendar_does_not_open(self):
        d = decide(
            "hello there",
            laya=_laya(app="calendar", app_p=0.61, intent="chat"),
            catalog={"calendar": {}, "notes": {}},
        )
        self.assertEqual(d.action, "ask")
        self.assertIsNone(d.app)

    def test_named_app_opens_at_moderate_laya_confidence(self):
        d = decide(
            "open vs code",
            laya=_laya(app="vscode", app_p=0.59),
            catalog={"vscode": {"aliases": ["vscode", "vs code"]}},
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "vscode", "laya"))

    def test_exactly_named_app_opens_at_low_laya_score(self):
        d = decide(
            "antigravity",
            laya=_laya(app="antigravity", app_p=0.28),
            catalog={"antigravity": {"aliases": ["antigravity"]}},
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "antigravity", "laya"))

    def test_picks_highest_probability_not_stale_choice(self):
        d = decide(
            "arc browser",
            laya={
                "app": {
                    "choice": "chrome",
                    "answer_confidence": 0.80,
                    "probabilities": {"arc": 0.71, "chrome": 0.20, "unspecified": 0.09},
                }
            },
            catalog={"arc": {"aliases": ["arc"]}, "chrome": {"aliases": ["chrome"]}},
        )
        self.assertEqual((d.action, d.app, d.reason), ("open", "arc", "laya"))


if __name__ == "__main__":
    unittest.main()
