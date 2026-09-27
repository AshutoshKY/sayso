import json
import unittest
from io import StringIO
from unittest import mock

from opener.engine import ENGINE_HOST, ENGINE_JEV, ENGINE_LAYA, engine_spec, predict_for
from opener.server import decide_payload


CATALOG = {
    "notes": {"say": "Notes", "criteria": "Notes.app", "aliases": ["notes"]},
    "safari": {"say": "Safari", "criteria": "Safari.app", "aliases": ["safari"]},
}


class EngineSpecTests(unittest.TestCase):
    def test_host_is_available_without_docker_or_token(self):
        spec = engine_spec("host")
        self.assertEqual(spec["engine"], ENGINE_HOST)
        self.assertTrue(spec["available"])
        self.assertFalse(spec["needs_docker"])
        self.assertIsNone(spec["url"])
        self.assertIsNone(spec["model"])
        self.assertIsNone(spec["token"])

    def test_laya_uses_local_systemone_and_english(self):
        spec = engine_spec("laya")
        self.assertEqual(spec["engine"], ENGINE_LAYA)
        self.assertEqual(spec["url"], "http://127.0.0.1:8001/v1/systemone")
        self.assertEqual(spec["model"], "english")
        self.assertIsNone(spec["token"])
        self.assertTrue(spec["needs_docker"])

    def test_jev_uses_typesafe_and_requires_token(self):
        spec = engine_spec("jev", token="abc")
        self.assertEqual(spec["engine"], ENGINE_JEV)
        self.assertEqual(spec["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(spec["model"], "jev-latest")
        self.assertEqual(spec["token"], "abc")
        self.assertFalse(spec["needs_docker"])

    def test_jev_without_token_is_unavailable(self):
        spec = engine_spec("jev", token="")
        self.assertEqual(spec["engine"], ENGINE_JEV)
        self.assertFalse(spec["available"])
        self.assertEqual(spec["reason"], "missing-key")

    def test_unknown_engine_is_unavailable(self):
        spec = engine_spec("nope")
        self.assertFalse(spec["available"])
        self.assertEqual(spec["reason"], "unknown-engine")


class DecidePayloadEngineTests(unittest.TestCase):
    def test_jev_with_token_calls_predict_and_opens(self):
        called = []

        def predict(text, catalog):
            called.append(text)
            return {
                "app": {"choice": "notes", "answer_confidence": 0.95, "probabilities": {}},
            }

        out = decide_payload(
            "open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="jev",
            token="abc",
        )
        self.assertEqual(called, ["open notes"])
        self.assertEqual(out["action"], "open")
        self.assertEqual(out["app"], "notes")
        self.assertEqual(out["reason"], "laya")

    def test_host_opens_named_app_without_calling_predict(self):
        def predict(text, catalog):
            raise AssertionError("host must not call a model")

        out = decide_payload(
            "open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="host",
        )
        self.assertEqual(out["action"], "open")
        self.assertEqual(out["app"], "notes")
        self.assertEqual(out["reason"], "host")
        self.assertIsNone((out.get("timing") or {}).get("laya_ms"))

    def test_host_paraphrase_does_not_open(self):
        def predict(text, catalog):
            raise AssertionError("host must not call a model")

        out = decide_payload(
            "jot something down",
            catalog=CATALOG,
            predict_fn=predict,
            backend="host",
        )
        self.assertEqual(out["action"], "ask")
        self.assertIsNone(out["app"])
        self.assertEqual(out["reason"], "host")

    def test_host_still_parses_volume(self):
        def predict(text, catalog):
            raise AssertionError("host must not call a model")

        out = decide_payload(
            "increase volume by 2",
            catalog=CATALOG,
            predict_fn=predict,
            backend="host",
        )
        self.assertEqual(out["action"], "system")
        self.assertEqual(out["system"][0]["verb"], "volume_up")
        self.assertEqual(out["reason"], "host")

    def test_jev_without_token_does_not_call_predict(self):
        def predict(text, catalog):
            raise AssertionError("missing key must not call Jev")

        out = decide_payload(
            "open notes",
            catalog=CATALOG,
            predict_fn=predict,
            backend="jev",
            token="",
        )
        self.assertEqual(out["action"], "ask")
        self.assertEqual(out["reason"], "backend-unavailable")
        self.assertIn("Jev", out["spoken"])

    def test_unknown_backend_still_refuses(self):
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

    def test_predict_for_jev_passes_url_model_token(self):
        captured = {}

        def fake_predict(text, catalog, url=None, model="english", token=None, **kwargs):
            captured.update({"text": text, "url": url, "model": model, "token": token})
            return {"app": {"choice": "notes", "answer_confidence": 1.0, "probabilities": {}}}

        fn = predict_for("jev", token="abc", predict_fn=fake_predict)
        fn("open notes", CATALOG)
        self.assertEqual(captured["url"], "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(captured["model"], "jev-latest")
        self.assertEqual(captured["token"], "abc")

    def test_predict_for_laya_uses_local_english_and_no_token(self):
        captured = {}

        def fake_predict(text, catalog, url=None, model="english", token=None, **kwargs):
            captured.update({"url": url, "model": model, "token": token})
            return {"app": {"choice": "notes", "answer_confidence": 1.0, "probabilities": {}}}

        fn = predict_for("laya", predict_fn=fake_predict)
        fn("open notes", CATALOG)
        self.assertEqual(captured["url"], "http://127.0.0.1:8001/v1/systemone")
        self.assertEqual(captured["model"], "english")
        self.assertIsNone(captured["token"])


class DecideCLITests(unittest.TestCase):
    def test_cli_reads_stdin_and_prints_decision(self):
        from opener import __main__ as main

        body = {
            "text": "open notes",
            "catalog": CATALOG,
            "backend": "jev",
            "token": "abc",
            "running": [],
            "pending": [],
            "settings": {"decision_backend": "jev"},
        }

        def predict(text, catalog):
            return {"app": {"choice": "notes", "answer_confidence": 0.9, "probabilities": {}}}

        stdin = StringIO(json.dumps(body))
        stdout = StringIO()
        with mock.patch.object(main, "predict_for", return_value=predict):
            code = main.main(["decide"], stdin=stdin, stdout=stdout)
        self.assertEqual(code, 0)
        out = json.loads(stdout.getvalue())
        self.assertEqual(out["action"], "open")
        self.assertEqual(out["app"], "notes")

    def test_cli_without_subcommand_still_exits_nonzero_without_server(self):
        from opener import __main__ as main

        stderr = StringIO()
        code = main.main([], stdin=StringIO(), stdout=StringIO(), stderr=stderr)
        self.assertEqual(code, 2)
        self.assertNotIn("docker compose up", stderr.getvalue().lower())


class EngineEnsureTests(unittest.TestCase):
    def test_ensure_laya_starts_only_upstream(self):
        from opener.dockerutil import CONTAINER, ensure_laya

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
                raise OSError("down")
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

    def test_compose_declares_only_laya_upstream(self):
        from pathlib import Path

        text = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text()
        self.assertIn("laya-upstream", text)
        self.assertNotIn("laya-opener", text)
        self.assertNotIn("8010", text)


if __name__ == "__main__":
    unittest.main()
