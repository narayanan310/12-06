"""
macro_engine.py
Hardcoded multi-action sequences — highest-priority resolver.

Macros bypass the entire intent pipeline. They fire atomically
with a small inter-frame gap so ECU logs remain readable.

Macros defined
──────────────
dog mode      — cracked window, 22°C, AC on, fan 2
bye           — headlights off, AC off, fan 1, sunroof closed, brightness 10
good night    — brightness 5, sunroof closed, headlights off
focus mode    — 20°C, fan 1, brightness 30 (minimal distraction)
reset         — all systems to factory defaults
"""

import asyncio


_MACROS: dict[str, dict] = {

    "dog mode": {
        "display": "Dog Mode",
        "speech": (
            "Dog mode activated. "
            "Cracking the window to 10%, "
            "climate set to 22 degrees, AC and fan on."
        ),
        "actions": [
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 10},
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 22},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 1},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 2},
        ],
    },

    "bye": {
        "display": "Shutdown Sequence",
        "speech": (
            "Goodbye. Shutting everything down — "
            "headlights off, AC off, sunroof closed, dashboard dimmed."
        ),
        "actions": [
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 0},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 0},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 1},
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 0},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 10},
        ],
    },

    "good night": {
        "display": "Good Night Sequence",
        "speech": (
            "Good night. "
            "Dimming the dashboard, closing the sunroof, lights off."
        ),
        "actions": [
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 5},
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 0},
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 0},
        ],
    },

    "focus mode": {
        "display": "Focus Mode",
        "speech": (
            "Focus mode on. "
            "Optimal temperature, low fan, dimmed dashboard — "
            "reducing distractions."
        ),
        "actions": [
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 20},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 1},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 30},
        ],
    },

    "reset": {
        "display": "Reset to Defaults",
        "speech": (
            "Resetting all systems to defaults: "
            "22 degrees, fan 2, AC on, sunroof closed, "
            "lights off, brightness 50%."
        ),
        "actions": [
            {"can_id": "0x101", "command": "SET_TEMPERATURE", "value": 22},
            {"can_id": "0x101", "command": "SET_FAN_SPEED",   "value": 2},
            {"can_id": "0x101", "command": "TOGGLE_AC",       "value": 1},
            {"can_id": "0x102", "command": "SET_POSITION",    "value": 0},
            {"can_id": "0x103", "command": "SET_HEADLIGHTS",  "value": 0},
            {"can_id": "0x103", "command": "SET_BRIGHTNESS",  "value": 50},
        ],
    },
}


class MacroEngine:
    def match(self, text: str) -> dict | None:
        t = text.lower().strip()
        for trigger, macro in _MACROS.items():
            if trigger in t:
                return macro
        return None

    async def execute(self, bus, macro: dict) -> None:
        for action in macro["actions"]:
            await bus.publish(action["can_id"], action["command"], action["value"])
            await asyncio.sleep(0.12)
