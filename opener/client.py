import json
import os
import re
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

from opener.alias import resolve_alias, spoken_key
from opener.system_cmd import SYSTEM_CRITERIA, looks_systemish


DEFAULT_URL = os.environ.get("LAYA_URL", "http://127.0.0.1:8001/v1/systemone")

INTENT_CRITERIA = {
    "launch": "user wants a macOS application launched or brought to the front right now",
    "chat": "greeting, thanks, small talk, weather, or a question that does not launch software",
    "refuse": "user does not want any app opened: don't, never, hate",
}

UNSPECIFIED = "greeting, weather, small talk, or an app that is not in this list."

# Daily set Laya calibrates well on. Extras join only when the utterance names them.
DAILY_IDS = (
    "notes",
    "reminders",
    "mail",
    "messages",
    "finder",
    "facetime",
    "calendar",
    "photos",
    "maps",
    "spotify",
    "music",
    "safari",
    "chrome",
    "brave",
)

EXTRA_CRITERIA = {
    "hermes": "the word hermes, her mess, or hermits as the desktop chat app",
    "cloudflarewarp": "cloudflare warp, cloud flare, or warp as the VPN app",
    "vscode": "vs code, vscode, visual studio code",
    "docker": "the word docker only",
    "whatsapp": "the word whatsapp only",
    "settings": "system settings, system preferences",
    "arc": "Arc browser. arc, ark, art as the browser name Arc",
    "claude": "the word claude only",
    "codex": "the word codex only",
    "preview": "the word preview only",
    "calculator": "the word calculator only",
    "terminal": "the word terminal only",
    "vlc": "the word vlc only",
    "vivaldi": "the word vivaldi only",
    "word": "microsoft word",
    "excel": "the word excel only",
    "tv": "apple tv, the tv app",
    "textedit": "textedit, text editor",
}

LAYA_CRITERIA = {
    "notes": "jot something down, write a note, apple notes",
    "reminders": "remind me later, a to-do, reminders",
    "mail": "send an email, inbox, mail",
    "messages": "send a text, imessage, messages",
    "finder": "where is that file, browse folders, finder",
    "facetime": "take a video call, facetime",
    "calendar": "the word calendar, show my calendar",
    "photos": "show my photos, photo library",
    "maps": "get directions, apple maps",
    "spotify": "the word spotify",
    "music": "play some music, apple music, play a song",
    "safari": "the word safari only",
    "chrome": "the word chrome only",
    "brave": "the word brave only",
    "unspecified": UNSPECIFIED,
}


def _word_match(alias, text):
    return re.search(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", text) is not None


def build_questions(catalog):
    criteria = {}
    for app_id, spec in catalog.items():
        text = spec.get("criteria") or app_id
        criteria[app_id] = text
    criteria["unspecified"] = UNSPECIFIED
    return {
        "intent": {
            "type": "choice",
            "instructions": "Is the user asking to launch a macOS app, refusing, or just talking?",
            "criteria": dict(INTENT_CRITERIA),
        },
        "app": {
            "type": "choice",
            "instructions": "Which installed app matches the request? Use unspecified if none of the named apps fit.",
            "criteria": criteria,
        },
    }


BROWSER_IDS = ("safari", "chrome", "brave", "arc", "vivaldi")
BROWSER_HINTS = (
    "browser",
    "chrome",
    "safari",
    "brave",
    "arc",
    "ark",
    "art",
    "vivaldi",
)
BROWSER_CRITERIA = {
    "arc": "Arc browser. arc, ark, art as the browser name Arc",
    "chrome": "the word chrome only",
    "safari": "the word safari only",
    "brave": "the word brave only",
    "vivaldi": "the word vivaldi only",
}


def _looks_like_browser(text):
    lowered = (text or "").lower()
    return any(_word_match(hint, lowered) for hint in BROWSER_HINTS)


def questions_for(text, catalog):
    """Installed daily apps, plus extras the utterance actually names.

    A system-ish utterance also gets the `system` choice head so paraphrases
    ("make it louder") resolve without a host regex for every phrasing.
    """
    questions = _app_questions(text, catalog)
    if looks_systemish(text):
        questions["system"] = {
            "type": "choice",
            "instructions": "Which Mac system control does the user want, if any? Use unspecified for pure app requests or chat.",
            "criteria": dict(SYSTEM_CRITERIA),
        }
    return questions


def _app_questions(text, catalog):
    catalog = catalog or {}
    if _looks_like_browser(text):
        criteria = {}
        for app_id in BROWSER_IDS:
            if app_id not in catalog:
                continue
            criteria[app_id] = (
                BROWSER_CRITERIA.get(app_id)
                or EXTRA_CRITERIA.get(app_id)
                or LAYA_CRITERIA.get(app_id)
                or app_id
            )
        criteria["unspecified"] = "not a web browser request"
        return {
            "app": {
                "type": "choice",
                "instructions": "Which browser is the user talking about? Open, close, quit, or force quit all name the same browser. Use unspecified if none fit.",
                "criteria": criteria,
            }
        }
    named = resolve_alias(text, catalog)
    if not named:
        compact = spoken_key(text)
        if compact and compact in catalog:
            named = compact
    if named:
        return {
            "app": {
                "type": "choice",
                "instructions": "Which app is the user talking about? Open, close, quit, or force quit all name the same app. Use unspecified if none fit.",
                "criteria": _named_criteria(named, catalog),
            }
        }
    criteria = {}
    for app_id in DAILY_IDS:
        spec = catalog.get(app_id)
        if spec is None:
            continue
        criteria[app_id] = LAYA_CRITERIA.get(app_id) or spec.get("criteria") or app_id
    criteria["unspecified"] = UNSPECIFIED
    return {
        "app": {
            "type": "choice",
            "instructions": "Which app is the user talking about? Open, close, quit, or force quit all name the same app. Use unspecified if none fit.",
            "criteria": criteria,
        }
    }


def _criteria_for(app_id, spec):
    return (
        EXTRA_CRITERIA.get(app_id)
        or LAYA_CRITERIA.get(app_id)
        or spec.get("criteria")
        or app_id
    )


_NAMED_DISTRACTORS = ("notes", "safari", "chrome", "reminders")


def _named_criteria(named, catalog):
    """Named hit plus a few distractors. Never a lone app + unspecified."""
    criteria = {named: _criteria_for(named, catalog.get(named) or {})}
    for app_id in list(_NAMED_DISTRACTORS) + list(DAILY_IDS):
        if app_id == named or app_id in criteria or app_id not in catalog:
            continue
        criteria[app_id] = _criteria_for(app_id, catalog.get(app_id) or {})
        if len(criteria) >= 4:
            break
    criteria["unspecified"] = UNSPECIFIED
    return criteria


def parse_answers(payload):
    answers = (payload or {}).get("answers") or {}
    out = {}
    for key in ("intent", "app", "system"):
        block = answers.get(key) or {}
        out[key] = {
            "choice": block.get("choice"),
            "answer_confidence": block.get("answer_confidence", block.get("confidence")),
            "probabilities": block.get("probabilities") or {},
        }
    return out


def predict(text, catalog, url=None, opener=None, timeout=30, model="english", token=None):
    target = url or DEFAULT_URL
    body = {
        "state": text,
        "questions": questions_for(text, catalog),
        "model": model,
    }
    headers = {"content-type": "application/json"}
    if token:
        headers["authorization"] = "Bearer %s" % token
    req = Request(
        target,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    do_open = opener or urlopen
    try:
        with do_open(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return {
            "intent": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
            "app": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
            "system": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
        }
    return parse_answers(payload)
