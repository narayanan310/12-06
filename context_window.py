"""
context_window.py
Domain-aware rolling conversation memory with TTL.

Key fix over prior version
──────────────────────────
resolve_relative() now accepts an optional domain hint from the
DialogueManager so "make it cooler" resolves against the CLIMATE domain,
not the last actuator touched (which might have been the sunroof).
If no domain hint is given it falls back to "last action of any domain"
for purely relative phrases like "a bit more".

Fixes applied
─────────────
- __init__ / __init__ dunder corruption fixed
- _DELTA / _BOUNDS asterisk typos fixed in resolve_relative()
- self._history asterisk typo fixed in check_proactive_nudge()
- last_cmd.split('_') fixed (was split('*'))
- "temperature" / "temp" added to domain-detection keyword block
  → "increase temperature" now resolves against CLIMATE, not last fan action
- Added directional verbs (increase/decrease/raise/lower/turn up/turn down)
  to domain detection so bare directional + domain-name utterances work
"""

import time
from collections import deque

_DELTA: dict[str, int] = {
    "SET_TEMPERATURE": 2,
    "SET_FAN_SPEED":   1,
    "SET_POSITION":   15,
    "SET_BRIGHTNESS": 10,
}

_BOUNDS: dict[str, tuple[int, int]] = {
    "SET_TEMPERATURE": (17, 29),
    "SET_FAN_SPEED":   (1,  5),
    "SET_POSITION":    (0, 100),
    "SET_BRIGHTNESS":  (0, 100),
}

# Domain → commands belonging to it
_DOMAIN_CMDS: dict[str, set[str]] = {
    "climate":  {"SET_TEMPERATURE", "SET_FAN_SPEED", "TOGGLE_AC"},
    "sunroof":  {"SET_POSITION"},
    "lighting": {"SET_HEADLIGHTS", "SET_BRIGHTNESS"},
}

_INCREASE_KW = {
    "more", "higher", "up", "increase", "raise",
    "bit more", "little more", "hotter", "warmer",
    "louder", "brighter", "faster", "stronger",
    "turn up", "crank up", "bump up",
}
_DECREASE_KW = {
    "less", "lower", "down", "decrease", "reduce",
    "bit less", "little less", "cooler", "colder",
    "quieter", "dimmer", "slower", "gentler", "softer",
    "turn down", "crank down", "dial down",
}


def _domain_for_cmd(cmd: str) -> str | None:
    for domain, cmds in _DOMAIN_CMDS.items():
        if cmd in cmds:
            return domain
    return None


class ContextWindow:
    def __init__(self, maxlen: int = 8, ttl_seconds: int = 180) -> None:
        self._history: deque = deque(maxlen=maxlen)
        self._ttl = ttl_seconds

    # ── Write ─────────────────────────────────────────────────────────────
    def push(self, input_text: str, intent: dict) -> None:
        self._history.append({
            "input":     input_text,
            "command":   intent.get("command"),
            "can_id":    intent.get("can_id"),
            "value":     intent.get("value"),
            "domain":    _domain_for_cmd(intent.get("command", "")),
            "timestamp": time.time(),
        })

    # ── Read ──────────────────────────────────────────────────────────────
    def _valid(self) -> list[dict]:
        now = time.time()
        return [e for e in self._history if now - e["timestamp"] < self._ttl]

    def last_valid(self) -> dict | None:
        entries = self._valid()
        return entries[-1] if entries else None

    def last_for_domain(self, domain: str) -> dict | None:
        entries = [e for e in self._valid() if e.get("domain") == domain]
        return entries[-1] if entries else None

    # ── Relative resolution ───────────────────────────────────────────────
    def resolve_relative(
        self,
        text:   str,
        domain: str | None = None,
    ) -> dict | None:
        """
        Enhanced relative resolver with explicit domain detection.

        Domain detection order:
          1. Keywords in current utterance  (most specific)
          2. domain hint passed by DialogueManager
          3. last_valid() across all domains  (broadest fallback)

        BUG FIX: "temperature" / "temp" are now in the climate keyword list,
        so "increase temperature" correctly targets SET_TEMPERATURE and not
        whatever command was last used (e.g. SET_FAN_SPEED).
        """
        t = text.lower().strip()

        # === Domain Detection from current utterance ===
        current_domain: str | None = None

        # Climate — temperature keywords (FIXED: was missing "temp"/"temperature")
        if any(word in t for word in [
            "temp", "temperature", "heat", "warm", "cool", "cold", "hot",
            "degrees", "celsius", "ac", "air con", "climate",
        ]):
            current_domain = "climate"
            # Prefer SET_TEMPERATURE for this utterance; handled below via domain lookup

        # Climate — fan keywords (checked after temperature so explicit "temp" wins)
        elif any(word in t for word in [
            "fan", "blower", "speed", "airflow",
        ]):
            current_domain = "climate"

        # Sunroof
        elif any(word in t for word in ["sunroof", "roof", "moonroof"]):
            current_domain = "sunroof"

        # Lighting
        elif any(word in t for word in [
            "bright", "brightness", "dim", "dashboard", "screen", "display",
        ]):
            current_domain = "lighting"

        # --- Direction detection ---
        words  = set(t.split())
        going_up = bool(
            (words & _INCREASE_KW) or any(kw in t for kw in _INCREASE_KW)
        )
        going_dn = bool(
            (words & _DECREASE_KW) or any(kw in t for kw in _DECREASE_KW)
        )

        # Smart fallback for very short replies
        if not (going_up or going_dn):
            if t in {"more", "higher", "up", "again", "even more"}:
                going_up = True
            elif t in {"less", "lower", "down", "bit less"}:
                going_dn = True
            else:
                return None

        # --- Context lookup (domain priority order) ---
        _TEMP_WORDS = {
            "temp", "temperature", "heat", "warm", "cool",
            "cold", "hot", "degrees", "celsius",
        }
        _FAN_WORDS = {"fan", "blower", "speed", "airflow"}

        if current_domain:
            # Temperature-specific utterance → only look at SET_TEMPERATURE history.
            # If no temperature history exists return None so the Regex/SLM stage
            # can handle it correctly (e.g. "increase temperature" → regex → 24°C).
            if current_domain == "climate" and any(w in t for w in _TEMP_WORDS):
                temp_entries = [
                    e for e in self._valid()
                    if e.get("command") == "SET_TEMPERATURE"
                ]
                if not temp_entries:
                    return None          # no temperature baseline → let Regex take over
                last = temp_entries[-1]

            # Fan-specific utterance → only look at SET_FAN_SPEED history.
            elif current_domain == "climate" and any(w in t for w in _FAN_WORDS):
                fan_entries = [
                    e for e in self._valid()
                    if e.get("command") == "SET_FAN_SPEED"
                ]
                if not fan_entries:
                    return None          # no fan baseline → let Regex take over
                last = fan_entries[-1]

            else:
                last = self.last_for_domain(current_domain)
        elif domain:
            last = self.last_for_domain(domain)
        else:
            last = self.last_valid()

        if not last:
            return None

        cmd = last["command"]
        if cmd not in _DELTA:
            return None

        delta   = _DELTA[cmd]
        cur_val = last["value"]
        new_val = cur_val + delta if going_up else cur_val - delta
        lo, hi  = _BOUNDS.get(cmd, (0, 100))
        new_val = max(lo, min(hi, new_val))

        at_limit  = (new_val == cur_val)
        direction = ("maximum" if going_up else "minimum") if at_limit else None

        return {
            "can_id":     last["can_id"],
            "command":    cmd,
            "value":      new_val,
            "reason":     (
                f"Already at {direction} ({new_val})."
                if at_limit else
                f"Relative adjustment: {cur_val} → {new_val}."
            ),
            "confidence": 0.85 if at_limit else 0.93,
            "handled_by": "ContextWindow",
            "latency":    "0.1ms",
            "_at_limit":  at_limit,
        }

    # ── Proactive nudge ───────────────────────────────────────────────────
    def check_proactive_nudge(self) -> str | None:
        """
        If driver has adjusted the same setting 3+ times in one direction
        in the last 5 minutes, suggest a direct target instead.
        """
        now    = time.time()
        # FIXED: was self.*history (asterisk typo)
        recent = [e for e in self._history if now - e["timestamp"] < 300]
        if len(recent) < 3:
            return None

        last_cmd = recent[-1]["command"]
        tail     = [e for e in recent if e["command"] == last_cmd][-3:]
        if len(tail) < 3:
            return None

        vals = [e["value"] for e in tail]

        if vals[0] > vals[1] > vals[2]:
            # FIXED: was split('*'), should be split('_')
            label = last_cmd.replace("_", " ").title()
            return (
                f"You've lowered {label} three times in a row "
                f"(now at {vals[2]}). "
                f"Say 'set {last_cmd.split('_')[-1].lower()} to [value]' "
                f"for a precise target."
            )
        if vals[0] < vals[1] < vals[2]:
            label = last_cmd.replace("_", " ").title()
            return (
                f"You've raised {label} three times in a row "
                f"(now at {vals[2]}). "
                f"Say 'set {last_cmd.split('_')[-1].lower()} to [value]' "
                f"for a precise target."
            )

        return None
