import unittest

from opener.loop import handle_utterance, spoken
from opener.system_cmd import from_laya, label, looks_systemish, parse


def empty_laya(text, catalog):
    return {
        "intent": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
        "app": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
        "system": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
    }


def notes_laya(text, catalog):
    return {
        "intent": {"choice": "launch", "answer_confidence": 0.9, "probabilities": {}},
        "app": {
            "choice": "notes",
            "answer_confidence": 0.9,
            "probabilities": {"notes": 0.9, "unspecified": 0.1},
        },
        "system": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
    }


CATALOG = {"notes": {"say": "Notes", "criteria": "Notes.app"}}


class ParseTests(unittest.TestCase):
    def check(self, text, verb, value=None):
        cmd = parse(text)
        self.assertIsNotNone(cmd, text)
        self.assertEqual(cmd["verb"], verb, text)  # type: ignore[index]
        if value is not None:
            self.assertAlmostEqual(cmd.get("value"), value, places=3, msg=text)  # type: ignore[union-attr]

    def test_user_example_two_means_twenty_percent(self):
        self.check("increase screen brightness by 2", "brightness_up", 0.2)
        self.check("increase brightness by 2", "brightness_up", 0.2)
        self.check("decrease volume by 5", "volume_down", 0.5)

    def test_volume(self):
        self.check("turn up the volume", "volume_up", 0.1)
        self.check("volume up", "volume_up", 0.1)
        self.check("volume down by 3", "volume_down", 0.3)
        self.check("make it louder", "volume_up", 0.1)
        self.check("quieter please", "volume_down", 0.1)
        self.check("set volume to 50", "volume_set", 0.5)
        self.check("max volume", "volume_set", 1.0)
        self.check("half volume", "volume_set", 0.5)
        self.check("mute", "volume_mute")
        self.check("unmute", "volume_unmute")
        self.check("volume 70", "volume_set", 0.7)

    def test_brightness(self):
        self.check("turn up the brightness", "brightness_up", 0.1)
        self.check("dim the screen", "brightness_down", 0.1)
        self.check("make the screen brighter", "brightness_up", 0.1)
        self.check("screen too bright", "brightness_down", 0.1)
        self.check("too dim", "brightness_up", 0.1)
        self.check("set brightness to 80", "brightness_set", 0.8)
        self.check("minimum brightness", "brightness_set", 0.05)

    def test_explicit_percent_beats_step_rule(self):
        self.check("increase volume by 2 percent", "volume_up", 0.02)
        self.check("brightness up 20 percent", "brightness_up", 0.2)

    def test_asr_homophones_after_by(self):
        # Apple Speech writes "by two" as "by to"/"by too".
        self.check("increase volume by two", "volume_up", 0.2)
        self.check("increase volume by to", "volume_up", 0.2)
        self.check("increase volume by too", "volume_up", 0.2)
        self.check("volume down by ate", "volume_down", 0.8)

    def test_intensifier_too_is_not_a_number(self):
        self.check("screen too bright", "brightness_down", 0.1)
        self.check("too dim", "brightness_up", 0.1)
        self.check("music too loud", "volume_down", 0.1)

    def test_appearance(self):
        self.check("turn on dark mode", "dark_mode")
        self.check("dark mode", "dark_mode")
        self.check("turn off dark mode", "light_mode")
        self.check("light mode on", "light_mode")
        self.check("night mode on", "night_shift_on")
        self.check("turn on night shift", "night_shift_on")
        self.check("nightshift off", "night_shift_off")

    def test_lock_battery(self):
        self.check("lock screen", "lock_screen")
        self.check("lock my mac", "lock_screen")
        self.check("battery percentage", "battery")
        self.check("how much battery is left", "battery")
        self.check("how much juice is left", "battery")
        self.check("is it charging", "battery")

    def test_panes_and_airdrop(self):
        self.check("open wifi settings", "wifi_settings")
        self.check("open wi-fi preferences", "wifi_settings")
        self.check("bluetooth settings", "bluetooth_settings")
        self.check("turn off airdrop", "airdrop_off")
        self.check("airdrop off", "airdrop_off")
        self.check("disable air drop", "airdrop_off")
        self.check("airdrop everyone", "airdrop_everyone")
        self.check("airdrop contacts only", "airdrop_contacts")
        self.check("turn airdrop on", "airdrop_on")

    def test_negatives(self):
        for text in (
            "open notes",
            "open wifi",
            "unlock the mac",
            "don't turn up the volume",
            "what is the weather",
            "set volume",   # set with no amount is ambiguous
        ):
            self.assertIsNone(parse(text), text)

    def test_gate(self):
        self.assertTrue(looks_systemish("make it louder"))
        self.assertTrue(looks_systemish("open wifi settings"))
        self.assertFalse(looks_systemish("open notes"))

    def test_label_lockstep(self):
        self.assertEqual(label({"verb": "volume_up", "value": 0.2}), "Volume up 20%.")
        self.assertEqual(label({"verb": "lock_screen"}), "Locking the screen.")
        self.assertEqual(label({"verb": "nonsense"}), "")


class FromLayaTests(unittest.TestCase):
    def laya(self, choice, conf=0.8, probs=None):
        return {
            "system": {
                "choice": choice,
                "answer_confidence": conf,
                "probabilities": probs if probs is not None else {choice: conf},
            }
        }

    def test_confident_choice_gets_defaults(self):
        self.assertEqual(from_laya(self.laya("volume_up")), {"verb": "volume_up", "value": 0.1})
        self.assertEqual(from_laya(self.laya("lock_screen")), {"verb": "lock_screen"})

    def test_unspecified_and_low_confidence_skip(self):
        self.assertIsNone(from_laya(self.laya("unspecified", 0.9)))
        self.assertIsNone(from_laya(self.laya("volume_up", 0.3)))
        self.assertIsNone(from_laya({}))
        self.assertIsNone(from_laya(None))

    def test_disagreeing_probabilities_skip(self):
        laya = self.laya("volume_up", 0.8, probs={"unspecified": 0.9, "volume_up": 0.1})
        self.assertIsNone(from_laya(laya))


class LoopIntegrationTests(unittest.TestCase):
    def test_single_system_skips_laya(self):
        def predict(text, catalog):
            raise AssertionError("host parse should win without a Laya call")

        decision = handle_utterance(
            "increase screen brightness by 2", CATALOG, {}, predict
        )
        self.assertEqual(decision.action, "system")
        self.assertEqual(decision.system, [{"verb": "brightness_up", "value": 0.2}])
        self.assertEqual(spoken(decision, CATALOG), "Brightness up 20%.")

    def test_wake_strip_then_system(self):
        decision = handle_utterance(
            "hey mac lock screen",
            CATALOG,
            {},
            empty_laya,
            settings={"wake_enabled": True},
        )
        self.assertEqual(decision.action, "system")
        self.assertEqual(decision.system, [{"verb": "lock_screen"}])

    def test_wake_then_mixed_open_and_system(self):
        decision = handle_utterance(
            "hey mac open notes and increase volume by 2",
            CATALOG,
            {},
            notes_laya,
            settings={"wake_enabled": True},
        )
        self.assertEqual(decision.action, "open")
        self.assertEqual(decision.apps, ["notes"])
        self.assertEqual(decision.system, [{"verb": "volume_up", "value": 0.2}])

    def test_laya_fallback_for_paraphrase(self):
        def laya(text, catalog):
            out = empty_laya(text, catalog)
            out["system"] = {
                "choice": "volume_up",
                "answer_confidence": 0.8,
                "probabilities": {"volume_up": 0.8, "unspecified": 0.2},
            }
            return out

        decision = handle_utterance("I can barely hear it", CATALOG, {}, laya)
        # No gate words -> no system head asked; laya answers app-unspecified.
        self.assertIn(decision.action, ("ask", "system"))

        gated = empty_laya("make it sound louder", CATALOG)
        gated["system"] = {
            "choice": "volume_up",
            "answer_confidence": 0.8,
            "probabilities": {"volume_up": 0.8},
        }
        decision = handle_utterance("make it sound louder", CATALOG, {}, lambda t, c: gated)
        self.assertEqual(decision.action, "system")
        self.assertEqual(decision.system, [{"verb": "volume_up", "value": 0.1}])

    def test_mixed_open_and_system(self):
        decision = handle_utterance(
            "open notes and increase volume by 2", CATALOG, {}, notes_laya
        )
        self.assertEqual(decision.action, "open")
        self.assertEqual(decision.apps, ["notes"])
        self.assertEqual(decision.system, [{"verb": "volume_up", "value": 0.2}])
        self.assertEqual(spoken(decision, CATALOG), "Opening Notes. Volume up 20%.")

    def test_multi_system(self):
        decision = handle_utterance(
            "turn up the volume and lock the screen", CATALOG, {}, empty_laya
        )
        self.assertEqual(decision.action, "system")
        self.assertEqual(
            decision.system,
            [{"verb": "volume_up", "value": 0.1}, {"verb": "lock_screen"}],
        )

    def test_duplicate_system_verbs_deduped(self):
        decision = handle_utterance(
            "volume up and volume up", CATALOG, {}, empty_laya
        )
        self.assertEqual(len(decision.system), 1)

    def test_open_still_works(self):
        decision = handle_utterance("open notes", CATALOG, {}, notes_laya)
        self.assertEqual(decision.action, "open")
        self.assertEqual(decision.apps, ["notes"])
        self.assertEqual(decision.system, [])


if __name__ == "__main__":
    unittest.main()
