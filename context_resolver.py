"""
context_resolver.py
Deterministic semantic resolver for natural-language comfort, safety,
wellness, and domain-re-routing expressions.

Priority order: safety → comfort → ambiance → wellness
"""

import time


_RULES: list[dict] = [

    # ══ SAFETY ════════════════════════════════════════════════════════════
    {   "priority": "safety",
        "keywords": [
            "can't see", "cannot see", "cant see",
            "can't see the road", "cant see the road",
            "blind", "dark road", "dark outside",
            "foggy", "fog", "misty", "mist",
            "visibility", "hard to see", "too dark to drive",
            "nothing ahead", "pitch black", "pitch-black",
            "everything is black", "all black",
        ],
        "can_id":  "0x103", "command": "SET_HEADLIGHTS", "value": 1,
        "confidence": 0.95,
        "reason":  "Visibility hazard — headlights on.",
    },

    {   "priority": "safety",
        "keywords": [
            "brake problem", "brakes feel", "steering problem",
            "vibration", "shaking badly", "tire noise",
            "smoke coming", "engine noise", "weird noise",
            "something's wrong", "somethings wrong",
        ],
        "can_id":  None, "command": "SAFETY_ALERT", "value": 0,
        "confidence": 0.90,
        "reason":  "Mechanical safety concern flagged.",
    },

    {   "priority": "safety",
        "keywords": [
            "falling asleep", "can't stay awake", "cant stay awake",
            "drowsy", "dozing", "about to sleep",
            "eyes closing", "need to stay awake",
        ],
        "can_id":  "0x101", "command": "SET_TEMPERATURE", "value": 18,
        "confidence": 0.80,
        "reason":  "Driver drowsiness — cooling cabin to aid alertness.",
        "_extra_warning": "⚠ Drowsiness detected. Please pull over safely if needed.",
    },

    # ══ COMFORT — HEAT / COOLING ══════════════════════════════════════════
    {   "priority": "comfort",
        "keywords": [
            "sweating", "sweaty", "sweat",
            "boiling", "burning up", "roasting",
            "it's hot", "its hot", "too hot", "very hot",
            "suffocating", "suffocate",
            "can't breathe", "cant breathe",
            "no air", "humid", "stifling",
            "sticky", "muggy",
            "i'm warm", "im warm", "feeling warm", "getting warm",
            "i'm hot", "im hot",
        ],
        "can_id":  "0x101", "command": "SET_TEMPERATURE", "value": 18,
        "confidence": 0.88,
        "reason":  "Heat complaint — lowering temperature.",
    },

    {   "priority": "comfort",
        "keywords": [
            "freezing", "frozen", "shivering",
            "it's cold", "its cold", "too cold", "very cold",
            "chilly", "ice cold", "brrr",
            "i'm cold", "im cold", "feeling cold", "getting cold",
            "i'm freezing", "im freezing",
            "cold in here", "bit cold",
        ],
        "can_id":  "0x101", "command": "SET_TEMPERATURE", "value": 26,
        "confidence": 0.88,
        "reason":  "Cold complaint — raising temperature.",
    },

    # NEW: Vague improvement requests (this fixes "make it better")
    {   "priority": "comfort",
        "keywords": [
            "make it better", "make better", "a bit better",
            "more comfortable", "feels better", "improve",
            "make it nicer", "better temperature", "better air",
        ],
        "can_id":  "0x101", "command": "SET_TEMPERATURE", "value": 21,
        "confidence": 0.78,
        "reason":  "Vague comfort request — setting neutral temperature.",
    },

    # ══ COMFORT — SUNROOF / VENTILATION ══════════════════════════════════
    {   "priority": "comfort",
        "keywords": [
            "fresh air", "need fresh air", "need some air",
            "open up", "let air in", "let some air in",
            "crack it open", "bit of breeze", "breeze please",
            "air it out", "ventilation",
        ],
        "can_id":  "0x102", "command": "SET_POSITION", "value": 50,
        "confidence": 0.83,
        "reason":  "Fresh air request — partial sunroof open.",
    },

    {   "priority": "comfort",
        "keywords": [
            "stuffy", "stale air", "stale",
            "hot and stuffy", "needs ventilation",
            "uncomfortable", "i'm uncomfortable", "im uncomfortable",
        ],
        "can_id":  "0x101", "command": "SET_FAN_SPEED", "value": 4,
        "confidence": 0.82,
        "reason":  "Stuffiness / discomfort — increasing fan speed.",
    },
        {   "priority": "comfort",
        "keywords": [
            "fan more", "fan higher", "increase fan", "more fan",
            "fan less", "fan lower", "reduce fan", "lower fan",
        ],
        "can_id":  "0x101", "command": "SET_FAN_SPEED", "value": 5,
        "confidence": 0.85,
        "reason":  "Fan speed adjustment requested.",
    },

    # ══ AMBIANCE — LIGHTING ═══════════════════════════════════════════════
    {   "priority": "ambiance",
        "keywords": [
            "gloomy", "dim inside", "dark inside",
            "can't see dashboard", "cant see dashboard",
            "too dark in here", "it's dark in here", "its dark in here",
            "hard to read", "screen too dim",
        ],
        "can_id":  "0x103", "command": "SET_BRIGHTNESS", "value": 85,
        "confidence": 0.80,
        "reason":  "Dark interior — raising dashboard brightness.",
    },

    {   "priority": "ambiance",
        "keywords": [
            "too bright", "blinding dashboard", "glaring screen",
            "eyes hurt", "hurts my eyes",
            "screen too bright", "too much light inside",
            "dial it down", "turn down the screen",
        ],
        "can_id":  "0x103", "command": "SET_BRIGHTNESS", "value": 20,
        "confidence": 0.80,
        "reason":  "Bright interior — lowering brightness.",
    },

    # ══ WELLNESS ══════════════════════════════════════════════════════════
    {   "priority": "wellness",
        "keywords": [
            "i'm tired", "im tired", "i am tired",
            "feeling tired", "bit tired",
            "exhausted", "worn out",
        ],
        "can_id":  "0x101", "command": "SET_TEMPERATURE", "value": 18,
        "confidence": 0.72,
        "reason":  "Fatigue — cooling cabin to aid alertness.",
        "_wellness_msg": (
            "Cooling the cabin to help you stay alert. "
            "If you're very tired, please find a safe place to rest."
        ),
    },

    {   "priority": "wellness",
        "keywords": [
            "i'm stressed", "im stressed", "feeling stressed",
            "anxious", "i have a headache", "headache",
            "head hurts", "migraine",
        ],
        "can_id":  "0x101", "command": "SET_TEMPERATURE", "value": 20,
        "confidence": 0.68,
        "reason":  "Stress / headache — setting comfortable temperature.",
        "_wellness_msg": (
            "Setting a calm cabin temperature. "
            "Consider taking a short break when it's safe to do so."
        ),
    },

    {   "priority": "wellness",
        "keywords": [
            "cozy", "cosy", "snug", "comfortable",
            "just right", "pleasant",
        ],
        "can_id":  "0x101", "command": "SET_TEMPERATURE", "value": 22,
        "confidence": 0.65,
        "reason":  "Comfort preference — setting neutral temperature.",
    },
]

_PRIORITY_ORDER = {"safety": 0, "comfort": 1, "ambiance": 2, "wellness": 3}
_SORTED_RULES   = sorted(_RULES, key=lambda r: _PRIORITY_ORDER.get(r["priority"], 9))


class ContextResolver:
    def resolve(self, text: str) -> dict | None:
        t     = text.lower().strip()
        start = time.monotonic()

        for rule in _SORTED_RULES:
            if any(kw in t for kw in rule["keywords"]):
                latency_ms = (time.monotonic() - start) * 1000

                intent: dict = {
                    "can_id":     rule["can_id"],
                    "command":    rule["command"],
                    "value":      rule["value"],
                    "reason":     rule["reason"],
                    "confidence": rule["confidence"],
                    "priority":   rule["priority"],
                    "handled_by": "ContextResolver",
                    "latency":    f"{latency_ms:.2f}ms",
                }

                if "_extra_warning" in rule:
                    intent["_warning"] = rule["_extra_warning"]
                if "_wellness_msg" in rule:
                    intent["_wellness_msg"] = rule["_wellness_msg"]

                return intent

        return None