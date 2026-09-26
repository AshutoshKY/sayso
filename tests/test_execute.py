import unittest

from opener.execute import open_app, speak


class OpenAppTests(unittest.TestCase):
    def test_uses_open_dash_a_with_catalog_name(self):
        ran = []

        def runner(cmd, check=False):
            ran.append(cmd)
            return 0

        ok = open_app("notes", {"notes": {"open": "Notes"}}, runner=runner)
        self.assertTrue(ok)
        self.assertEqual(ran, [["open", "-a", "Notes"]])

    def test_unknown_app_does_not_run(self):
        ran = []
        ok = open_app("nope", {"notes": {"open": "Notes"}}, runner=ran.append)
        self.assertFalse(ok)
        self.assertEqual(ran, [])


class SpeakTests(unittest.TestCase):
    def test_uses_say(self):
        ran = []

        def runner(cmd, check=False):
            ran.append(cmd)
            return 0

        speak("Opening Notes.", runner=runner)
        self.assertEqual(ran, [["say", "Opening Notes."]])


if __name__ == "__main__":
    unittest.main()
