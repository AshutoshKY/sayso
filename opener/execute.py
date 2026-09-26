import subprocess


def _invoke(runner, cmd):
    try:
        return runner(cmd, check=False)
    except TypeError:
        return runner(cmd)


def open_app(app_id, catalog, runner=None):
    spec = (catalog or {}).get(app_id) or {}
    name = spec.get("open")
    if not name:
        return False
    _invoke(runner or subprocess.run, ["open", "-a", name])
    return True


def speak(text, runner=None):
    if not text:
        return False
    _invoke(runner or subprocess.run, ["say", text])
    return True
