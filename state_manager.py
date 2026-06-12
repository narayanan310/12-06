"""
state_manager.py
Centralised vehicle state store with asyncio-safe lock.

All public methods are safe to call from both sync and async contexts.
The asyncio.Lock is held only during updates; reads copy the dict out
before returning so callers never block each other.
"""

import asyncio


_DEFAULT_STATE: dict = {
    "ac_temperature":   22,
    "fan_speed":         2,
    "ac_enabled":    False,
    "sunroof_position":  0,
    "headlights":    False,
    "brightness":       50,
}


class StateManager:
    def __init__(self) -> None:
        self._state: dict      = dict(_DEFAULT_STATE)
        self._lock             = asyncio.Lock()
        self._subscribers: list = []

    # ── Sync-safe helpers (used by ECU sync callbacks) ────────────────────

    def update(self, key: str, value) -> None:
        """Update a single key (sync-safe — no lock needed for GIL-protected dict)."""
        self._state[key] = value
        for cb in self._subscribers:
            try:
                cb(key, value)
            except Exception:
                pass

    def get(self, key: str, default=None):
        return self._state.get(key, default)

    def get_state(self) -> dict:
        """Return a shallow copy — safe to read outside any lock."""
        return dict(self._state)

    def subscribe(self, callback) -> None:
        self._subscribers.append(callback)

    def reset_to_defaults(self) -> None:
        self._state = dict(_DEFAULT_STATE)

    def snapshot(self) -> str:
        s = self.get_state()
        return (
            f"  Temperature : {s['ac_temperature']}°C\n"
            f"  Fan Speed   : {s['fan_speed']}\n"
            f"  AC          : {'ON' if s['ac_enabled'] else 'OFF'}\n"
            f"  Sunroof     : {s['sunroof_position']}%\n"
            f"  Headlights  : {'ON' if s['headlights'] else 'OFF'}\n"
            f"  Brightness  : {s['brightness']}%"
        )
