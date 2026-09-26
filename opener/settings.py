"""Shared settings + wake-word matching. Swift Settings.swift stays in lockstep."""

import re


DEFAULT_WAKE_PHRASES = ["hey mac", "bhai mac"]
KNOWN_BACKENDS = ("laya", "jev")
HOVER_DWELL_MIN_MS = 100
HOVER_DWELL_MAX_MS = 2000

# Apple Speech confusions for the default wake phrases only.
WAKE_FORMS = {
    "hey mac": ["hey mac", "hay mac", "hey mack", "hay mack"],
    "bhai mac": ["bhai mac", "bye mac", "by mac", "buy mac", "bai mac", "by mack", "bye mack"],
}

# Carbon virtual key codes used by RegisterEventHotKey.
KEY_CODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "9": 25,
    "7": 26,
    "8": 28,
    "0": 29,
    "o": 31,
    "u": 32,
    "i": 34,
    "p": 35,
    "return": 36,
    "l": 37,
    "j": 38,
    "k": 40,
    "n": 45,
    "m": 46,
    "tab": 48,
    "space": 49,
    "delete": 51,
    "escape": 53,
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
}

_MOD_ALIASES = {
    "ctrl": "control",
    "control": "control",
    "alt": "option",
    "opt": "option",
    "option": "option",
    "cmd": "command",
    "command": "command",
    "shift": "shift",
}
_VALID_MODS = ("control", "option", "command", "shift")

_FILLER = re.compile(r"^(?:um+|uh+|er+|ah+|hmm+)\s+", re.I)
_SPACES = re.compile(r"\s+")

DEFAULT_HOTKEY = {
    "key": "space",
    "key_code": 49,
    "modifiers": ["control", "option"],
}

DEFAULT_SETTINGS = {
    "listening_enabled": True,
    "wake_enabled": True,
    "hotkey_enabled": True,
    "hover_enabled": True,
    "click_enabled": True,
    "wake_phrases": list(DEFAULT_WAKE_PHRASES),
    "hover_dwell_ms": 500,
    "hotkey": dict(DEFAULT_HOTKEY),
    "decision_backend": "laya",
}


def _as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("", "0", "false", "no", "off", "n"):
        return False
    if text in ("1", "true", "yes", "on", "y"):
        return True
    return default


def _clean_text(text):
    lowered = _SPACES.sub(" ", (text or "").strip().lower()).strip()
    while True:
        trimmed = _FILLER.sub("", lowered).strip()
        if trimmed == lowered:
            break
        lowered = trimmed
    return lowered


def _forms(phrase):
    phrase = _SPACES.sub(" ", (phrase or "").strip().lower()).strip()
    if not phrase:
        return []
    out = []
    for item in [phrase] + list(WAKE_FORMS.get(phrase, [])):
        item = _SPACES.sub(" ", item.strip().lower()).strip()
        if item and item not in out:
            out.append(item)
    return out


def match_wake(text, phrases):
    """Return (hit, remainder). Wake phrases must be a prefix, not mid-utterance."""
    cleaned = _clean_text(text)
    if not cleaned:
        return False, ""
    candidates = []
    for phrase in phrases or []:
        candidates.extend(_forms(phrase))
    candidates.sort(key=lambda item: (-len(item), item))
    for phrase in candidates:
        if cleaned == phrase:
            return True, ""
        prefix = phrase + " "
        if cleaned.startswith(prefix):
            return True, cleaned[len(prefix) :].strip()
    return False, cleaned


def strip_wake(text, phrases):
    hit, rest = match_wake(text, phrases)
    if hit:
        return rest
    return (text or "").strip()


# How long a bare wake ("hey mac") waits for a following command before
# we treat it as listen-only. Apple's first partial is almost always the
# wake word alone; committing then drops "open safari".
WAKE_BARE_HOLD = 0.45


# After the wake, Apple often emits just the verb ("open") before the
# app name. That is not a command yet.
_INCOMPLETE_COMMAND = re.compile(
    r"(?i)^(force\s+quit|close|quit|kill|open|launch|start|run)(\s+(the|a|an|my|please))?$"
)
# Trailing list glue: the speaker is still naming apps.
_OPEN_LIST = re.compile(r"(?i)(?:,|\band\b|\bthen\b)\s*$")
# "open A and B" / "open A then B" is a finished list.
_CLOSED_LIST = re.compile(r"(?i)\b(?:and|then)\b")


def list_still_open(text):
    """True while more app names may still be spoken.

    Apple Speech has punctuation off and often drops the verb, so the
    live partial is ``Calculator`` or ``Gravity calculator`` — not a
    finished list. A list is closed only after ``and`` / ``then``.
    Anything else stays open until a real silence.
    """
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if _OPEN_LIST.search(cleaned):
        return True
    if _CLOSED_LIST.search(cleaned):
        return False
    return True


def command_ready(text):
    """True when a stripped remainder is enough to decide."""
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if _INCOMPLETE_COMMAND.match(cleaned):
        return False
    if _OPEN_LIST.search(cleaned):
        return False
    return True


def listen_hold_named(text):
    """Short silence hold only when the phrase names an app and is not mid-list."""
    cleaned = _clean_text(text)
    if not cleaned:
        return False
    if _INCOMPLETE_COMMAND.match(cleaned):
        return False
    if list_still_open(cleaned):
        return False
    return True


def wake_commit(text, phrases, elapsed, hold=WAKE_BARE_HOLD, final=False):
    """Decide what a streaming wake transcript should do.

    Returns:
      "ignore" — not a wake prefix
      "hold" — wake heard, but still waiting for a possible command
      ("go", remainder) — combined utterance, run the remainder now
      ("listen", "") — bare wake hung long enough; start a fresh listen

    Partial transcripts must not .go: the first named app or a
    system-ish phrase is still growing (\"open notes\" -> \"and safari\",
    \"increase volume\" -> \"by 2\"). Seed only on a closed list
    (and/then) or the final transcript.
    """
    hit, rest = match_wake(text, phrases)
    if not hit:
        return "ignore"
    # beginSeeded aborts the mic. A partial first name or a system-ish
    # fragment ("increase volume") must not commit or later words are lost.
    if rest and final:
        return ("go", rest)
    if elapsed >= hold and not rest:
        return ("listen", "")
    return "hold"


def normalize_hotkey(raw):
    data = raw if isinstance(raw, dict) else {}
    key = str(data.get("key") or DEFAULT_HOTKEY["key"]).strip().lower()
    if key not in KEY_CODES:
        key = DEFAULT_HOTKEY["key"]
    mods = []
    for item in data.get("modifiers") or []:
        mapped = _MOD_ALIASES.get(str(item).strip().lower())
        if mapped and mapped not in mods:
            mods.append(mapped)
    if not mods:
        mods = list(DEFAULT_HOTKEY["modifiers"])
    # Keep a stable canonical order.
    mods = [name for name in _VALID_MODS if name in mods]
    return {"key": key, "key_code": KEY_CODES[key], "modifiers": mods}


def _clean_phrases(raw):
    out = []
    for item in raw or []:
        phrase = _SPACES.sub(" ", str(item).strip().lower()).strip()
        if phrase and phrase not in out:
            out.append(phrase)
    return out or list(DEFAULT_WAKE_PHRASES)


def normalize_settings(raw):
    data = raw if isinstance(raw, dict) else {}
    hover = data.get("hover_dwell_ms", DEFAULT_SETTINGS["hover_dwell_ms"])
    try:
        hover = int(hover)
    except (TypeError, ValueError):
        hover = DEFAULT_SETTINGS["hover_dwell_ms"]
    hover = max(HOVER_DWELL_MIN_MS, min(HOVER_DWELL_MAX_MS, hover))
    backend = str(data.get("decision_backend") or DEFAULT_SETTINGS["decision_backend"]).strip().lower()
    if backend not in KNOWN_BACKENDS:
        backend = DEFAULT_SETTINGS["decision_backend"]
    return {
        "listening_enabled": _as_bool(data.get("listening_enabled"), True),
        "wake_enabled": _as_bool(data.get("wake_enabled"), True),
        "hotkey_enabled": _as_bool(data.get("hotkey_enabled"), True),
        "hover_enabled": _as_bool(data.get("hover_enabled"), True),
        "click_enabled": _as_bool(data.get("click_enabled"), True),
        "wake_phrases": _clean_phrases(data.get("wake_phrases", DEFAULT_WAKE_PHRASES)),
        "hover_dwell_ms": hover,
        "hotkey": normalize_hotkey(data.get("hotkey")),
        "decision_backend": backend,
    }


def mic_needed(raw):
    """Always-on mic is only for the wake-word trigger."""
    cfg = normalize_settings(raw)
    return bool(cfg["listening_enabled"] and cfg["wake_enabled"])


def hover_apply(
    event,
    armed,
    expanded=False,
    busy=False,
    listening_enabled=True,
    hover_enabled=True,
):
    """Advance hover arming. Returns (armed, should_schedule).

    A listen consumes the current hover. Collapse and island-cover
    tracking events (fake exit/enter) must stay disarmed. Re-arm only
    on a later genuine mouse-exit after the island has collapsed.
    """
    if event in ("start", "collapse"):
        return False, False
    if event == "exit":
        if expanded or busy:
            return False, False
        return True, False
    if event != "enter":
        return bool(armed), False
    if not (
        listening_enabled
        and hover_enabled
        and armed
        and not expanded
        and not busy
    ):
        return bool(armed), False
    return bool(armed), True
