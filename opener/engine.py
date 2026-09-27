"""Decision-engine adapters. Laya and Jev are System One models; decide stays here."""

from opener.client import DEFAULT_URL, predict as client_predict


ENGINE_HOST = "host"
ENGINE_LAYA = "laya"
ENGINE_JEV = "jev"

JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
LAYA_MODEL = "english"

KNOWN = (ENGINE_HOST, ENGINE_LAYA, ENGINE_JEV)


def engine_spec(name, token=None, laya_url=None):
    engine = str(name or ENGINE_HOST).strip().lower() or ENGINE_HOST
    if engine not in KNOWN:
        return {
            "engine": engine,
            "available": False,
            "reason": "unknown-engine",
            "url": None,
            "model": None,
            "token": None,
            "needs_docker": False,
        }
    if engine == ENGINE_HOST:
        return {
            "engine": ENGINE_HOST,
            "available": True,
            "reason": None,
            "url": None,
            "model": None,
            "token": None,
            "needs_docker": False,
        }
    if engine == ENGINE_JEV:
        key = (token or "").strip() or None
        return {
            "engine": ENGINE_JEV,
            "available": bool(key),
            "reason": None if key else "missing-key",
            "url": JEV_URL,
            "model": JEV_MODEL,
            "token": key,
            "needs_docker": False,
        }
    return {
        "engine": ENGINE_LAYA,
        "available": True,
        "reason": None,
        "url": laya_url or DEFAULT_URL,
        "model": LAYA_MODEL,
        "token": None,
        "needs_docker": True,
    }


def predict_for(name, token=None, laya_url=None, predict_fn=None):
    spec = engine_spec(name, token=token, laya_url=laya_url)
    pred = predict_fn or client_predict

    def _predict(text, catalog):
        if spec["engine"] == ENGINE_HOST or not spec["url"]:
            return {
                "intent": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
                "app": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
                "system": {"choice": None, "answer_confidence": 0.0, "probabilities": {}},
            }
        return pred(
            text,
            catalog,
            url=spec["url"],
            model=spec["model"],
            token=spec["token"],
        )

    return _predict


def unavailable_payload(spec):
    engine = spec.get("engine") or "that engine"
    label = engine[:1].upper() + engine[1:]
    if spec.get("reason") == "missing-key":
        spoken = "Add a %s API key in Settings." % label
    elif spec.get("reason") == "unknown-engine":
        spoken = "%s is not a known engine." % label
    else:
        spoken = "%s is not available." % label
    return {
        "action": "ask",
        "app": None,
        "apps": [],
        "system": [],
        "reason": "backend-unavailable",
        "spoken": spoken,
    }
