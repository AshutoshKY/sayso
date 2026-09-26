import unittest

from opener.listen import listen_once


class ListenOnceTests(unittest.TestCase):
    def test_returns_stripped_stdout(self):
        class Result:
            stdout = "  open notes  \n"
            stderr = ""
            returncode = 0

        text = listen_once(
            binary="/tmp/fake-listen",
            runner=lambda *a, **k: Result(),
        )
        self.assertEqual(text, "open notes")

    def test_missing_binary_is_empty(self):
        self.assertEqual(listen_once(binary="/no/such/listen"), "")


if __name__ == "__main__":
    unittest.main()
