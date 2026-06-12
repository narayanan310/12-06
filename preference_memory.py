"""
preference_memory.py
Driver preference storage and recall — fully offline, JSON file backed.

Supports
────────
• "Remember this."         — saves current vehicle state as named profile
• "Use my usual settings." — applies saved preferences
• "What are my preferences?" — lists saved preferences
• Per-key preference ("remember this temperature")

Preferences are stored in ~/.cockpit_prefs.json so they survive restarts.
"""

import json
import os
import time


_PREFS_FILE = os.path.expanduser("~/.cockpit_prefs.json")

# Keys we consider "personalisation-worthy"
_PREF_KEYS = {
    "ac_temperature": "temperature",
    "fan_speed":      "fan speed",
    "brightness":     "brightness",
}

# Trigger phrases that mean "save current state"
_SAVE_TRIGGERS = [
    "remember this",
    "save this",
    "save my settings",
    "store this",
    "keep this",
    "this is perfect",
    "that's perfect",
    "thats perfect",
    "remember my preference",
    "save my preference",
]

# Trigger phrases that mean "load preferences"
_LOAD_TRIGGERS = [
    "use my usual",
    "my usual settings",
    "my preferences",
    "restore my settings",
    "load my settings",
    "apply my settings",
    "preferred settings",
    "use my saved",
]

# Query phrases
_QUERY_TRIGGERS = [
    "what are my preferences",
    "show my preferences",
    "what did i save",
    "my saved settings",
]

# Per-key save triggers — map a substring to a state key
_KEY_SAVE_TRIGGERS = {
    "this temperature": "ac_temperature",
    "this temp":        "ac_temperature",
    "this brightness":  "brightness",
    "this fan":         "fan_speed",
    "this fan speed":   "fan_speed",
}


class PreferenceMemory:
    def __init__(self) -> None:
        self._prefs: dict = self._load()

    # ── Persistence ───────────────────────────────────────────────────────

    def _load(self) -> dict:
        try:
            with open(_PREFS_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        with open(_PREFS_FILE, "w") as f:
            json.dump(self._prefs, f, indent=2)

    # ── Public API ────────────────────────────────────────────────────────

    def detect(self, text: str) -> str | None:
        """
        Returns one of: 'save', 'save_key:<key>', 'load', 'query', or None.
        Caller uses this to decide what action to take.
        """
        t = text.lower().strip()

        # Query first (subset of save triggers sometimes)
        if any(kw in t for kw in _QUERY_TRIGGERS):
            return "query"

        # Per-key save
        for phrase, key in _KEY_SAVE_TRIGGERS.items():
            if phrase in t:
                return f"save_key:{key}"

        # Full-state save
        if any(kw in t for kw in _SAVE_TRIGGERS):
            return "save"

        # Load
        if any(kw in t for kw in _LOAD_TRIGGERS):
            return "load"

        return None

    def save_all(self, state: dict) -> str:
        """Save all personalisation-worthy keys from current state."""
        for state_key in _PREF_KEYS:
            if state_key in state:
                self._prefs[state_key] = {
                    "value": state[state_key],
                    "saved_at": time.strftime("%Y-%m-%d %H:%M"),
                }
        self._save()
        lines = [
            f"{_PREF_KEYS[k]}: {self._prefs[k]['value']}"
            for k in _PREF_KEYS if k in self._prefs
        ]
        return "Saved: " + ", ".join(lines) + "."

    def save_key(self, key: str, state: dict) -> str:
        """Save a single preference key."""
        if key not in state:
            return f"Could not save {key} — not found in current state."
        self._prefs[key] = {
            "value": state[key],
            "saved_at": time.strftime("%Y-%m-%d %H:%M"),
        }
        self._save()
        label = _PREF_KEYS.get(key, key)
        return f"Saved {label}: {state[key]}."

    def load_all(self) -> list[dict] | None:
        """
        Return a list of CAN actions to restore saved preferences,
        or None if no preferences are saved.
        """
        if not self._prefs:
            return None

        _KEY_TO_CAN = {
            "ac_temperature": ("0x101", "SET_TEMPERATURE"),
            "fan_speed":       ("0x101", "SET_FAN_SPEED"),
            "brightness":      ("0x103", "SET_BRIGHTNESS"),
        }

        actions = []
        for state_key, (can_id, cmd) in _KEY_TO_CAN.items():
            if state_key in self._prefs:
                actions.append({
                    "can_id":  can_id,
                    "command": cmd,
                    "value":   self._prefs[state_key]["value"],
                })
        return actions if actions else None

    def describe(self) -> str:
        """Human-readable description of stored preferences."""
        if not self._prefs:
            return "No preferences saved yet. Say 'remember this' to save current settings."
        lines = []
        for key, label in _PREF_KEYS.items():
            if key in self._prefs:
                entry = self._prefs[key]
                lines.append(f"  {label}: {entry['value']} (saved {entry['saved_at']})")
        return "Your saved preferences:\n" + "\n".join(lines)
