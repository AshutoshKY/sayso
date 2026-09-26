import os
import re
from pathlib import Path


DEFAULT_ROOTS = (
    "/Applications",
    "/System/Applications",
    "/System/Applications/Utilities",
    "/System/Cryptexes/App/System/Applications",
    str(Path.home() / "Applications"),
)

_SKIP = {
    "utilities",
    "relocated items",
    "garageband wrapper",
}
_SKIP_SUFFIX = (
    " helper",
    " uninstaller",
    " installer",
    " updater",
    " crash reporter",
)
_GENERIC_TAILS = {
    "video",
    "editor",
    "player",
    "manager",
    "helper",
    "studio",
    "browser",
    "launcher",
}
_PRODUCT_TAILS = {
    "warp",
    "desktop",
    "helper",
    "pro",
    "lite",
    "ide",
}
_COMPOUND = (
    ("cloudflare", "cloud flare"),
    ("whatsapp", "whats app"),
    ("facetime", "face time"),
    ("antigravity", "anti gravity"),
    ("textedit", "text edit"),
)
_SPEECH = {
    "hermes": ("her mes", "her mess", "hermits", "hurmez"),
}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def _split_camel(name):
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", name or "")


def aliases_for(name):
    stem = (name or "").strip()
    if not stem:
        return []
    lower = stem.lower()
    spaced_camel = _split_camel(stem).lower()
    tokens = [part for part in re.split(r"[^a-z0-9]+", spaced_camel) if part]
    spaced = " ".join(tokens)
    compact = "".join(tokens) or slug(stem)
    out = []
    for alias in (lower, spaced_camel, spaced, compact):
        if alias and alias not in out:
            out.append(alias)
    if spaced.endswith(" edit"):
        editor = spaced + "or"
        if editor not in out:
            out.append(editor)
    # Short names like Hermes / Notes are not English plurals.
    if (
        spaced.endswith("s")
        and len(spaced) >= 7
        and not spaced.endswith(("ss", "us", "is", "os"))
    ):
        singular = spaced[:-1]
        if singular and singular not in out:
            out.append(singular)
    apple_short = {"tv", "mail", "notes", "music", "maps", "photos", "calendar", "podcasts"}
    if compact in apple_short:
        apple = "apple " + (spaced or compact)
        if apple not in out:
            out.append(apple)
    if len(tokens) >= 2:
        head = " ".join(tokens[:2])
        if head not in out:
            out.append(head)
        tail = tokens[-1]
        if len(tail) >= 8 and tail not in _GENERIC_TAILS and tail not in out:
            out.append(tail)
        first = tokens[0]
        if (
            first not in out
            and first not in _GENERIC_TAILS
            and (len(first) >= 10 or (len(first) >= 8 and tail in _PRODUCT_TAILS))
        ):
            out.append(first)
    for token, exploded in _COMPOUND:
        if token not in compact:
            continue
        rest = compact.replace(token, "", 1)
        for form in (exploded, token, (exploded + " " + rest).strip() if rest else exploded):
            if form and form not in out:
                out.append(form)
    for form in _SPEECH.get(compact) or ():
        if form not in out:
            out.append(form)
    return out


_COMMON_SPEECH = {
    "notes",
    "mail",
    "safari",
    "chrome",
    "calendar",
    "photos",
    "maps",
    "messages",
    "finder",
    "music",
    "settings",
    "terminal",
    "preview",
}


def _is_unusual(app_id, spec):
    compact = slug(app_id)
    if compact in _SPEECH:
        return True
    if any(token in compact for token, _ in _COMPOUND):
        return True
    official = {
        compact,
        slug(spec.get("say") or ""),
        slug(spec.get("open") or ""),
    }
    return any(slug(alias) not in official for alias in spec.get("aliases") or [])


def _phrase_priority(phrase, app_id, spec):
    lowered = (phrase or "").strip().lower()
    compact = slug(lowered)
    if compact in _SPEECH or lowered in _SPEECH.get(slug(app_id), ()):
        return 0
    if any(token in slug(app_id) or token in compact for token, _ in _COMPOUND):
        return 1
    if _is_unusual(app_id, spec) and compact not in _COMMON_SPEECH:
        return 2
    return 3


def speech_phrases(catalog, limit=100):
    """Short phrases Apple Speech should bias toward. Cap 100."""
    seen = set()
    scored = []
    for app_id, spec in (catalog or {}).items():
        candidates = [spec.get("say") or spec.get("open") or app_id]
        candidates.extend(spec.get("aliases") or [])
        for raw in candidates:
            phrase = (raw or "").strip()
            if len(phrase) < 3 or len(phrase) > 32:
                continue
            key = phrase.lower()
            if key in seen:
                continue
            seen.add(key)
            scored.append((_phrase_priority(phrase, app_id, spec), key, phrase))
    scored.sort()
    return [phrase for _, _, phrase in scored[:limit]]


def _skip(stem):
    lowered = stem.lower().strip()
    if lowered in _SKIP or lowered.startswith("."):
        return True
    return any(lowered.endswith(suffix) for suffix in _SKIP_SUFFIX)


def _criteria(stem, aliases):
    sample = ", ".join(aliases[:4]) or stem
    return "the app %s. %s" % (stem, sample)


def scan_apps(roots=None, listdir=None, is_dir=None):
    """Top-level .app bundles under the usual Mac install roots."""
    listdir = listdir or os.listdir
    is_dir = is_dir or (lambda path: Path(path).is_dir())
    out = {}
    for root in roots or DEFAULT_ROOTS:
        try:
            names = listdir(root)
        except OSError:
            continue
        for name in names:
            if not name.endswith(".app"):
                continue
            path = os.path.join(root, name)
            if not is_dir(path):
                continue
            stem = name[:-4]
            if _skip(stem):
                continue
            app_id = slug(stem)
            if not app_id or app_id in out:
                continue
            aliases = aliases_for(stem)
            out[app_id] = {
                "open": stem,
                "say": stem,
                "paths": [path],
                "aliases": aliases,
                "criteria": _criteria(stem, aliases),
            }
    return out


def merge_scanned(curated, scanned):
    """Keep curated specs; add scanned apps that are not already present."""
    out = {key: dict(spec) for key, spec in (curated or {}).items()}
    known_paths = set()
    known_bundles = set()
    for spec in out.values():
        known_paths.update(spec.get("paths") or [])
        if spec.get("path"):
            known_paths.add(spec["path"])
        if spec.get("bundle"):
            known_bundles.add(spec["bundle"])
    for app_id, spec in (scanned or {}).items():
        paths = spec.get("paths") or []
        if any(path in known_paths for path in paths):
            continue
        if spec.get("bundle") and spec["bundle"] in known_bundles:
            continue
        key = app_id
        n = 2
        while key in out:
            key = "%s%s" % (app_id, n)
            n += 1
        item = dict(spec)
        out[key] = item
        known_paths.update(paths)
        if item.get("bundle"):
            known_bundles.add(item["bundle"])
    return out
