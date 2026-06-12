"""
vehicle_modules.py
Three ECU modules: Climate (0x101), Sunroof (0x102), Lighting (0x103).

Design principles
─────────────────
• TOGGLE_AC is value-driven: value=1 forces ON, value=0 forces OFF.
  No blind state flip. Idempotent — "already ON" is logged, not re-executed.
• Every numeric value is clamped at the ECU level as the final safety net.
• All handlers check current state and report "no change" if already at target.
"""

from state_manager  import StateManager
from virtual_can_bus import VirtualCANBus


_BOUNDS: dict[str, tuple[int, int]] = {
    "SET_TEMPERATURE": (17, 29),
    "SET_FAN_SPEED":   (1, 5),
    "SET_POSITION":    (0, 100),
    "SET_BRIGHTNESS":  (0, 100),
}


def _clamp(cmd: str, value: int) -> int:
    if cmd in _BOUNDS:
        lo, hi = _BOUNDS[cmd]
        return max(lo, min(hi, value))
    return value


# ─────────────────────────────────────────────────────────────────────────────

class ClimateModule:
    """CAN ID 0x101 — temperature, fan speed, AC toggle."""

    def __init__(self, sm: StateManager, bus: VirtualCANBus) -> None:
        self.sm = sm
        bus.subscribe("0x101", self.handle_message)

    def handle_message(self, msg: dict) -> None:
        cmd = msg.get("command")
        val = msg.get("value")

        if cmd == "SET_TEMPERATURE":
            val = _clamp(cmd, int(val))
            if self.sm.get("ac_temperature") == val:
                print(f"  [Climate ECU] Temperature already at {val}°C — no change.")
                return
            self.sm.update("ac_temperature", val)
            print(f"  [Climate ECU] Temperature → {val}°C")

        elif cmd == "SET_FAN_SPEED":
            val = _clamp(cmd, int(val))
            if self.sm.get("fan_speed") == val:
                print(f"  [Climate ECU] Fan speed already at {val} — no change.")
                return
            self.sm.update("fan_speed", val)
            print(f"  [Climate ECU] Fan speed → {val}")

        elif cmd == "TOGGLE_AC":
            target  = bool(int(val))
            current = self.sm.get("ac_enabled", False)
            if current == target:
                print(f"  [Climate ECU] AC already {'ON' if target else 'OFF'} — no change.")
                return
            self.sm.update("ac_enabled", target)
            print(f"  [Climate ECU] AC → {'ON' if target else 'OFF'}")

        else:
            print(f"  [Climate ECU] Unknown command: {cmd}")


# ─────────────────────────────────────────────────────────────────────────────

class SunroofModule:
    """CAN ID 0x102 — sunroof position 0–100%."""

    def __init__(self, sm: StateManager, bus: VirtualCANBus) -> None:
        self.sm = sm
        bus.subscribe("0x102", self.handle_message)

    def handle_message(self, msg: dict) -> None:
        cmd = msg.get("command")
        val = msg.get("value")

        if cmd == "SET_POSITION":
            val = _clamp(cmd, int(val))
            if self.sm.get("sunroof_position") == val:
                print(f"  [Sunroof ECU] Already at {val}% — no change.")
                return
            self.sm.update("sunroof_position", val)
            label = "open" if val > 0 else "closed"
            print(f"  [Sunroof ECU] Position → {val}% ({label})")

        else:
            print(f"  [Sunroof ECU] Unknown command: {cmd}")


# ─────────────────────────────────────────────────────────────────────────────

class LightingModule:
    """CAN ID 0x103 — headlights and dashboard brightness."""

    def __init__(self, sm: StateManager, bus: VirtualCANBus) -> None:
        self.sm = sm
        bus.subscribe("0x103", self.handle_message)

    def handle_message(self, msg: dict) -> None:
        cmd = msg.get("command")
        val = msg.get("value")

        if cmd == "SET_HEADLIGHTS":
            target  = bool(int(val))
            current = self.sm.get("headlights", False)
            if current == target:
                print(f"  [Lighting ECU] Headlights already {'ON' if target else 'OFF'} — no change.")
                return
            self.sm.update("headlights", target)
            print(f"  [Lighting ECU] Headlights → {'ON' if target else 'OFF'}")

        elif cmd == "SET_BRIGHTNESS":
            val = _clamp(cmd, int(val))
            if self.sm.get("brightness") == val:
                print(f"  [Lighting ECU] Brightness already at {val}% — no change.")
                return
            self.sm.update("brightness", val)
            print(f"  [Lighting ECU] Dashboard brightness → {val}%")

        else:
            print(f"  [Lighting ECU] Unknown command: {cmd}")
