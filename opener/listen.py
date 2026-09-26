import os
import subprocess
from pathlib import Path


def default_binary():
    return Path(__file__).resolve().parents[1] / "native" / "listen"


def listen_once(binary=None, runner=None, env=None, timeout=20):
    """Run the on-device Speech helper. Returns transcript or ''."""
    path = Path(binary) if binary else default_binary()
    run = runner or subprocess.run
    if runner is None and not path.exists():
        return ""
    merged = os.environ.copy()
    if env:
        merged.update(env)
    result = run(
        [str(path)],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=merged,
    )
    return (result.stdout or "").strip()
