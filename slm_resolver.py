"""
slm_resolver.py
SLM fallback resolver — strict last resort with hardened prompt.

Fixes applied
─────────────
- __init__ dunder corruption fixed (was **init**)
- No other logic changes; original code was correct
"""

import urllib.request
import json
import time
from intent_parser import extract_json

_VALUE_BOUNDS: dict[str, tuple[int, int]] = {
    "SET_TEMPERATURE": (17, 29),
    "SET_FAN_SPEED":   (1,  5),
    "TOGGLE_AC":       (0,  1),
    "SET_POSITION":    (0, 100),
    "SET_HEADLIGHTS":  (0,  1),
    "SET_BRIGHTNESS":  (0, 100),
    "UNKNOWN":         (0,  0),
}

_VALID_COMMANDS: set[tuple[str, str]] = {
    ("0x101", "SET_TEMPERATURE"),
    ("0x101", "SET_FAN_SPEED"),
    ("0x101", "TOGGLE_AC"),
    ("0x102", "SET_POSITION"),
    ("0x103", "SET_HEADLIGHTS"),
    ("0x103", "SET_BRIGHTNESS"),
    ("UNKNOWN", "UNKNOWN"),
}

_CMD_KEYWORDS: dict[str, list[str]] = {
    "SET_TEMPERATURE": ["temp", "hot", "cold", "warm", "cool", "better", "comfort", "improve"],
    "SET_FAN_SPEED":   ["fan", "air", "better", "comfort"],
    "SET_POSITION":    ["sunroof", "window", "roof", "air", "breeze", "better"],
    "SET_HEADLIGHTS":  ["light", "headlight", "dark", "better"],
    "SET_BRIGHTNESS":  ["bright", "dim", "better"],
    "TOGGLE_AC":       ["ac", "better"],
    "UNKNOWN":         [],
}


def _sanity_check(text: str, command: str) -> bool:
    if command == "UNKNOWN":
        return True
    keywords = _CMD_KEYWORDS.get(command, [])
    t = text.lower()
    if any(word in t for word in ["better", "improve", "comfort", "fix"]):
        return True
    return any(kw in t for kw in keywords)


class SLMIntentResolver:
    def __init__(self, host: str = "http://127.0.0.1:8080") -> None:
        self._url        = f"{host}/completion"
        self._health_url = f"{host}/health"

    def health_check(self) -> bool:
        try:
            with urllib.request.urlopen(self._health_url, timeout=3):
                return True
        except Exception:
            return False

    def resolve(self, text: str) -> dict | None:
        start = time.monotonic()

        prompt = (
            f"<|im_start|>system\n"
            f"You are a vehicle command classifier. "
            f"Reply with ONLY valid JSON. No thinking, no extra text.\n"
            f'Schema: {{"can_id":"0x101","function":"SET_TEMPERATURE","value":22,"reason":"short reason"}}\n'
            f"Valid functions: SET_TEMPERATURE, SET_FAN_SPEED, SET_POSITION, "
            f"SET_HEADLIGHTS, SET_BRIGHTNESS, TOGGLE_AC\n"
            f"For vague requests like 'make it better' → use SET_TEMPERATURE value 20 or 24.\n"
            f"<|im_end|>\n"
            f"<|im_start|>user\n{text}<|im_end|>\n"
            f"<|im_start|>assistant\n{{"
        )

        payload = {
            "prompt":       prompt,
            "n_predict":    80,
            "temperature":  0.0,
            "top_k":        1,
            "top_p":        0.1,
            "stop":         ["<|im_end|>", "\n", "```"],
            "cache_prompt": True,
        }

        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                result      = json.loads(resp.read().decode("utf-8"))
                latency     = time.monotonic() - start
                raw_content = result.get("content", "").strip()
                print(f"  [SLM Raw] {raw_content}")

                # Force start with {
                if not raw_content.startswith("{"):
                    raw_content = "{" + raw_content

                parsed = extract_json(raw_content)
                if not parsed:
                    print("  [SLM] Failed to parse JSON")
                    return None

                can_id   = str(parsed.get("can_id", "")).strip()
                function = str(
                    parsed.get("function", parsed.get("command", ""))
                ).strip()
                reason   = str(parsed.get("reason", "SLM fallback"))

                try:
                    value = int(float(
                        parsed.get("value", parsed.get("temperature", 22))
                    ))
                except Exception:
                    value = 22

                if (can_id, function) not in _VALID_COMMANDS:
                    print(f"  [SLM Rejected] Invalid pair: {can_id} {function}")
                    return None

                if not _sanity_check(text, function):
                    print("  [SLM Rejected] No keyword match")
                    return None

                if function in _VALUE_BOUNDS:
                    lo, hi = _VALUE_BOUNDS[function]
                    value  = max(lo, min(hi, value))

                return {
                    "can_id":     can_id,
                    "command":    function,
                    "value":      value,
                    "reason":     reason,
                    "confidence": 0.60,
                    "handled_by": "SLM",
                    "latency":    f"{latency:.2f}s",
                }

        except Exception as exc:
            print(f"  [SLM Error] {exc}")
            return None
