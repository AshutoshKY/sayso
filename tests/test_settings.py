import unittest

from opener.settings import (
    DEFAULT_SETTINGS,
    command_ready,
    hover_apply,
    listen_hold_named,
    match_wake,
    mic_needed,
    normalize_hotkey,
    normalize_settings,
    strip_wake,
    wake_commit,
)


class WakeMatchTests(unittest.TestCase):
    def test_hey_mac_alone_is_wake(self):
        hit, rest = match_wake("Hey Mac", DEFAULT_SETTINGS["wake_phrases"])
        self.assertTrue(hit)
        self.assertEqual(rest, "")

    def test_bhai_mac_alone_is_wake(self):
        hit, rest = match_wake("Bhai mac", DEFAULT_SETTINGS["wake_phrases"])
        self.assertTrue(hit)
        self.assertEqual(rest, "")

    def test_hey_mac_open_notes_strips_prefix(self):
        hit, rest = match_wake("hey mac open notes", DEFAULT_SETTINGS["wake_phrases"])
        self.assertTrue(hit)
        self.assertEqual(rest, "open notes")

    def test_asr_bye_mac_maps_to_bhai_mac(self):
        hit, rest = match_wake("bye mac open safari", DEFAULT_SETTINGS["wake_phrases"])
        self.assertTrue(hit)
        self.assertEqual(rest, "open safari")

    def test_asr_hay_mack_maps_to_hey_mac(self):
        hit, rest = match_wake("hay mack", DEFAULT_SETTINGS["wake_phrases"])
        self.assertTrue(hit)
        self.assertEqual(rest, "")

    def test_open_notes_is_not_a_wake(self):
        hit, rest = match_wake("open notes", DEFAULT_SETTINGS["wake_phrases"])
        self.assertFalse(hit)
        self.assertEqual(rest, "open notes")

    def test_custom_phrase_is_prefix_only(self):
        hit, rest = match_wake("okay computer launch mail", ["okay computer"])
        self.assertTrue(hit)
        self.assertEqual(rest, "launch mail")

    def test_wake_in_the_middle_is_ignored(self):
        hit, rest = match_wake("please open hey mac", DEFAULT_SETTINGS["wake_phrases"])
        self.assertFalse(hit)
        self.assertEqual(rest, "please open hey mac")

    def test_leading_filler_still_matches(self):
        hit, rest = match_wake("um hey mac", DEFAULT_SETTINGS["wake_phrases"])
        self.assertTrue(hit)
        self.assertEqual(rest, "")

    def test_empty_is_not_wake(self):
        hit, rest = match_wake("  ", DEFAULT_SETTINGS["wake_phrases"])
        self.assertFalse(hit)
        self.assertEqual(rest, "")

    def test_strip_wake_leaves_command(self):
        self.assertEqual(
            strip_wake("Hey Mac open notes", DEFAULT_SETTINGS["wake_phrases"]),
            "open notes",
        )

    def test_strip_wake_keeps_non_wake(self):
        self.assertEqual(
            strip_wake("open notes", DEFAULT_SETTINGS["wake_phrases"]),
            "open notes",
        )

    def test_strip_bare_wake_is_empty(self):
        self.assertEqual(strip_wake("bhai mac", DEFAULT_SETTINGS["wake_phrases"]), "")

    def test_streaming_hey_mac_then_command_waits_for_remainder(self):
        phrases = DEFAULT_SETTINGS["wake_phrases"]
        # First Apple partial is just the wake word. Do not commit — the
        # command is still being spoken.
        self.assertEqual(wake_commit("hey mac", phrases, elapsed=0.05), "hold")
        self.assertEqual(wake_commit("hey mac", phrases, elapsed=0.20), "hold")
        # "open safari" is still an open list — more names may follow.
        # Committing here drops "and notes".
        self.assertEqual(wake_commit("hey mac open safari", phrases, elapsed=0.40), "hold")
        self.assertEqual(
            wake_commit("hey mac open safari", phrases, elapsed=0.40, final=True),
            ("go", "open safari"),
        )

    def test_streaming_bare_wake_commits_after_hang(self):
        phrases = DEFAULT_SETTINGS["wake_phrases"]
        self.assertEqual(wake_commit("bhai mac", phrases, elapsed=0.10), "hold")
        self.assertEqual(wake_commit("bye mac", phrases, elapsed=0.55), ("listen", ""))

    def test_streaming_ignores_non_wake(self):
        self.assertEqual(
            wake_commit("open notes", DEFAULT_SETTINGS["wake_phrases"], elapsed=1.0),
            "ignore",
        )

    def test_streaming_verb_only_remainder_is_not_enough(self):
        phrases = DEFAULT_SETTINGS["wake_phrases"]
        # Apple's next partial after the wake is almost always just "open".
        # Committing that fires /decide with no app and drops "browser".
        self.assertEqual(wake_commit("hey mac open", phrases, elapsed=0.40), "hold")
        self.assertEqual(wake_commit("hey mac open the", phrases, elapsed=0.55), "hold")
        self.assertEqual(wake_commit("bhai mac launch", phrases, elapsed=1.20), "hold")
        self.assertEqual(wake_commit("hey mac open safari", phrases, elapsed=0.40), "hold")
        self.assertEqual(
            wake_commit("hey mac open safari", phrases, elapsed=0.40, final=True),
            ("go", "open safari"),
        )
        self.assertEqual(wake_commit("hey mac notes", phrases, elapsed=0.30), "hold")
        self.assertEqual(
            wake_commit("hey mac notes", phrases, elapsed=0.30, final=True),
            ("go", "notes"),
        )

    def test_wake_plus_multi_app_holds_until_list_closes_or_final(self):
        phrases = DEFAULT_SETTINGS["wake_phrases"]
        # Same recognition session: first name must not abort the mic.
        self.assertEqual(wake_commit("hey mac open notes", phrases, elapsed=0.40), "hold")
        self.assertEqual(wake_commit("hey mac open notes and", phrases, elapsed=0.55), "hold")
        self.assertEqual(
            wake_commit("hey mac open notes and safari", phrases, elapsed=0.70),
            "hold",
        )
        self.assertEqual(
            wake_commit("hey mac open notes and safari", phrases, elapsed=0.70, final=True),
            ("go", "open notes and safari"),
        )
        # User stopped after one name — the final transcript may go.
        self.assertEqual(
            wake_commit("hey mac open notes", phrases, elapsed=1.80, final=True),
            ("go", "open notes"),
        )

    def test_wake_plus_system_holds_until_final(self):
        phrases = DEFAULT_SETTINGS["wake_phrases"]
        # "increase" / "increase volume" look command-ready but the amount
        # is still coming. Do not .go on the partial.
        self.assertEqual(wake_commit("hey mac increase", phrases, elapsed=0.40), "hold")
        self.assertEqual(wake_commit("hey mac increase volume", phrases, elapsed=0.55), "hold")
        self.assertEqual(
            wake_commit("hey mac increase volume by 2", phrases, elapsed=0.80),
            "hold",
        )
        self.assertEqual(
            wake_commit("hey mac increase volume by 2", phrases, elapsed=0.80, final=True),
            ("go", "increase volume by 2"),
        )
        self.assertEqual(
            wake_commit("hey mac mute", phrases, elapsed=0.40, final=True),
            ("go", "mute"),
        )
        self.assertEqual(
            wake_commit("hey mac lock screen", phrases, elapsed=0.50, final=True),
            ("go", "lock screen"),
        )
        self.assertEqual(
            wake_commit(
                "hey mac open notes and increase volume by 2",
                phrases,
                elapsed=0.90,
            ),
            "hold",
        )
        self.assertEqual(
            wake_commit(
                "hey mac open notes and increase volume by 2",
                phrases,
                elapsed=0.90,
                final=True,
            ),
            ("go", "open notes and increase volume by 2"),
        )

    def test_command_ready_false_when_list_still_open(self):
        # First named app is not enough — more names may still be spoken.
        self.assertFalse(command_ready("open calculator,"))
        self.assertFalse(command_ready("open calculator and"))
        self.assertFalse(command_ready("open calculator, antigravity and"))
        self.assertTrue(command_ready("open calculator"))
        self.assertTrue(command_ready("open calculator, antigravity and notes"))
        self.assertTrue(command_ready("open calculator antigravity"))

    def test_listen_hold_stays_long_while_list_is_open(self):
        # Short named hold only after a closed list. An open list must
        # keep the unknown/long hold so later names are not cut off.
        self.assertFalse(listen_hold_named("open calculator,"))
        self.assertFalse(listen_hold_named("open calculator and"))
        self.assertFalse(listen_hold_named("open calculator, antigravity"))
        self.assertFalse(listen_hold_named("open calculator"))
        self.assertTrue(listen_hold_named("open calculator and notes"))
        self.assertTrue(listen_hold_named("open calculator, antigravity and notes"))

    def test_spoken_list_without_commas_stays_open(self):
        # Apple Speech has punctuation off, so the live partial is
        # "open calculator antigravity" — not "open calculator, antigravity".
        # That must stay mid-list until a real silence after the last name.
        from opener.settings import list_still_open

        self.assertTrue(list_still_open("open calculator"))
        self.assertTrue(list_still_open("open calculator antigravity"))
        self.assertTrue(list_still_open("open calculator antigravity and"))
        self.assertFalse(list_still_open("open calculator and notes"))
        self.assertFalse(list_still_open("open calculator, antigravity and notes"))
        self.assertFalse(listen_hold_named("open calculator"))
        self.assertFalse(listen_hold_named("open calculator antigravity"))
        self.assertTrue(listen_hold_named("open calculator and notes"))

    def test_asr_fragments_stay_open(self):
        # Live logs: Apple often emits just "Calculator" or "Gravity calculator"
        # mid-utterance. Those must not take the short named hold.
        from opener.settings import list_still_open

        self.assertTrue(list_still_open("Calculator"))
        self.assertTrue(list_still_open("Gravity calculator"))
        self.assertTrue(list_still_open("Open anti gravity"))
        self.assertTrue(list_still_open("Open Notes anti gravity"))
        self.assertFalse(list_still_open("open notes and safari"))
        self.assertFalse(listen_hold_named("Calculator"))
        self.assertFalse(listen_hold_named("Gravity calculator"))
        self.assertFalse(listen_hold_named("Open anti gravity"))


class SettingsNormalizeTests(unittest.TestCase):
    def test_defaults_are_complete(self):
        out = normalize_settings(None)
        self.assertEqual(out["listening_enabled"], True)
        self.assertEqual(out["wake_enabled"], True)
        self.assertEqual(out["hotkey_enabled"], True)
        self.assertEqual(out["hover_enabled"], True)
        self.assertEqual(out["click_enabled"], True)
        self.assertEqual(out["wake_phrases"], ["hey mac", "bhai mac"])
        self.assertEqual(out["hover_dwell_ms"], 500)
        self.assertEqual(
            out["hotkey"],
            {"key": "space", "key_code": 49, "modifiers": ["control", "option"]},
        )
        self.assertEqual(out["decision_backend"], "laya")

    def test_clamps_hover_dwell(self):
        self.assertEqual(normalize_settings({"hover_dwell_ms": 10})["hover_dwell_ms"], 100)
        self.assertEqual(normalize_settings({"hover_dwell_ms": 9000})["hover_dwell_ms"], 2000)
        self.assertEqual(normalize_settings({"hover_dwell_ms": 750})["hover_dwell_ms"], 750)

    def test_unknown_backend_falls_back_to_laya(self):
        self.assertEqual(normalize_settings({"decision_backend": "jev"})["decision_backend"], "jev")
        self.assertEqual(normalize_settings({"decision_backend": "nope"})["decision_backend"], "laya")

    def test_wake_phrases_are_cleaned(self):
        out = normalize_settings({"wake_phrases": ["  Hey MAC ", "", "Okay Computer"]})
        self.assertEqual(out["wake_phrases"], ["hey mac", "okay computer"])

    def test_empty_wake_phrases_restore_defaults(self):
        out = normalize_settings({"wake_phrases": []})
        self.assertEqual(out["wake_phrases"], ["hey mac", "bhai mac"])

    def test_hotkey_normalizes_modifiers(self):
        out = normalize_hotkey({"key": "Space", "modifiers": ["ctrl", "alt", "bogus"]})
        self.assertEqual(out["key"], "space")
        self.assertEqual(out["key_code"], 49)
        self.assertEqual(out["modifiers"], ["control", "option"])

    def test_hotkey_letter_gets_a_keycode(self):
        out = normalize_hotkey({"key": "n", "modifiers": ["command", "shift"]})
        self.assertEqual(out["key"], "n")
        self.assertEqual(out["key_code"], 45)
        self.assertEqual(out["modifiers"], ["command", "shift"])

    def test_listening_flags_are_bools(self):
        out = normalize_settings({"listening_enabled": 0, "wake_enabled": "no"})
        self.assertFalse(out["listening_enabled"])
        self.assertFalse(out["wake_enabled"])

    def test_trigger_toggles_default_on(self):
        out = normalize_settings(None)
        self.assertTrue(out["hotkey_enabled"])
        self.assertTrue(out["hover_enabled"])
        self.assertTrue(out["click_enabled"])
        self.assertTrue(out["wake_enabled"])

    def test_trigger_toggles_can_be_turned_off(self):
        out = normalize_settings(
            {
                "hotkey_enabled": False,
                "hover_enabled": "off",
                "click_enabled": 0,
                "wake_enabled": "no",
            }
        )
        self.assertFalse(out["hotkey_enabled"])
        self.assertFalse(out["hover_enabled"])
        self.assertFalse(out["click_enabled"])
        self.assertFalse(out["wake_enabled"])

    def test_wake_off_means_no_always_on_mic(self):
        self.assertFalse(mic_needed({"listening_enabled": True, "wake_enabled": False}))
        self.assertTrue(mic_needed({"listening_enabled": True, "wake_enabled": True}))
        self.assertFalse(mic_needed({"listening_enabled": False, "wake_enabled": True}))


class HoverArmTests(unittest.TestCase):
    def test_parked_pointer_does_not_reopen_after_listen(self):
        # Collapse + island cover fire a fake exit then a fake enter while
        # the pointer is still in the notch. That pair must not start another
        # listen. Only a real leave + re-enter may schedule.
        armed = True
        armed, schedule = hover_apply("start", armed, cursor_in_hit=True)
        self.assertFalse(armed)
        self.assertFalse(schedule)

        armed, schedule = hover_apply("exit", armed, cursor_in_hit=True)
        self.assertFalse(armed)
        self.assertFalse(schedule)

        armed, schedule = hover_apply("enter", armed, cursor_in_hit=True)
        self.assertFalse(armed)
        self.assertFalse(schedule)

    def test_pointer_on_island_drop_is_still_parked(self):
        # After collapse the cursor often sits in the drop below the
        # menu-bar strip. That is still "on the island" — do not re-arm.
        armed, schedule = hover_apply("collapse", False, cursor_in_hit=True)
        self.assertFalse(armed)
        self.assertFalse(schedule)
        armed, schedule = hover_apply("exit", armed, cursor_in_hit=True)
        self.assertFalse(armed)
        armed, schedule = hover_apply("enter", armed, cursor_in_hit=True)
        self.assertFalse(schedule)

    def test_real_leave_then_rehover_schedules_listen(self):
        armed = False
        armed, schedule = hover_apply("exit", armed, cursor_in_hit=False)
        self.assertTrue(armed)
        self.assertFalse(schedule)

        armed, schedule = hover_apply("enter", armed, cursor_in_hit=True)
        self.assertTrue(armed)
        self.assertTrue(schedule)

    def test_leave_early_cancels_without_disarming_fresh_hover(self):
        armed, schedule = hover_apply("enter", True, cursor_in_hit=True)
        self.assertTrue(schedule)
        armed, schedule = hover_apply("exit", armed, cursor_in_hit=False)
        self.assertTrue(armed)
        self.assertFalse(schedule)

    def test_hover_does_not_schedule_while_island_is_up(self):
        _, schedule = hover_apply("enter", True, cursor_in_hit=True, expanded=True)
        self.assertFalse(schedule)
        _, schedule = hover_apply("enter", True, cursor_in_hit=True, busy=True)
        self.assertFalse(schedule)

    def test_hover_respects_toggles(self):
        _, schedule = hover_apply(
            "enter", True, cursor_in_hit=True, listening_enabled=False
        )
        self.assertFalse(schedule)
        _, schedule = hover_apply(
            "enter", True, cursor_in_hit=True, hover_enabled=False
        )
        self.assertFalse(schedule)

    def test_collapse_while_parked_stays_disarmed(self):
        armed, schedule = hover_apply("collapse", False, cursor_in_hit=True)
        self.assertFalse(armed)
        self.assertFalse(schedule)
        armed, schedule = hover_apply("collapse", False, cursor_in_hit=False)
        self.assertTrue(armed)
        self.assertFalse(schedule)


if __name__ == "__main__":
    unittest.main()
