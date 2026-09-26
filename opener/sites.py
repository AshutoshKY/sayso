"""Host-side parse of 'open youtube in brave' / clipboard. Laya still names the app."""

import re

from opener.alias import resolve_alias, spoken_key


_OPEN_PREFIX = re.compile(r"(?i)^(open|launch|start|run)\s+")
_IN_APP = re.compile(r"(?i)^(.+?)\s+in\s+(.+)$")
_BARE_CLIPBOARD = re.compile(r"(?i)^(the\s+)?clipboard$")
_DOT_HOST = re.compile(
    r"(?i)\b((?:www\.)?[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z]{2,})+)\b"
)

SITES = (
    (("youtube", "you tube", "youtu.be", "youtube.com"), "https://www.youtube.com", "YouTube"),
    (("gmail", "g mail", "gmail.com"), "https://mail.google.com", "Gmail"),
    (("github", "git hub", "github.com"), "https://github.com", "GitHub"),
    (("twitter", "x.com", "twitter.com"), "https://x.com", "X"),
    (("reddit", "reddit.com"), "https://www.reddit.com", "Reddit"),
    (("chatgpt", "chat gpt", "chat.openai.com"), "https://chatgpt.com", "ChatGPT"),
    (("google.com",), "https://www.google.com", "Google"),
)

_HOST_LABEL = {
    "youtube.com": "YouTube",
    "www.youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "github.com": "GitHub",
    "www.github.com": "GitHub",
    "mail.google.com": "Gmail",
    "gmail.com": "Gmail",
    "google.com": "Google",
    "www.google.com": "Google",
    "x.com": "X",
    "twitter.com": "X",
    "reddit.com": "Reddit",
    "www.reddit.com": "Reddit",
    "chatgpt.com": "ChatGPT",
    "chat.openai.com": "ChatGPT",
}


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _host_url(host):
    host = (host or "").strip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None
    return "https://%s" % host


def parse_open_target(text):
    """Return {kind, url, app_hint, label} or None if this is a plain app open."""
    lowered = _OPEN_PREFIX.sub("", _norm(text))
    if not lowered:
        return None
    app_hint = None
    payload = lowered
    match = _IN_APP.match(lowered)
    if match:
        payload = _norm(match.group(1))
        app_hint = _norm(match.group(2))
    if _BARE_CLIPBOARD.match(payload):
        return {
            "kind": "clipboard",
            "url": "clipboard",
            "app_hint": app_hint,
            "label": "clipboard",
        }
    for aliases, url, label in SITES:
        for alias in aliases:
            if re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", payload):
                return {
                    "kind": "url",
                    "url": url,
                    "app_hint": app_hint,
                    "label": label,
                }
    host = _DOT_HOST.search(payload)
    if host:
        url = _host_url(host.group(1))
        if url:
            return {
                "kind": "url",
                "url": url,
                "app_hint": app_hint,
                "label": label_for(url),
            }
    return None


def laya_text(text, catalog=None):
    """Utterance Laya should see: app name only, site/clipboard stripped."""
    target = parse_open_target(text)
    if not target:
        return text
    hint = target.get("app_hint")
    if hint:
        named = None
        if catalog:
            named = resolve_alias(hint, catalog) or (
                spoken_key(hint) if spoken_key(hint) in catalog else None
            )
        label = (catalog or {}).get(named, {}).get("say") if named else None
        return "open %s" % (label or hint)
    return text


def label_for(url):
    if not url or url == "clipboard":
        return "the clipboard"
    host = re.sub(r"^https?://", "", url).split("/", 1)[0].lower()
    if host in _HOST_LABEL:
        return _HOST_LABEL[host]
    bare = host[4:] if host.startswith("www.") else host
    if bare in _HOST_LABEL:
        return _HOST_LABEL[bare]
    return bare or "the page"
