"""Mac system controls: volume, brightness, appearance, lock, battery, panes.

Fully-parsed commands skip Laya (the `open clipboard` precedent): the host
extracts verb + amount exactly and the island executes. Paraphrases ("make it
louder") are gated by looks_systemish into Laya's `system` choice head; the
head picks the verb and the host fills default amounts.

Amounts: "increase brightness by 2" means two steps of 10% -> +20%. Numbers
above ten read as raw percents ("by 20" -> 20%). "percent" forces raw.
"""

import re

_VERBS = (
    "volume_up", "volume_down", "volume_set", "volume_mute", "volume_unmute",
    "brightness_up", "brightness_down", "brightness_set",
    "dark_mode", "light_mode", "night_shift_on", "night_shift_off",
    "lock_screen", "battery",
    "wifi_settings", "bluetooth_settings",
    "airdrop_off", "airdrop_on", "airdrop_contacts", "airdrop_everyone",
)

# Gate words for the Laya `system` head and the Swift partial-fire guard.
# Loose substring match is fine: the gate only adds a question, parse decides.
GATE_WORDS = (
    "volume", "sound", "speaker", "audio", "louder", "quieter", "softer",
    "mute", "brightness", "brighter", "brighten", "dimmer", "dim", "backlight",
    "dark mode", "light mode", "night mode", "night shift", "nightshift",
    "lock", "battery", "charging", "charge", "juice",
    "wifi", "wi-fi", "bluetooth", "airdrop", "air drop",
)

# Laya choice head for paraphrases. Host parse emits the same verb strings, so
# a confident Laya pick maps 1:1 onto a command with default amounts.
SYSTEM_CRITERIA = {
    "volume_up": "turn the volume up, make it louder, increase the sound",
    "volume_down": "turn the volume down, make it quieter, lower the sound, too loud",
    "volume_mute": "mute or silence the sound",
    "volume_unmute": "unmute the sound",
    "brightness_up": "make the screen brighter, increase brightness, too dim",
    "brightness_down": "dim the screen, decrease brightness, too bright",
    "dark_mode": "turn on dark mode, dark appearance",
    "light_mode": "turn on light mode, turn off dark mode, light appearance",
    "night_shift_on": "turn on night shift or night mode, warmer screen colors",
    "night_shift_off": "turn off night shift or night mode",
    "lock_screen": "lock the screen, lock the mac",
    "battery": "battery percentage, charge level, how much battery is left",
    "wifi_settings": "open wifi settings or wi-fi preferences",
    "bluetooth_settings": "open bluetooth settings or preferences",
    "airdrop_off": "turn off or disable airdrop",
    "airdrop_on": "turn on or enable airdrop",
    "unspecified": "no system control — an app request, a question, or chat",
}

LAYA_DEFAULTS = {
    "volume_up": {"verb": "volume_up", "value": 0.1},
    "volume_down": {"verb": "volume_down", "value": 0.1},
    "volume_mute": {"verb": "volume_mute"},
    "volume_unmute": {"verb": "volume_unmute"},
    "brightness_up": {"verb": "brightness_up", "value": 0.1},
    "brightness_down": {"verb": "brightness_down", "value": 0.1},
    "dark_mode": {"verb": "dark_mode"},
    "light_mode": {"verb": "light_mode"},
    "night_shift_on": {"verb": "night_shift_on"},
    "night_shift_off": {"verb": "night_shift_off"},
    "lock_screen": {"verb": "lock_screen"},
    "battery": {"verb": "battery"},
    "wifi_settings": {"verb": "wifi_settings"},
    "bluetooth_settings": {"verb": "bluetooth_settings"},
    "airdrop_off": {"verb": "airdrop_off"},
    "airdrop_on": {"verb": "airdrop_on"},
}

_NEGATION = re.compile(r"\b(don't|dont|do not|never)\b", re.I)

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}

# ASR homophones of small numbers — only trusted after "by", where a bare
# "to/too/for/ate" can only be a number ("increase volume by to" = by two).
_BY_HOMOPHONES = {
    "two": 2, "to": 2, "too": 2,
    "four": 4, "for": 4,
    "eight": 8, "ate": 8,
}


def looks_systemish(text):
    low = (text or "").lower()
    return any(word in low for word in GATE_WORDS)


def _fraction(num, explicit_percent):
    if num is None or num < 0:
        return None
    pct = num if explicit_percent or num > 10 else num * 10
    return max(0.01, min(1.0, pct / 100.0))


def _amount(text):
    match = re.search(r"(\d{1,3})\s*(%|percent|per cent)?", text)
    if match:
        return _fraction(int(match.group(1)), bool(match.group(2)))
    by = re.search(
        r"\bby\s+(two|to|too|four|for|eight|ate)\b\s*(%|percent|per cent)?", text
    )
    if by:
        return _fraction(_BY_HOMOPHONES[by.group(1)], bool(by.group(2)))
    for word in sorted(_NUMBER_WORDS, key=len, reverse=True):
        match = re.search(rf"\b{word}\b", text)
        if match:
            return _fraction(_NUMBER_WORDS[word], "percent" in text)
    return None


# A "to" that follows "by" is the number two, not a set-target
# ("increase volume by to" = up 20%, not set to 20%).
_SET_TARGET = re.compile(r"\b(?:set|change)\b|\bat\b|(?<!by )\bto\b")


def _parse_volume(text):
    if re.search(r"\bunmute\b", text):
        return {"verb": "volume_unmute"}
    if re.search(r"\b(mute|silence)\b", text):
        return {"verb": "volume_mute"}
    keyed = re.search(r"\b(volume|sounds?|speakers?|audio)\b", text)
    bare_dir = re.search(r"\b(louder|quieter|softer)\b", text)
    too = re.search(r"\btoo\s+(loud|noisy|quiet|low)\b", text)
    if not keyed and not bare_dir and not too:
        return None
    if re.search(r"\b(max|maximum|full)\b", text):
        return {"verb": "volume_set", "value": 1.0}
    if re.search(r"\b(min|minimum|zero)\b", text):
        return {"verb": "volume_set", "value": 0.0}
    if re.search(r"\bhalf\b", text):
        return {"verb": "volume_set", "value": 0.5}
    value = _amount(text)
    if too:
        verb = "volume_down" if too.group(1) in ("loud", "noisy") else "volume_up"
        return {"verb": verb, "value": value if value is not None else 0.1}
    if re.search(r"\b(set|change)\b", text) or (value is not None and _SET_TARGET.search(text)):
        if value is None:
            return None
        return {"verb": "volume_set", "value": value}
    if re.search(r"\b(increase|raise|higher|boost|up|louder)\b", text) or re.search(r"\bturn(ed)?\s+up\b", text):
        return {"verb": "volume_up", "value": value if value is not None else 0.1}
    if re.search(r"\b(decrease|reduce|lower|down|quieter|softer)\b", text) or re.search(r"\bturn(ed)?\s+down\b", text):
        return {"verb": "volume_down", "value": value if value is not None else 0.1}
    if value is not None and keyed:
        return {"verb": "volume_set", "value": value}
    return None


def _parse_brightness(text):
    keyed = re.search(r"\b(brightness|backlight)\b", text)
    screen_dir = re.search(r"\b(screen|display|monitor)\b", text) and re.search(
        r"\b(brighter|brighten|dim|dimmer)\b", text
    )
    bare = re.search(r"\b(brighter|dimmer|brighten)\b", text)
    too = re.search(r"\btoo\s+(bright|dim)\b", text)
    if not (keyed or screen_dir or bare or too):
        return None
    if re.search(r"\b(max|maximum|full)\b", text):
        return {"verb": "brightness_set", "value": 1.0}
    if re.search(r"\b(min|minimum|lowest)\b", text):
        return {"verb": "brightness_set", "value": 0.05}
    if re.search(r"\bhalf\b", text):
        return {"verb": "brightness_set", "value": 0.5}
    value = _amount(text)
    if too:
        verb = "brightness_down" if too.group(1) == "bright" else "brightness_up"
        return {"verb": verb, "value": value if value is not None else 0.1}
    if re.search(r"\b(set|change)\b", text) or (value is not None and _SET_TARGET.search(text)):
        if value is None:
            return None
        return {"verb": "brightness_set", "value": value}
    if re.search(r"\b(increase|raise|higher|up|brighter|brighten)\b", text) or re.search(r"\bturn(ed)?\s+up\b", text):
        return {"verb": "brightness_up", "value": value if value is not None else 0.1}
    if re.search(r"\b(decrease|reduce|lower|down|dim|dimmer)\b", text) or re.search(r"\bturn(ed)?\s+down\b", text):
        return {"verb": "brightness_down", "value": value if value is not None else 0.1}
    if value is not None and keyed:
        return {"verb": "brightness_set", "value": value}
    return None


def _parse_appearance(text):
    if re.search(r"\bnight[\s-]?shift\b|\bnight mode\b", text):
        off = re.search(r"\b(off|disable|stop)\b", text)
        return {"verb": "night_shift_off" if off else "night_shift_on"}
    if re.search(r"\bdark (mode|theme|appearance)\b", text):
        off = re.search(r"\b(off|disable)\b", text)
        return {"verb": "light_mode" if off else "dark_mode"}
    if re.search(r"\blight (mode|theme|appearance)\b", text):
        off = re.search(r"\b(off|disable)\b", text)
        return {"verb": "dark_mode" if off else "light_mode"}
    return None


def _parse_lock(text):
    if re.search(r"\bunlock\b", text):
        return None
    if re.search(r"\block\b", text) and re.search(r"\b(screen|mac|computer|laptop|display|it)\b", text):
        return {"verb": "lock_screen"}
    return None


def _parse_battery(text):
    if re.search(r"\bbattery\b", text):
        return {"verb": "battery"}
    if re.search(r"\bhow much (charge|juice|power)\b", text):
        return {"verb": "battery"}
    if re.search(r"\bcharge (level|percentage|status|left)\b", text):
        return {"verb": "battery"}
    if re.search(r"\b(is it|is my (mac|laptop|computer)) (still )?charging\b", text):
        return {"verb": "battery"}
    return None


def _parse_pane(text):
    pane = re.search(r"\b(settings?|preferences?|prefs?|pane)\b", text)
    if not pane:
        return None
    if re.search(r"\bwi[- ]?fi\b|\bwifi\b", text):
        return {"verb": "wifi_settings"}
    if re.search(r"\bbluetooth\b", text):
        return {"verb": "bluetooth_settings"}
    return None


def _parse_airdrop(text):
    if not re.search(r"\bair\s?drop\b", text):
        return None
    if re.search(r"\beveryone\b", text):
        return {"verb": "airdrop_everyone"}
    if re.search(r"\bcontacts?\b", text):
        return {"verb": "airdrop_contacts"}
    if re.search(r"\bturn(ed)?\s+off\b", text) or re.search(r"\b(off|disable|stop)\b", text):
        return {"verb": "airdrop_off"}
    if re.search(r"\bturn(ed)?\s+on\b", text) or re.search(r"\b(on|enable|start)\b", text):
        return {"verb": "airdrop_on"}
    return None


_PARSERS = (
    _parse_airdrop,
    _parse_pane,
    _parse_lock,
    _parse_battery,
    _parse_appearance,
    _parse_volume,
    _parse_brightness,
)


def parse(text):
    """Utterance -> one system command, or None. Runs before the Laya call."""
    low = " ".join((text or "").lower().split())
    if not low or _NEGATION.search(low):
        return None
    for parser in _PARSERS:
        hit = parser(low)
        if hit:
            return hit
    return None


def from_laya(laya, threshold=0.55):
    """System command from Laya's `system` head, or None. Default amounts."""
    head = (laya or {}).get("system") or {}
    choice = head.get("choice")
    if not choice or choice == "unspecified" or choice not in LAYA_DEFAULTS:
        return None
    try:
        conf = float(head.get("answer_confidence", head.get("confidence")) or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    probs = head.get("probabilities") or {}
    if probs:
        try:
            best = max(probs.items(), key=lambda item: float(item[1]))[0]
        except (TypeError, ValueError):
            best = None
        if best and best != choice:
            return None
    if conf < threshold:
        return None
    return dict(LAYA_DEFAULTS[choice])


def label(cmd):
    """Caption line for a command. Lockstep with Engine.systemLabel in Swift."""
    verb = (cmd or {}).get("verb") or ""
    value = (cmd or {}).get("value")
    pct = ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        pct = " %d%%" % round(value * 100)
    labels = {
        "volume_up": "Volume up" + pct + ".",
        "volume_down": "Volume down" + pct + ".",
        "volume_set": "Volume set to" + pct + ".",
        "volume_mute": "Muted.",
        "volume_unmute": "Unmuted.",
        "brightness_up": "Brightness up" + pct + ".",
        "brightness_down": "Brightness down" + pct + ".",
        "brightness_set": "Brightness set to" + pct + ".",
        "dark_mode": "Dark mode on.",
        "light_mode": "Light mode on.",
        "night_shift_on": "Night Shift on.",
        "night_shift_off": "Night Shift off.",
        "lock_screen": "Locking the screen.",
        "battery": "Checking the battery.",
        "wifi_settings": "Opening Wi-Fi settings.",
        "bluetooth_settings": "Opening Bluetooth settings.",
        "airdrop_off": "AirDrop off.",
        "airdrop_on": "AirDrop on, contacts only.",
        "airdrop_contacts": "AirDrop on, contacts only.",
        "airdrop_everyone": "AirDrop on for everyone.",
    }
    return labels.get(verb, "")
