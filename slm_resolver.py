"""
slm_resolver.py
SLM fallback resolver — strict last resort with hardened prompt.

Fixes applied (v3 - Bulletproof Edition)
────────────────────────────────────────
- Added "Vibe/Mood" vocabulary to _CHANGE_WILDCARDS ("relaxing", "vibe", "drive") 
  so the sanity check doesn't block abstract scene requests.
- Upgraded the SLM Prompt to explicitly teach the model how to handle 
  abstract/vibe requests (pick ONE logical system to change).
- Added a new few-shot example specifically for "relaxing night drive".
- Added a Markdown stripper to sanitize the SLM output before JSON extraction 
  (catches models that stubbornly wrap answers in ```json blocks).
- Extended timeout for edge device (Raspberry Pi) capability.
"""

import urllib.request
import json
import time
import re
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

# ── Metaphor / sentiment keyword banks ──────────────────────────────────────
_HOT_PHRASES = {
    "sauna", "oven", "furnace", "sweat", "sweating", "unbearable", "burning up",
    "roasting", "boiling alive", "scorching", "baking", "melting", "suffocating",
    "feels like fire", "way too warm", "can't breathe", "too warm", "too hot",
    "it's hell", "inferno", "blazing",
}

_COLD_PHRASES = {
    "antarctica", "arctic", "north pole", "icebox", "ice box", "freezer",
    "shivering", "shivers", "goosebumps", "goose bumps", "freeze", "frozen",
    "numb", "teeth chattering", "too cold", "really cold", "so cold",
    "feels like winter",
}

_VENT_AIR_PHRASES = {
    "recycled", "stale", "stuffy", "musty", "stagnant", "no air", "need air",
    "air feels", "can't breathe", "suffocating", "lacking oxygen", "ventilation",
    "fresh air", "open it up", "breathe", "breathable",
}

_LIGHT_PHRASES = {
    "dark", "can't see", "cannot see", "night", "blinded", "too bright",
    "headlight", "lights", "visibility", "glare", "dim", "bright", "evening",
}

# EXTREMELY IMPORTANT: Vibe/Mood wildcards added here so the sanity check 
# doesn't block abstract requests like "relaxing night drive".
_CHANGE_WILDCARDS = {
    "better", "improve", "comfort", "fix", "something", "change",
    "adjust", "different", "do something", "help", 
    "vibe", "mood", "relax", "relaxing", "drive", "prepare", "scene", "chill"
}

# Maps SLM function name → which phrase sets are acceptable evidence
_SANITY_MAP: dict[str, list[set]] = {
    "SET_TEMPERATURE": [_HOT_PHRASES, _COLD_PHRASES, _VENT_AIR_PHRASES, _CHANGE_WILDCARDS,
                        {"temp", "temperature", "hot", "cold", "warm", "cool", "heat",
                         "climate", "cabin", "degrees"}],
    "SET_FAN_SPEED":   [_VENT_AIR_PHRASES, _CHANGE_WILDCARDS,
                        {"fan", "air", "blower", "speed", "airflow"}],
    "SET_POSITION":    [_VENT_AIR_PHRASES, _CHANGE_WILDCARDS,
                        {"sunroof", "window", "roof", "open", "close", "air"}],
    "SET_HEADLIGHTS":  [_LIGHT_PHRASES, _CHANGE_WILDCARDS,
                        {"light", "headlight", "dark", "see", "vision"}],
    "SET_BRIGHTNESS":  [_LIGHT_PHRASES, _CHANGE_WILDCARDS,
                        {"bright", "dim", "screen", "display", "dashboard"}],
    "TOGGLE_AC":       [_VENT_AIR_PHRASES, _CHANGE_WILDCARDS,
                        {"ac", "air con", "conditioning", "cool"}],
    "UNKNOWN":         [],
}


def _sanity_check(text: str, command: str) -> bool:
    if command == "UNKNOWN":
        return True

    t = text.lower()

    if any(kw in t for kw in _CHANGE_WILDCARDS):
        return True

    phrase_sets = _SANITY_MAP.get(command, [])
    for phrase_set in phrase_sets:
        if any(phrase in t for phrase in phrase_set):
            return True

    return False


# ── Few-shot examples embedded in the prompt ────────────────────────────────
_FEW_SHOT = (
    'User: "it feels like a sauna in here"\n'
    'Assistant: {"can_id":"0x101","function":"SET_TEMPERATURE","value":18,"reason":"hot metaphor - cooling down"}\n'
    'User: "its antarctica in this car"\n'
    'Assistant: {"can_id":"0x101","function":"SET_TEMPERATURE","value":26,"reason":"cold metaphor - warming up"}\n'
    'User: "the air feels recycled and stale"\n'
    'Assistant: {"can_id":"0x101","function":"SET_FAN_SPEED","value":4,"reason":"stale air - increase ventilation"}\n'
    'User: "Prepare the car for a long, relaxing night drive."\n'
    'Assistant: {"can_id":"0x103","function":"SET_BRIGHTNESS","value":15,"reason":"night drive - dimming dashboard for comfort"}\n'
    'User: "this is unbearable"\n'
    'Assistant: {"can_id":"0x101","function":"SET_TEMPERATURE","value":18,"reason":"discomfort - defaulting to cool"}\n'
)


class SLMIntentResolver:
    def __init__(self, host: str = "http://127.0.0.1:8080") -> None:
        self._url        = f"{host}/completion"
        self._health_url = f"{host}/health"

    def health_check(self) -> bool:
        try:
            # Quick 5-second check so the app doesn't hang on boot
            with urllib.request.urlopen(self._health_url, timeout=5):
                return True
        except Exception:
            return False

    def resolve(self, text: str) -> dict | None:
        start = time.monotonic()

        prompt = (
            f"<|im_start|>system\n"
            f"You are a vehicle command classifier for a smart car assistant.\n"
            f"Reply with ONLY valid JSON. No thinking, no explanation, no markdown.\n"
            f'Schema: {{"can_id":"0x101","function":"SET_TEMPERATURE","value":22,"reason":"short reason"}}\n'
            f"Valid functions and their CAN IDs:\n"
            f"  0x101 → SET_TEMPERATURE (17-29°C), SET_FAN_SPEED (1-5), TOGGLE_AC (0=off,1=on)\n"
            f"  0x102 → SET_POSITION (0-100% sunroof)\n"
            f"  0x103 → SET_HEADLIGHTS (0=off,1=on), SET_BRIGHTNESS (0-100%)\n"
            f"\n"
            f"IMPORTANT: Pick the value that makes sense for the emotion:\n"
            f"  Hot/stuffy/sauna → SET_TEMPERATURE value 18\n"
            f"  Cold/freezing/arctic → SET_TEMPERATURE value 26\n"
            f"  Stale/recycled air → SET_FAN_SPEED value 4\n"
            f"  Vibe/Mood/Abstract → Pick the ONE most relevant system (e.g., SET_BRIGHTNESS 15 or SET_TEMPERATURE 22)\n"
            f"\nExamples:\n{_FEW_SHOT}"
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
            "stop":         ["<|im_end|>", "\n\n"],
            "cache_prompt": False,
        }

        req = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        try:
            # 120s timeout gives the Pi edge processor plenty of time
            with urllib.request.urlopen(req, timeout=120) as resp:
                result      = json.loads(resp.read().decode("utf-8"))
                latency     = time.monotonic() - start
                raw_content = result.get("content", "").strip()
                
                # Sanitize: Strip out pesky markdown blocks if the SLM hallucinated them
                raw_content = re.sub(r"^```json\s*", "", raw_content, flags=re.IGNORECASE)
                raw_content = re.sub(r"```\s*$", "", raw_content)
                raw_content = raw_content.strip()

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
                    # Robust number parsing
                    val_raw = parsed.get("value", parsed.get("temperature", 22))
                    if isinstance(val_raw, str):
                        # Extract just the digits if it hallucinated "22C" or "15%"
                        digits = re.findall(r"\d+", val_raw)
                        value = int(digits[0]) if digits else 22
                    else:
                        value = int(float(val_raw))
                except Exception:
                    value = 22

                if (can_id, function) not in _VALID_COMMANDS:
                    print(f"  [SLM Rejected] Invalid pair: {can_id} {function}")
                    return None

                if not _sanity_check(text, function):
                    print(f"  [SLM Rejected] No plausible match for '{function}' in: {text!r}")
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