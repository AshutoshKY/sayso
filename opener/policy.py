from opener.alias import resolve_alias

DEFAULT_THRESHOLDS = {
    "intent": 0.72,
    "app": 0.70,
    "named": 0.20,
    "margin": 0.15,
}


class Decision:
    def __init__(self, action, app=None, reason="", apps=None, pending=None, url=None, system=None):
        self.action = action
        self.app = app
        self.reason = reason
        if apps is not None:
            self.apps = list(apps)
        elif app:
            self.apps = [app]
        else:
            self.apps = []
        self.pending = list(pending) if pending else []
        self.url = url
        self.system = [dict(cmd) for cmd in (system or [])]


def _choice(block, key="choice"):
    if not block:
        return None
    return block.get(key)


def _conf(block):
    if not block:
        return 0.0
    value = block.get("answer_confidence")
    if value is None:
        value = block.get("confidence")
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _margin(block, chosen):
    probs = (block or {}).get("probabilities") or {}
    if not probs:
        return _conf(block)
    try:
        chosen_p = float(probs.get(chosen) or 0) if chosen else 0.0
    except (TypeError, ValueError):
        chosen_p = 0.0
    rest = [
        float(score)
        for name, score in probs.items()
        if name != chosen
    ]
    if not rest:
        return chosen_p or _conf(block)
    return chosen_p - max(rest)


def _best_app(block, catalog):
    """Highest Laya probability among installed apps. Unspecified never wins."""
    probs = (block or {}).get("probabilities") or {}
    ranked = []
    for name, score in probs.items():
        if not name or name == "unspecified":
            continue
        if catalog is not None and name not in catalog:
            continue
        try:
            ranked.append((float(score), name))
        except (TypeError, ValueError):
            continue
    if ranked:
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked[0][1], ranked[0][0]
    choice = _choice(block)
    return choice, _conf(block)


def decide(text, alias=None, laya=None, thresholds=None, catalog=None):
    """Use Laya's highest-scoring installed app. Host aliases are ignored."""
    del alias
    gates = dict(DEFAULT_THRESHOLDS)
    if thresholds:
        gates.update(thresholds)
    laya = laya or {}
    intent = _choice(laya.get("intent"))
    intent_p = _conf(laya.get("intent"))
    app_block = laya.get("app") or {}
    app, app_p = _best_app(app_block, catalog)

    if intent == "refuse":
        return Decision("refuse", reason="laya")

    known = app and app != "unspecified"
    in_catalog = catalog is None or app in catalog
    named = bool(catalog) and resolve_alias(text, catalog) == app
    gate = gates["named"] if named else gates["app"]
    confident = app_p >= gate
    clear = _margin(app_block, app) >= gates["margin"]
    if known and in_catalog and confident and clear:
        return Decision("open", app=app, reason="laya")

    if intent and (intent != "launch" or intent_p < gates["intent"]):
        if not known:
            return Decision("chat", reason="not-launch")
        return Decision("ask", reason="unspecified")

    return Decision("ask", reason="unspecified")
