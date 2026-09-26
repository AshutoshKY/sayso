import re

from opener.alias import resolve_alias, spoken_key
from opener.policy import Decision, decide
from opener.settings import match_wake, normalize_settings
from opener.sites import laya_text, parse_open_target
from opener.system_cmd import from_laya as system_from_laya
from opener.system_cmd import label as system_label
from opener.system_cmd import parse as parse_system


_STOP = (
    "goodbye",
    "good bye",
    "bye",
    "stop listening",
    "that's all",
    "thats all",
    "quit listening",
    "go to sleep",
    "we're done",
    "we are done",
)

_PROTECTED = frozenset(("finder", "layaopener"))

_YES = (
    "yes",
    "yeah",
    "yep",
    "yup",
    "ok",
    "okay",
    "sure",
    "please",
    "do it",
    "open it",
    "open",
    "go ahead",
)

_NO = (
    "no",
    "nope",
    "nah",
    "don't",
    "dont",
    "do not",
    "cancel",
    "never",
    "stop",
)

_VERB_PREFIX = re.compile(
    r"(?i)^(force\s+quit|close|quit|kill|open|launch|start|run)\s+"
)
_BARE_VERB = re.compile(r"(?i)^(force\s+quit|close|quit|kill)$")
_CLOSE_VERBS = {
    "close": "close",
    "quit": "quit",
    "kill": "kill",
    "force quit": "kill",
}


def is_stop(text):
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(
        re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", lowered)
        for phrase in _STOP
    )


_SPLIT = re.compile(r"\s*(?:,|\band\b|\bthen\b)\s*", re.I)
_OPEN_PREFIX = re.compile(r"(?i)^(open|launch|start|run)\s+")


def exact_installed_id(text, catalog):
    compact = spoken_key(text)
    if compact and catalog and compact in catalog:
        return compact
    return None


def named_apps_in(text, catalog):
    """Installed ids named in utterance order (split on and / , / then)."""
    out = []
    for part in split_requests(text):
        for recovered in _named_in_part(part, catalog):
            if recovered not in out:
                out.append(recovered)
    return out


def _named_in_part(part, catalog):
    """Ids named in *part*, left-to-right. Do not compact the chunk —
    ``calculator antigravity`` is two ids, not one fake spoken_key."""
    tokens = re.findall(r"[a-z0-9]+", (part or "").lower())
    if not tokens or not catalog:
        return []
    aliases = []
    for app_id, spec in catalog.items():
        names = [app_id, (spec or {}).get("say") or "", (spec or {}).get("open") or ""]
        names.extend((spec or {}).get("aliases") or [])
        for name in names:
            words = re.findall(r"[a-z0-9]+", str(name).lower())
            if words:
                aliases.append((len(words), words, app_id))
    aliases.sort(key=lambda item: (-item[0], item[2]))
    out = []
    i = 0
    while i < len(tokens):
        hit = None
        width = 0
        for length, words, app_id in aliases:
            if i + length > len(tokens):
                continue
            if tokens[i : i + length] == words:
                hit = app_id
                width = length
                break
        if hit:
            if hit not in out:
                out.append(hit)
            i += max(width, 1)
        else:
            i += 1
    return out


def newly_named_apps(text, catalog, already=None):
    """Ids newly named since *already* — for streaming partials."""
    seen = list(already or [])
    fresh = []
    for app_id in named_apps_in(text, catalog):
        if app_id not in seen:
            seen.append(app_id)
            fresh.append(app_id)
    return fresh


def split_requests(text):
    raw = (text or "").strip()
    if not raw:
        return []
    parts = [part.strip() for part in _SPLIT.split(raw) if part.strip()]
    if len(parts) <= 1:
        return [raw]
    prefix = ""
    match = _VERB_PREFIX.match(parts[0]) or _OPEN_PREFIX.match(parts[0])
    if match:
        prefix = match.group(0)
    out = []
    for index, part in enumerate(parts):
        if index == 0 or not prefix or _VERB_PREFIX.match(part) or _OPEN_PREFIX.match(part):
            out.append(part)
        else:
            out.append(prefix + part)
    return out


def lifecycle_verb(text):
    """Return close / quit / kill if the utterance is that kind of request."""
    lowered = (text or "").strip().lower()
    if not lowered:
        return None
    match = _VERB_PREFIX.match(lowered) or _BARE_VERB.match(lowered)
    if not match:
        return None
    key = re.sub(r"\s+", " ", match.group(1).lower())
    return _CLOSE_VERBS.get(key)


def _is_yes(text):
    lowered = (text or "").strip().lower()
    return lowered in _YES


def _is_no(text):
    lowered = (text or "").strip().lower()
    return lowered in _NO


def _resolve_app(text, catalog, laya, thresholds):
    decision = decide(text, alias=None, laya=laya, thresholds=thresholds, catalog=catalog)
    recovered = exact_installed_id(text, catalog) or resolve_alias(text, catalog)
    if recovered and decision.action not in ("refuse", "open"):
        return recovered, Decision("open", app=recovered, apps=[recovered], reason="laya")
    if decision.action == "open" and decision.app:
        return decision.app, decision
    return recovered, decision


def _lifecycle_decision(verb, app_ids, running):
    live = set(running or ())
    protected = [app_id for app_id in app_ids if app_id in _PROTECTED]
    targets = [app_id for app_id in app_ids if app_id not in _PROTECTED]
    if not targets:
        if protected or verb:
            return Decision("ask", reason="protected" if protected else "which-app")
        return Decision("ask", reason="which-app")
    acting = [app_id for app_id in targets if app_id in live]
    missing = [app_id for app_id in targets if app_id not in live]
    if acting and missing:
        return Decision(
            verb,
            app=acting[0],
            apps=acting,
            reason="laya",
            pending=missing,
        )
    if acting:
        return Decision(verb, app=acting[0], apps=acting, reason="laya")
    return Decision(
        "confirm",
        app=missing[0],
        apps=[],
        reason="not-running",
        pending=missing,
    )


def handle_utterance(
    text,
    catalog,
    defaults,
    predict_fn,
    thresholds=None,
    settings=None,
    running=None,
    pending=None,
):
    del defaults
    cfg = normalize_settings(settings)
    uttered = (text or "").strip()
    if cfg["wake_enabled"]:
        hit, rest = match_wake(uttered, cfg["wake_phrases"])
        if hit:
            uttered = rest
            if not uttered:
                return Decision("chat", reason="wake")
    waiting = [app_id for app_id in (pending or []) if app_id]
    if waiting:
        if _is_yes(uttered):
            return Decision(
                "open",
                app=waiting[0],
                apps=waiting,
                reason="confirm",
            )
        if _is_no(uttered):
            return Decision("refuse", reason="confirm")
    if is_stop(uttered):
        return Decision("stop", reason="stop")
    target = parse_open_target(uttered)
    if target and target.get("kind") == "clipboard" and not target.get("app_hint"):
        return Decision("open_url", url="clipboard", reason="clipboard")
    named = named_apps_in(uttered, catalog)
    parts = split_requests(uttered)
    if len(named) > 1:
        # Prefer host-named ids when Apple omitted commas
        # ("open calculator antigravity and notes").
        parts = ["open " + app_id for app_id in named]
    if len(parts) <= 1:
        verb = lifecycle_verb(uttered)
        if not verb and not target:
            sys_hit = parse_system(uttered)
            if sys_hit:
                return Decision("system", system=[sys_hit], reason="host")
        laya_input = laya_text(uttered, catalog) if target else uttered
        laya = predict_fn(laya_input, catalog)
        app_id, decision = _resolve_app(laya_input, catalog, laya, thresholds)
        if verb:
            if not app_id:
                return Decision("ask", reason="which-app")
            if app_id in _PROTECTED:
                return Decision("ask", reason="protected")
            return _lifecycle_decision(verb, [app_id], running)
        if target:
            return _url_decision(target, app_id, decision, catalog)
        if decision.action in ("ask", "chat"):
            sys_fb = system_from_laya(laya)
            if sys_fb:
                return Decision("system", system=[sys_fb], reason="laya")
        return decision
    verb = lifecycle_verb(uttered) or lifecycle_verb(parts[0])
    opened = []
    system_actions = []
    sys_reason = "host"
    last = None

    def collect_system(cmd, reason):
        if cmd and not any(c.get("verb") == cmd.get("verb") for c in system_actions):
            system_actions.append(cmd)
            return reason
        return None

    for part in parts:
        if not verb:
            sys_hit = parse_system(part)
            if sys_hit:
                collect_system(sys_hit, "host")
                continue
        laya = predict_fn(part, catalog)
        last = decide(part, alias=None, laya=laya, thresholds=thresholds, catalog=catalog)
        if last.action == "refuse":
            continue
        recovered = None
        if last.action == "open" and last.app:
            recovered = last.app
        else:
            recovered = exact_installed_id(part, catalog) or resolve_alias(part, catalog)
        if recovered and recovered not in opened:
            opened.append(recovered)
            continue
        if not verb and last.action in ("ask", "chat"):
            sys_fb = system_from_laya(laya)
            if collect_system(sys_fb, "laya"):
                sys_reason = "laya"
    if verb:
        if not opened:
            return last or Decision("ask", reason="which-app")
        return _lifecycle_decision(verb, opened, running)
    if target and opened:
        return _url_decision(target, opened[0], last, catalog)
    if opened:
        return Decision("open", app=opened[0], apps=opened, system=system_actions, reason="laya")
    if system_actions:
        return Decision("system", system=system_actions, reason=sys_reason)
    return last or Decision("ask", reason="unspecified")


def _names(decision, catalog):
    ids = decision.apps or ([decision.app] if decision.app else [])
    names = []
    for app_id in ids:
        spec = (catalog or {}).get(app_id) or {}
        names.append(spec.get("say") or app_id)
    return names


def _join_names(names, fallback="it"):
    if not names:
        names = [fallback]
    if len(names) == 1:
        return names[0]
    return "%s and %s" % (", ".join(names[:-1]), names[-1])


def _url_app(target, catalog, fallback=None):
    hint = (target or {}).get("app_hint")
    if hint and catalog:
        named = resolve_alias(hint, catalog) or exact_installed_id(hint, catalog)
        if named:
            return named
    return fallback


def _url_decision(target, app_id, decision, catalog=None):
    url = target.get("url")
    if not url:
        return decision or Decision("ask", reason="unspecified")
    chosen = _url_app(target, catalog, fallback=app_id)
    if url == "clipboard":
        return Decision(
            "open_url",
            app=chosen,
            apps=[chosen] if chosen else [],
            url="clipboard",
            reason="clipboard",
        )
    if not chosen:
        return Decision("ask", reason="unspecified")
    return Decision(
        "open_url",
        app=chosen,
        apps=[chosen],
        url=url,
        reason="laya",
    )


def _site_label(url):
    from opener.sites import label_for

    return label_for(url)


def _system_suffix(decision):
    return " ".join(
        line for line in (system_label(cmd) for cmd in (decision.system or [])) if line
    )


def spoken(decision, catalog):
    base = _spoken_base(decision, catalog)
    suffix = _system_suffix(decision)
    if suffix and decision.action in ("open", "open_url"):
        return (base + " " + suffix).strip()
    return base


def _spoken_base(decision, catalog):
    if decision.action == "system":
        return _system_suffix(decision)
    if decision.action == "open_url":
        if decision.url == "clipboard":
            if decision.app:
                return "Opening the clipboard in %s." % _join_names(_names(decision, catalog))
            return "Opening the clipboard."
        site = _site_label(decision.url)
        if decision.app:
            return "Opening %s in %s." % (site, _join_names(_names(decision, catalog)))
        return "Opening %s." % site
    if decision.action == "open":
        return "Opening %s." % _join_names(_names(decision, catalog))
    if decision.action in ("close", "quit", "kill"):
        verbs = {"close": "Closed", "quit": "Quit", "kill": "Force quit"}
        line = "%s %s." % (verbs[decision.action], _join_names(_names(decision, catalog)))
        if decision.pending:
            waiting = []
            for app_id in decision.pending:
                spec = (catalog or {}).get(app_id) or {}
                waiting.append(spec.get("say") or app_id)
            line += " %s isn't open. Open it?" % _join_names(waiting, fallback="that app")
        return line
    if decision.action == "confirm":
        names = _names(decision, catalog)
        if not names and decision.pending:
            names = []
            for app_id in decision.pending:
                spec = (catalog or {}).get(app_id) or {}
                names.append(spec.get("say") or app_id)
        label = _join_names(names, fallback="that app")
        return "%s isn't open. Open it?" % label
    if decision.action == "refuse":
        return "Okay, I won't."
    if decision.action == "ask":
        if decision.reason == "which-app":
            return "Which app should I close?"
        if decision.reason == "protected":
            return "I won't quit that."
        return "Which app should I open?"
    if decision.action == "stop":
        return "Goodbye."
    return "I open apps. Try saying open notes, or open the browser."
