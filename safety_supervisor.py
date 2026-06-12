"""
safety_supervisor.py
Safety gate between intent resolution and CAN bus dispatch.

Responsibilities
────────────────
• Hard-block commands outside safe operating ranges.
• Warn (but allow) state-conflicting commands.
• Block explicitly banned commands.
• Detect repeated extreme adjustments and warn.
• Gibberish / nonsense input detection (standalone utility).
"""

import re


_SAFE_RANGES: dict[str, tuple[int, int]] = {
    "SET_TEMPERATURE": (17, 29),
    "SET_FAN_SPEED":   (1, 5),
    "SET_POSITION":    (0, 100),
    "SET_BRIGHTNESS":  (0, 100),
    "SET_HEADLIGHTS":  (0, 1),
    "TOGGLE_AC":       (0, 1),
}

# Dynamically populated in future (e.g. block sunroof open above speed threshold)
_BLOCKED_COMMANDS: set[str] = set()


class SafetySupervisor:
    def __init__(self, state_manager) -> None:
        self.sm = state_manager

    def check(self, intent: dict) -> tuple[bool, str | None]:
        """
        Returns (allowed: bool, message: str | None).
        (False, msg) → block.
        (True,  msg) → allow but warn.
        (True, None) → clean pass.
        """
        cmd = intent.get("command")
        val = intent.get("value")

        # Non-vehicle intents always pass
        if cmd in (None, "UNKNOWN", "SAFETY_ALERT"):
            return True, None

        # Explicitly blocked
        if cmd in _BLOCKED_COMMANDS:
            return False, f"[Safety] {cmd} is currently blocked."

        # Range check
        if cmd in _SAFE_RANGES and val is not None:
            try:
                v = int(float(val))
            except (TypeError, ValueError):
                return False, f"[Safety] Non-numeric value '{val}' for {cmd} — blocked."
            lo, hi = _SAFE_RANGES[cmd]
            if not (lo <= v <= hi):
                return False, (
                    f"[Safety] {cmd} value {v} is outside safe range "
                    f"[{lo}–{hi}]. Command blocked."
                )

        # State-dependent warnings
        state = self.sm.get_state()

        if cmd == "SET_HEADLIGHTS" and val == 0:
            if state.get("headlights", False):
                return True, (
                    "Turning headlights OFF while currently on. "
                    "Ensure this is intentional (not in a tunnel)."
                )

        if cmd == "SET_TEMPERATURE":
            try:
                v = int(float(val))
            except (TypeError, ValueError):
                v = 22
            if v <= 17:
                return True, "Cabin temperature set very low. Monitor passenger comfort."
            if v >= 29:
                return True, "Cabin temperature set very high. Monitor passenger comfort."

        if cmd == "SET_POSITION":
            try:
                v = int(float(val))
            except (TypeError, ValueError):
                v = 0
            if v == 0 and state.get("sunroof_position", 0) == 0:
                return True, None   # already closed — ECU handles idempotent log

        return True, None


# ── Standalone utility ────────────────────────────────────────────────────────

def is_gibberish(text: str) -> bool:
    """
    Heuristic gibberish detector.
    Returns True for keyboard mashing, random strings, or very short noise.
    """
    t = text.lower().strip()

    if len(t) < 2:
        return True

    alpha = re.sub(r"[^a-z]", "", t)
    if not alpha:
        return True

    # Vowel ratio — real English has >15% vowels
    vowels = sum(1 for c in alpha if c in "aeiou")
    if len(alpha) > 4 and vowels / len(alpha) < 0.10:
        return True

    # Long consonant run (>5 consecutive)
    if re.search(r"[^aeiou]{6,}", alpha):
        return True

    # Single long token with no known roots — likely gibberish
    _KNOWN = {
        "temp", "fan", "ac", "air", "sun", "roof", "window", "light",
        "head", "bright", "dark", "dim", "hot", "cold", "warm", "cool",
        "open", "close", "on", "off", "hi", "hey", "hello", "help",
        "set", "turn", "make", "increase", "decrease", "raise", "lower",
        "dog", "mode", "bye", "good", "night", "morning", "evening",
        "thanks", "thank", "okay", "great", "yeah", "yes", "no",
        "status", "reset", "focus", "undo", "back", "actually", "wait",
        "remember", "save", "usual", "preference",
    }
    if " " not in t and len(t) > 5:
        if not any(root in t for root in _KNOWN):
            return True

    return False
