"""In-app decide CLI. Swift posts one JSON object on stdin."""

import json
import sys

from opener.engine import predict_for
from opener.server import decide_payload


def main(argv=None, stdin=None, stdout=None, stderr=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    stdin = sys.stdin if stdin is None else stdin
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    if not argv or argv[0] != "decide":
        print(
            "Usage: python3 -m opener decide < request.json\n"
            "Decide runs in the Sayso app. Laya inference is docker start laya-upstream.",
            file=stderr,
        )
        return 2
    try:
        body = json.loads(stdin.read() or "{}")
    except json.JSONDecodeError:
        print(json.dumps({"action": "ask", "reason": "invalid-json", "spoken": "Bad request."}), file=stdout)
        return 1
    settings = body.get("settings") or {}
    backend = body.get("backend") or settings.get("decision_backend") or "host"
    token = body.get("token") or ""
    payload = decide_payload(
        body.get("text") or "",
        catalog=body.get("catalog"),
        defaults=body.get("defaults") or {},
        predict_fn=predict_for(backend, token=token, laya_url=body.get("laya_url")),
        backend=backend,
        settings=settings,
        running=body.get("running") or [],
        pending=body.get("pending") or [],
        token=token,
    )
    print(json.dumps(payload), file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
