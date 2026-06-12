"""
metaphor_resolver.py
Handles common automotive metaphors and idiomatic expressions.
Placed after ContextResolver for high-determinism coverage.
"""

import time


_METAPHORS = [

    # ============================================================
    # HOT / COOLING
    # ============================================================

    {
        "keywords": [
            "greenhouse", "sauna", "oven", "boiling", "roasting",
            "melting", "sweltering", "like an oven", "furnace",
            "desert", "sahara", "heatwave", "scorching",
            "burning up", "cooking in here", "hotbox",
            "toasty", "broiling", "blazing", "feels tropical"
        ],
        "can_id": "0x101",
        "command": "SET_TEMPERATURE",
        "value": 18,
        "reason": "Heat metaphor — cooling cabin.",
        "confidence": 0.90
    },

    # ============================================================
    # COLD / WARMING
    # ============================================================

    {
        "keywords": [
            "icebox", "arctic", "antarctica", "freezer",
            "igloo", "like a freezer", "polar vortex",
            "north pole", "winter wonderland",
            "cryogenic chamber", "cold as ice",
            "shivering", "frostbite", "freezing my",
            "teeth chattering", "icicle", "snowstorm",
            "tundra", "glacial"
        ],
        "can_id": "0x101",
        "command": "SET_TEMPERATURE",
        "value": 26,
        "reason": "Cold metaphor — warming cabin.",
        "confidence": 0.88
    },

    # ============================================================
    # FRESH AIR / SUNROOF OPEN
    # ============================================================

    {
        "keywords": [
            "stuffy", "claustrophobic", "airless",
            "needs air", "breeze", "fresh air",
            "stale air", "suffocating", "can't breathe",
            "cramped", "boxed in", "trapped",
            "let me breathe", "need ventilation",
            "open things up", "need oxygen",
            "some airflow", "too enclosed",
            "feels sealed", "cabin fever"
        ],
        "can_id": "0x102",
        "command": "SET_POSITION",
        "value": 30,
        "reason": "Ventilation metaphor — partial sunroof open.",
        "confidence": 0.86
    },

    # ============================================================
    # CLOSE SUNROOF
    # ============================================================

    {
        "keywords": [
            "too windy", "hair is everywhere",
            "too much air", "close it up",
            "button things up", "seal it",
            "drafty", "wind tunnel",
            "my papers are flying",
            "too breezy", "shut the roof",
            "close the opening"
        ],
        "can_id": "0x102",
        "command": "SET_POSITION",
        "value": 0,
        "reason": "Excessive airflow metaphor — closing sunroof.",
        "confidence": 0.84
    },

    # ============================================================
    # HEADLIGHTS ON
    # ============================================================

    {
        "keywords": [
            "pitch black", "pitch-black",
            "can't see anything", "total darkness",
            "black outside", "getting dark",
            "hard to see", "visibility is poor",
            "can't make out the road",
            "need more light", "too dim",
            "it's gloomy", "driving blind",
            "dark as night", "murky",
            "can't see the road"
        ],
        "can_id": "0x103",
        "command": "SET_HEADLIGHTS",
        "value": 1,
        "reason": "Visibility metaphor — headlights on.",
        "confidence": 0.92
    },

    # ============================================================
    # HEADLIGHTS OFF
    # ============================================================

    {
        "keywords": [
            "too bright", "blinding me",
            "kill the lights", "lights are too much",
            "turn down the glare",
            "don't need the lights",
            "shut the lights off",
            "it's bright enough",
            "not that dark anymore"
        ],
        "can_id": "0x103",
        "command": "SET_HEADLIGHTS",
        "value": 0,
        "reason": "Lighting metaphor — headlights off.",
        "confidence": 0.87
    },

    # ============================================================
    # FAN INCREASE
    # ============================================================

    {
        "keywords": [
            "need a breeze", "fan it up",
            "move some air", "more airflow",
            "still air", "fan harder",
            "air isn't moving",
            "circulate the air",
            "kick up the fan"
        ],
        "can_id": "0x101",
        "command": "SET_FAN_SPEED",
        "value": 4,
        "reason": "Airflow metaphor — increasing fan speed.",
        "confidence": 0.84
    },

    # ============================================================
    # FAN DECREASE
    # ============================================================

    {
        "keywords": [
            "too noisy", "wind is loud",
            "fan is screaming",
            "dial the fan back",
            "calm the airflow",
            "that's too much air",
            "fan is overdoing it",
            "quiet things down"
        ],
        "can_id": "0x101",
        "command": "SET_FAN_SPEED",
        "value": 1,
        "reason": "Excessive airflow metaphor — reducing fan speed.",
        "confidence": 0.83
    },

    # ============================================================
    # DASHBOARD BRIGHTNESS UP
    # ============================================================

    {
        "keywords": [
            "can't read the dashboard",
            "too dim inside",
            "dashboard is dark",
            "need more brightness",
            "brighten things up",
            "make the display clearer"
        ],
        "can_id": "0x103",
        "command": "SET_BRIGHTNESS",
        "value": 85,
        "reason": "Display visibility metaphor — increasing brightness.",
        "confidence": 0.88
    },

    # ============================================================
    # DASHBOARD BRIGHTNESS DOWN
    # ============================================================

    {
        "keywords": [
            "dashboard is blinding",
            "too bright inside",
            "dim things down",
            "lower the brightness",
            "that's hurting my eyes",
            "reduce the glare"
        ],
        "can_id": "0x103",
        "command": "SET_BRIGHTNESS",
        "value": 20,
        "reason": "Display comfort metaphor — reducing brightness.",
        "confidence": 0.88
    },

]

class MetaphorResolver:

    def resolve(self, text: str) -> dict | None:

        t = text.lower().strip()
        start = time.monotonic()

        best_match = None

        for m in _METAPHORS:

            hits = sum(
                kw in t
                for kw in m["keywords"]
            )

            if hits:

                score = m["confidence"] + hits * 0.02

                if best_match is None or score > best_match["score"]:

                    best_match = {
                        **m,
                        "score": score
                    }

        if best_match:

            latency = (time.monotonic() - start) * 1000

            return {
                "can_id": best_match["can_id"],
                "command": best_match["command"],
                "value": best_match["value"],
                "reason": best_match["reason"],
                "confidence": min(best_match["score"], 0.99),
                "handled_by": "MetaphorResolver",
                "latency": f"{latency:.2f}ms",
            }

        return None