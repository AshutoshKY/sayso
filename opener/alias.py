import re


_OPEN_PREFIX = re.compile(r"(?i)^(open|launch|start|run|force\s+quit|close|quit|kill)\s+")
_TRAILING_FILLER = re.compile(r"(?i)\s+(app|application|please)$")
_IN_APP = re.compile(r"(?i)^(.+?)\s+in\s+(.+)$")
_SITE_WORDS = (
    "youtube",
    "youtu.be",
    "google",
    "gmail",
    "github",
    "twitter",
    "reddit",
    "chatgpt",
    "clipboard",
)


def spoken_key(text):
    """Compact installed-id form of an utterance, dropping open/app filler."""
    lowered = (text or "").strip().lower()
    lowered = _OPEN_PREFIX.sub("", lowered)
    match = _IN_APP.match(lowered)
    if match:
        lowered = match.group(2)
    else:
        for site in _SITE_WORDS:
            lowered = re.sub(r"(?i)\b" + re.escape(site) + r"(?:\.com)?\b", " ", lowered)
        lowered = re.sub(r"(?i)\b[a-z0-9-]+\.(?:com|org|net|io|dev|app|ai)\b", " ", lowered)
    while True:
        trimmed = _TRAILING_FILLER.sub("", lowered)
        if trimmed == lowered:
            break
        lowered = trimmed
    return re.sub(r"[^a-z0-9]+", "", lowered)


_GENERIC_BROWSER = (
    "the browser",
    "a browser",
    "web browser",
    "my browser",
    "default browser",
)

_GENERIC_MUSIC = (
    "play some music",
    "play music",
    "some music",
    "play a song",
    "play a track",
)


def _word_match(alias, text):
    return re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text) is not None


def resolve_alias(text, catalog, defaults=None):
    """Return a catalog app id if the utterance names it, else None.

    Longer aliases win so "google chrome" is not eaten by a later "chrome".
    Generic phrases like "the browser" map through *defaults* only when no
    real product name is present.
    """
    lowered = (text or "").lower()
    hits = []
    for app_id, spec in catalog.items():
        aliases = spec.get("aliases") or [app_id]
        for alias in aliases:
            alias = alias.lower()
            if alias and _word_match(alias, lowered):
                hits.append((len(alias), app_id))
    key = spoken_key(lowered)
    if key and key in catalog:
        return key
    if hits:
        hits.sort(key=lambda item: (-item[0], item[1]))
        return hits[0][1]
    defaults = defaults or {}
    browser = defaults.get("browser")
    if browser and any(_word_match(phrase, lowered) for phrase in _GENERIC_BROWSER):
        return browser
    music = defaults.get("music")
    if music and any(_word_match(phrase, lowered) for phrase in _GENERIC_MUSIC):
        return music
    return None


def prefer_catalog_transcript(candidates, catalog):
    """Keep Apple's first named app; prefer the official spelling of that app."""
    texts = [item for item in (candidates or []) if item]
    if not texts:
        return ""
    first_named = None
    best = None
    best_score = None
    for index, text in enumerate(texts):
        named = resolve_alias(text, catalog)
        if not named:
            continue
        if first_named is None:
            first_named = named
        if named != first_named:
            continue
        spec = catalog.get(named) or {}
        official = [named]
        for key in ("say", "open"):
            if spec.get(key):
                official.append(spec[key])
        canon = any(_word_match(item.lower(), text.lower()) for item in official)
        score = (0 if canon else 1, index)
        if best_score is None or score < best_score:
            best_score = score
            best = text
    return best or texts[0]
