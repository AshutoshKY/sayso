import unittest
from urllib.error import URLError

from opener.dockerutil import CONTAINER, ensure_laya, health_ok


class HealthTests(unittest.TestCase):
    def test_ok_body(self):
        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"status":"ok"}'

        self.assertTrue(health_ok(fetcher=lambda url, timeout=2: Resp()))

    def test_down(self):
        def boom(url, timeout=2):
            raise URLError("down")

        self.assertFalse(health_ok(fetcher=boom))


class EnsureTests(unittest.TestCase):
    def test_starts_container_when_unhealthy_then_healthy(self):
        calls = []
        state = {"ok": False}

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"status":"ok"}'

        def fetcher(url, timeout=2):
            if not state["ok"]:
                raise URLError("down")
            return Resp()

        def runner(cmd, check=False):
            calls.append(cmd)
            if cmd[:2] == ["docker", "start"]:
                state["ok"] = True

        self.assertTrue(ensure_laya(runner=runner, fetcher=fetcher, sleeps=lambda _: None, tries=3))
        self.assertEqual(calls[0], ["docker", "start", CONTAINER])
        self.assertEqual(CONTAINER, "laya-upstream")
        started = [cmd[2] for cmd in calls if cmd[:2] == ["docker", "start"]]
        self.assertNotIn("laya-opener", started)


class ComposeFileTests(unittest.TestCase):
    def test_compose_declares_only_laya(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
        self.assertIn("laya-upstream", text)
        self.assertNotIn("laya-opener", text)
        self.assertNotIn("8010", text)
        self.assertIn("restart: unless-stopped", text)


if __name__ == "__main__":
    unittest.main()
