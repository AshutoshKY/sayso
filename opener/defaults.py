import pathlib
import plistlib


LAUNCH_SERVICES = (
    pathlib.Path.home()
    / "Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist"
)


def default_browser_id(handlers, catalog):
    """Map the http URL handler to a catalog app id. Safari if unknown."""
    bundles = {
        (spec.get("bundle") or "").lower(): app_id
        for app_id, spec in catalog.items()
        if spec.get("bundle")
    }
    for handler in handlers or []:
        if handler.get("scheme") != "http":
            continue
        bundle = (handler.get("bundle") or "").lower()
        if bundle in bundles:
            return bundles[bundle]
    return "safari"


def read_launch_services_handlers(path=None):
    target = pathlib.Path(path) if path else LAUNCH_SERVICES
    if not target.exists():
        return []
    data = plistlib.loads(target.read_bytes())
    out = []
    for raw in data.get("LSHandlers") or []:
        scheme = raw.get("LSHandlerURLScheme")
        bundle = raw.get("LSHandlerRoleAll") or raw.get("LSHandlerRoleViewer")
        if scheme and bundle:
            out.append({"scheme": scheme, "bundle": bundle})
    return out
