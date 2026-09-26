import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


CONTAINER = "laya-upstream"
OPENER_CONTAINER = "laya-opener"
HEALTH_URL = "http://127.0.0.1:8001/health"
OPENER_HEALTH = "http://127.0.0.1:8010/health"
COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.yml"


def _ok(url, fetcher=None, timeout=2):
    get = fetcher or (lambda target, timeout=timeout: urlopen(target, timeout=timeout))
    try:
        with get(url, timeout=timeout) as resp:
            body = resp.read().decode()
        return "ok" in body
    except (URLError, OSError, TimeoutError, TypeError):
        return False


def health_ok(fetcher=None, timeout=2):
    return _ok(HEALTH_URL, fetcher=fetcher, timeout=timeout)


def opener_ok(fetcher=None, timeout=2):
    return _ok(OPENER_HEALTH, fetcher=fetcher, timeout=timeout)


def ensure_laya(runner=None, fetcher=None, sleeps=None, tries=20):
    """Start Laya + this project's opener. Never launches a host Python server."""
    if health_ok(fetcher=fetcher) and opener_ok(fetcher=fetcher):
        return True
    run = runner or subprocess.run
    if not health_ok(fetcher=fetcher):
        run(["docker", "start", CONTAINER], check=False)
    if not opener_ok(fetcher=fetcher):
        run(["docker", "start", OPENER_CONTAINER], check=False)
    pause = sleeps or (lambda _: None)
    for _ in range(tries):
        if health_ok(fetcher=fetcher) and opener_ok(fetcher=fetcher):
            return True
        pause(0.5)
    compose = str(COMPOSE)
    if Path(compose).exists():
        if health_ok(fetcher=fetcher):
            run(["docker", "compose", "-f", compose, "up", "-d", "--no-deps", "opener"], check=False)
        else:
            run(["docker", "compose", "-f", compose, "up", "-d"], check=False)
        for _ in range(tries):
            if health_ok(fetcher=fetcher) and opener_ok(fetcher=fetcher):
                return True
            pause(0.5)
    return health_ok(fetcher=fetcher) and opener_ok(fetcher=fetcher)
