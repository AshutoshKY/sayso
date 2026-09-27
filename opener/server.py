"""Decide payload + optional HTTP wrapper. Product path is python3 -m opener decide."""

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import urlopen

from opener.catalog import APPS
from opener.client import predict
from opener.engine import engine_spec, unavailable_payload
from opener.loop import handle_utterance, spoken
from opener.settings import normalize_settings


LAYA_HEALTH = os.environ.get("LAYA_HEALTH", "http://127.0.0.1:8001/health")
HOST = os.environ.get("OPENER_HOST", "0.0.0.0")
PORT = int(os.environ.get("OPENER_PORT", "8010"))


def _laya_ok(timeout=2):
    try:
        with urlopen(LAYA_HEALTH, timeout=timeout) as resp:
            return "ok" in resp.read().decode()
    except (URLError, OSError, TimeoutError):
        return False


def decide_payload(
    text,
    catalog=None,
    defaults=None,
    predict_fn=None,
    backend=None,
    settings=None,
    running=None,
    pending=None,
    token=None,
):
    uttered = (text or "").strip()
    if not uttered:
        return {
            "action": "ask",
            "app": None,
            "system": [],
            "reason": "empty",
            "spoken": "Which app should I open?",
        }
    cfg = normalize_settings(settings)
    requested = backend if backend is not None else cfg["decision_backend"]
    engine = str(requested or "host").strip().lower() or "host"
    cfg["decision_backend"] = engine
    spec = engine_spec(engine, token=token)
    cat = catalog if catalog is not None else APPS
    pred = predict_fn or predict
    timed = {"laya_ms": None}
    host_only = spec["engine"] == "host"

    def wrapped(text, catalog):
        if host_only:
            raise AssertionError("host must not call a model")
        if not spec["available"]:
            return {
                "intent": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
                "app": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
                "system": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
            }
        started = time.perf_counter()
        out = pred(text, catalog)
        timed["laya_ms"] = round((time.perf_counter() - started) * 1000, 1)
        return out

    started = time.perf_counter()
    decision = handle_utterance(
        uttered,
        cat,
        defaults or {},
        wrapped,
        settings=cfg,
        running=set(running or []),
        pending=list(pending or []),
    )
    total_ms = round((time.perf_counter() - started) * 1000, 1)
    if host_only:
        if decision.reason in ("laya", "unspecified", "which-app", "not-launch"):
            decision.reason = "host"
    elif not spec["available"] and timed["laya_ms"] is None and decision.reason not in (
        "host",
        "clipboard",
        "confirm",
        "wake",
        "stop",
        "empty",
    ):
        # Host-parsed volume / clipboard / yes-no never need a model.
        # App prediction with a missing Jev key or unknown engine still refuses.
        return unavailable_payload(spec)
    payload = {
        "action": decision.action,
        "app": decision.app,
        "apps": decision.apps,
        "pending": decision.pending,
        "url": decision.url,
        "system": decision.system,
        "reason": decision.reason,
        "spoken": spoken(decision, cat),
        "timing": {"total_ms": total_ms, "laya_ms": timed["laya_ms"]},
    }
    print(
        "decide %r -> %s %s (%s) %.0fms laya=%.0fms"
        % (
            uttered,
            decision.action,
            decision.app,
            decision.reason,
            total_ms,
            timed["laya_ms"] or 0,
        ),
        file=sys.stderr,
        flush=True,
    )
    return payload


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def _json(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?", 1)[0] != "/health":
            self._json(404, {"error": "not found"})
            return
        # Always 200 once this process is up. A brief Laya blip must not
        # mark the container unhealthy — Docker Desktop treats that as a
        # crash (healthcheck exec_die + restart). Clients still see
        # ``laya: false`` and can wait.
        laya = _laya_ok()
        self._json(200, {"status": "ok" if laya else "degraded", "laya": laya})

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/decide":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid json"})
            return
        text = body.get("text") or ""
        catalog = body.get("catalog") or APPS
        defaults = body.get("defaults") or {}
        settings = body.get("settings") or {}
        backend = body.get("backend") or settings.get("decision_backend")
        running = body.get("running") or []
        pending = body.get("pending") or []
        self._json(
            200,
            decide_payload(
                text,
                catalog=catalog,
                defaults=defaults,
                backend=backend,
                settings=settings,
                running=running,
                pending=pending,
            ),
        )


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("laya-opener listening on %s:%s" % (HOST, PORT), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
