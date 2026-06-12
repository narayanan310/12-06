"""
dialogue_manager.py
Conversation state tracking, repair detection, and undo/rollback.

Responsibilities
────────────────
• Tracks the last dispatched intent per domain (climate / sunroof / lighting)
  so relative commands resolve against the RIGHT domain, not just "last action".
• Detects repair utterances: "no", "actually", "wait", "undo", "go back", etc.
• Detects confirmation responses: "yes", "confirm", "do it", etc.
• Provides rollback: stores pre-action state per domain so "undo" reverses it.
• Tracks the current conversation state: IDLE | PENDING_CONFIRM | PENDING_REPAIR

Domain-aware context prevents "make it cooler" from touching the sunroof
just because the sunroof was the last thing moved.
"""

import time
from enum import Enum


class DialogueState(Enum):
    IDLE            = "idle"
    PENDING_CONFIRM = "pending_confirm"   # waiting for yes/no before executing
    PENDING_REPAIR  = "pending_repair"    # last action may need correction


# Map each CAN command to its domain
_CMD_DOMAIN: dict[str, str] = {
    "SET_TEMPERATURE": "climate",
    "SET_FAN_SPEED":   "climate",
    "TOGGLE_AC":       "climate",
    "SET_POSITION":    "sunroof",
    "SET_HEADLIGHTS":  "lighting",
    "SET_BRIGHTNESS":  "lighting",
}

# ── Repair trigger phrases ────────────────────────────────────────────────────
_REPAIR_PHRASES = [
    "no", "nope", "nah", "not that", "not right",
    "actually", "wait", "hold on", "stop",
    "undo", "undo that", "reverse", "revert",
    "go back", "go back to", "that was wrong",
    "i didn't mean", "i meant", "wrong one",
    "too much", "that's too much", "thats too much",
    "too little", "that's too little",
    "cancel", "cancel that", "never mind", "nevermind",
    "scratch that",
]

# ── Confirmation trigger phrases ──────────────────────────────────────────────
_CONFIRM_PHRASES = [
    "yes", "yeah", "yep", "yup", "sure", "okay", "ok",
    "do it", "go ahead", "confirm", "fine", "alright",
    "that's fine", "thats fine", "sounds good",
]

# ── "I meant X domain" re-routing hints ──────────────────────────────────────
_DOMAIN_HINT: dict[str, str] = {
    "temperature": "climate",
    "temp":        "climate",
    "ac":          "climate",
    "fan":         "climate",
    "sunroof":     "sunroof",
    "window":      "sunroof",
    "roof":        "sunroof",
    "light":       "lighting",
    "lights":      "lighting",
    "brightness":  "lighting",
    "headlight":   "lighting",
}


class DialogueManager:
    def __init__(self) -> None:
        self.state: DialogueState = DialogueState.IDLE

        # Per-domain last-dispatched intent (for relative resolution + undo)
        self._last_by_domain: dict[str, dict] = {}

        # Pre-action snapshot per domain (for undo)
        self._undo_stack: dict[str, dict] = {}

        # Intent awaiting confirmation
        self._pending_intent: dict | None = None

        # TTL: how long context entries stay valid (seconds)
        self._ttl = 180

    # ── Domain tracking ───────────────────────────────────────────────────

    def record(self, input_text: str, intent: dict, pre_state: dict) -> None:
        """Called after a successful dispatch to record the action."""
        domain = _CMD_DOMAIN.get(intent.get("command", ""), "unknown")
        entry  = {
            "input":     input_text,
            "intent":    intent,
            "domain":    domain,
            "timestamp": time.time(),
        }
        self._last_by_domain[domain] = entry
        # Save the state BEFORE this action so we can undo it
        self._undo_stack[domain]     = dict(pre_state)
        self.state = DialogueState.IDLE

    def last_for_domain(self, domain: str) -> dict | None:
        """Return the most recent valid intent for a specific domain."""
        entry = self._last_by_domain.get(domain)
        if entry and (time.time() - entry["timestamp"]) < self._ttl:
            return entry["intent"]
        return None

    def last_any(self) -> dict | None:
        """Return the most recently dispatched intent across all domains."""
        candidates = [
            e for e in self._last_by_domain.values()
            if (time.time() - e["timestamp"]) < self._ttl
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda e: e["timestamp"])["intent"]

    def undo_intent_for_domain(self, domain: str) -> dict | None:
        """
        Return an intent that restores the state BEFORE the last action
        in the given domain, or None if nothing to undo.
        """
        pre_state = self._undo_stack.get(domain)
        last      = self._last_by_domain.get(domain)
        if not pre_state or not last:
            return None

        cmd = last["intent"].get("command")
        can_id = last["intent"].get("can_id")

        # Map command → the state key it affects
        _CMD_STATE_KEY = {
            "SET_TEMPERATURE": "ac_temperature",
            "SET_FAN_SPEED":   "fan_speed",
            "SET_POSITION":    "sunroof_position",
            "SET_BRIGHTNESS":  "brightness",
            "SET_HEADLIGHTS":  "headlights",
            "TOGGLE_AC":       "ac_enabled",
        }
        state_key = _CMD_STATE_KEY.get(cmd)
        if not state_key:
            return None

        old_value = pre_state.get(state_key)
        if old_value is None:
            return None

        # Boolean state keys need int conversion for CAN
        if isinstance(old_value, bool):
            old_value = 1 if old_value else 0

        return {
            "can_id":     can_id,
            "command":    cmd,
            "value":      old_value,
            "reason":     f"Undo — restoring previous value ({old_value}).",
            "confidence": 0.95,
            "handled_by": "DialogueManager",
            "latency":    "0ms",
        }

    # ── Repair detection ──────────────────────────────────────────────────

    def is_repair(self, text: str) -> bool:
        t = text.lower().strip()
        return any(phrase in t for phrase in _REPAIR_PHRASES)

    def is_confirmation(self, text: str) -> bool:
        t = text.lower().strip()
        return any(phrase in t for phrase in _CONFIRM_PHRASES)

    def extract_domain_hint(self, text: str) -> str | None:
        """
        If the driver says 'I meant inside' or 'I meant the temperature',
        extract which domain they're referring to.
        """
        t = text.lower()
        for keyword, domain in _DOMAIN_HINT.items():
            if keyword in t:
                return domain
        return None

    # ── Pending confirmation flow ─────────────────────────────────────────

    def set_pending(self, intent: dict) -> None:
        self._pending_intent = intent
        self.state           = DialogueState.PENDING_CONFIRM

    def pop_pending(self) -> dict | None:
        intent               = self._pending_intent
        self._pending_intent = None
        self.state           = DialogueState.IDLE
        return intent

    def clear_pending(self) -> None:
        self._pending_intent = None
        self.state           = DialogueState.IDLE

    # ── Repair resolution ─────────────────────────────────────────────────

    def resolve_repair(self, text: str) -> tuple[str, dict | None]:
        """
        Called when is_repair() is True.

        Returns (action, intent):
          ('undo', undo_intent)    — reverse the last action in detected domain
          ('undo_last', undo_intent) — reverse last action (no domain hint)
          ('cancel_pending', None) — there was a pending confirmation; cancelling
          ('nothing_to_undo', None) — no recent action to reverse
          ('unclear', None)        — repair detected but can't determine what to fix
        """
        # If there's a pending confirmation, cancel it
        if self.state == DialogueState.PENDING_CONFIRM:
            self.clear_pending()
            return ("cancel_pending", None)

        # Try to identify which domain the driver wants to repair
        domain_hint = self.extract_domain_hint(text)

        if domain_hint:
            intent = self.undo_intent_for_domain(domain_hint)
            if intent:
                return ("undo", intent)

        # Fall back to last-any domain
        last = self.last_any()
        if last:
            domain = _CMD_DOMAIN.get(last.get("command", ""), "unknown")
            intent = self.undo_intent_for_domain(domain)
            if intent:
                return ("undo_last", intent)

        # Check if they just mean "never mind" (no prior action)
        if any(p in text.lower() for p in ["never mind", "nevermind", "cancel", "scratch"]):
            return ("nothing_to_undo", None)

        return ("unclear", None)
