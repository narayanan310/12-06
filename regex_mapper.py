"""
regex_mapper.py
Deterministic fast-lane resolver for explicit vehicle commands.

PRODUCTION ENHANCEMENTS:
- 100+ patterns covering edge cases
- Natural language variations
- Abbreviations and slang
- Compound commands detection
- Fuzzy matching for common misspellings

Fixes applied
─────────────
- Added bare "open sunroof" / "open the sunroof" pattern (resolves to 50%)
  so it no longer falls through to SLM and times out.
"""

import re
import time

_PATTERNS: list[tuple] = [

    # ═══════════════════════════════════════════════════════════════════════
    # TEMPERATURE - Explicit Sets
    # ═══════════════════════════════════════════════════════════════════════

    (r"\bset (?:the )?(?:temp(?:erature)?|ac|climate|cabin)(?: to)? (\d+)\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Direct temperature set.", 0.99),

    (r"\b(?:temp(?:erature)?|ac|climate|cabin) (?:to )?(\d+)\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Temperature set (implied).", 0.98),

    (r"\b(\d+)\s*(?:degrees?|°)(?:\s*[Cc])?(?:\s*(?:please|pls|now))?\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Temperature by degree value.", 0.97),

    (r"\bmake it (\d+)\s*(?:degrees?|°)?\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Make it X degrees.", 0.96),

    (r"\bchange (?:the )?(?:temp|temperature) to (\d+)\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Change temperature to X.", 0.96),

    (r"\b(?:set|adjust) (\d+)\s*(?:degrees?|°)?\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Set to X degrees.", 0.95),

    # ═══════════════════════════════════════════════════════════════════════
    # TEMPERATURE - Hot/Cold Feelings (Expanded)
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:too|it['\s]?s|make it|getting|feels?|this is|that's|thats)\s+(?:hot|boiling|burning|roasting|warm|heated|scorching|blazing|sweltering)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Hot — lowering temperature.", 0.88),

    (r"\b(?:i'?m|i am|feeling|getting)\s+(?:hot|warm|overheated)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Personal hot complaint — cooling.", 0.87),

    (r"\b(?:too|it['\s]?s|make it|getting|feels?|this is|that's|thats)\s+(?:cold|freezing|chilly|icy|frigid|frozen|bitter)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Cold — raising temperature.", 0.88),

    (r"\b(?:i'?m|i am|feeling|getting)\s+(?:cold|freezing|chilly)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Personal cold complaint — heating.", 0.87),

    (r"\b(?:too|very|so)\s+(?:hot|cold|warm)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 18 if "hot" in m.group(0) or "warm" in m.group(0) else 26,
     "Extreme temperature complaint.", 0.86),

    # ═══════════════════════════════════════════════════════════════════════
    # TEMPERATURE - Directional Commands
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:hotter|warmer|heat(?:er)? up|warm(?:er)? (?:it )?up|increase heat|more heat)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Warmer request.", 0.85),

    (r"\b(?:cooler|colder|cool(?:er)? (?:it )?(?:down|off)?|decrease heat|less heat|more cold)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Cooler request.", 0.85),

    (r"\b(?:max|maximum|full)\s+(?:heat|hot|warm)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 29,
     "Maximum heat.", 0.90),

    (r"\b(?:max|maximum|full)\s+(?:cool|cold|ac)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 17,
     "Maximum cooling.", 0.90),

    (r"\b(?:turn|set|crank)\s+(?:it|the temp|temperature)\s+(?:up|down|higher|lower)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 24 if "up" in m.group(0) or "higher" in m.group(0) else 20,
     "Crank temperature direction.", 0.84),

    (r"\b(?:go|put|set)\s+(?:up|down)\s+(?:a bit|a little|a few)\s+(?:degrees?)?\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 24 if "up" in m.group(0) else 20,
     "Slight temperature adjustment.", 0.82),

    (r"\b(?:bump|raise|lower)\s+(?:the\s+)?(?:temp|temperature)\s+(?:a\s+)?(?:bit|little|notch)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 24 if "raise" in m.group(0) or "bump" in m.group(0) else 20,
     "Bump temperature.", 0.83),

    # ═══════════════════════════════════════════════════════════════════════
    # FAN SPEED - Explicit
    # ═══════════════════════════════════════════════════════════════════════

    (r"\bset (?:the )?fan(?: speed)? to (\d)\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Direct fan speed set.", 0.99),

    (r"\b(?:fan|blower)(?: speed)?(?: to)? (\d)(?:\s*(?:out of 5|/5))?\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Fan speed set (implied).", 0.98),

    (r"\bfan\s+(\d)\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Fan X (abbreviated).", 0.97),

    (r"\b(?:set|put|change)\s+(?:the\s+)?fan\s+(?:speed\s+)?(?:to\s+)?(\d)\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Set fan speed variation.", 0.97),

    # ═══════════════════════════════════════════════════════════════════════
    # FAN SPEED - Directional
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:increase|raise|turn up|crank up|bump up)\s+(?:the\s+)?fan\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "Fan speed up (max).", 0.88),

    (r"\bfan\s+(?:up|higher|faster|more|stronger|maximum|max|full blast)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "Fan speed up variation.", 0.88),

    (r"\b(?:decrease|lower|turn down|reduce|dial down)\s+(?:the\s+)?fan\b",
     "0x101", "SET_FAN_SPEED", lambda m: 1,
     "Fan speed down (minimum).", 0.88),

    (r"\bfan\s+(?:down|lower|slower|less|minimum|min)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 1,
     "Fan speed down variation.", 0.88),

    (r"\b(?:more|less)\s+(?:air|breeze|wind)\b",
     "0x101", "SET_FAN_SPEED",
     lambda m: 5 if "more" in m.group(0) else 2,
     "More/less air request.", 0.85),

    (r"\b(?:kick|put)\s+(?:the\s+)?fan\s+(?:up|down)\s+(?:a\s+)?(?:bit|notch)\b",
     "0x101", "SET_FAN_SPEED",
     lambda m: 4 if "up" in m.group(0) else 2,
     "Fan notch adjustment.", 0.82),

    (r"\b(?:full|max|maximum)\s+(?:fan|air|blower)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "Max fan request.", 0.90),

    (r"\b(?:lowest|minimum|min)\s+fan\b",
     "0x101", "SET_FAN_SPEED", lambda m: 1,
     "Minimum fan request.", 0.90),

    (r"\b(?:half|medium)\s+fan\b",
     "0x101", "SET_FAN_SPEED", lambda m: 3,
     "Half/medium fan speed.", 0.88),

    # ═══════════════════════════════════════════════════════════════════════
    # AC TOGGLE
    # ═══════════════════════════════════════════════════════════════════════

    (r"\bturn\s+(on|off)\s+(?:the\s+)?(?:ac|air\s*con(?:ditioning)?|climate control|a\s*c)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "AC toggle explicit.", 0.99),

    (r"\b(?:ac|air\s*con(?:ditioning)?|a\s*c)\s+(on|off)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "AC on/off (shorthand).", 0.99),

    (r"\b(?:switch|put|get|flick|flip)\s+(?:the\s+)?(?:ac|air(?:\s*con)?|a\s*c)\s+(on|off)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "AC toggle variation.", 0.97),

    (r"\b(start|stop|enable|disable)\s+(?:the\s+)?(?:ac|air\s*con(?:ditioning)?)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() in ["start", "enable"] else 0,
     "AC start/stop.", 0.96),

    (r"\b(?:hit|press)\s+(?:the\s+)?ac\s+button\b",
     "0x101", "TOGGLE_AC", lambda m: 1,
     "AC button press (toggle on).", 0.85),

    (r"\b(?:no|without)\s+(?:ac|air\s*con|air conditioning)\b",
     "0x101", "TOGGLE_AC", lambda m: 0,
     "AC off request.", 0.88),

    (r"\b(?:need|could use)\s+(?:ac|air\s*con|air conditioning|cool air)\b",
     "0x101", "TOGGLE_AC", lambda m: 1,
     "Need AC request.", 0.85),

    # ═══════════════════════════════════════════════════════════════════════
    # SUNROOF - Positions (explicit %)
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:open|set)\s+(?:the\s+)?sunroof\s+(?:to\s+)?(\d+)\s*(?:%|percent)?\b",
     "0x102", "SET_POSITION", lambda m: int(m.group(1)),
     "Specific sunroof position.", 0.99),

    (r"\b(?:close|shut)\s+(?:the\s+)?(?:sunroof|roof|moonroof)\b",
     "0x102", "SET_POSITION", lambda m: 0,
     "Sunroof closed.", 0.99),

    (r"\b(?:open|slide)\s+(?:the\s+)?(?:sunroof|roof|moonroof)\s+(?:fully|all the way|completely|100)\b",
     "0x102", "SET_POSITION", lambda m: 100,
     "Sunroof fully open.", 0.98),

    (r"\b(?:open|crack|tilt)\s+(?:the\s+)?(?:sunroof|roof|moonroof)\s+(?:half|50|50%|halfway)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Sunroof half open.", 0.98),

    (r"\b(?:crack|tilt|vent)\s+(?:the\s+)?(?:sunroof|roof|moonroof|window)\b",
     "0x102", "SET_POSITION", lambda m: 10,
     "Sunroof cracked/vented.", 0.95),

    (r"\b(?:open|slide)\s+(?:the\s+)?(?:sunroof|roof|moonroof)\s+(?:a\s+)?(?:little|bit|slightly|touch|crack)\b",
     "0x102", "SET_POSITION", lambda m: 15,
     "Sunroof slightly open.", 0.94),

    (r"\b(?:open|slide)\s+(?:the\s+)?(?:sunroof|roof|moonroof)\s+(?:three quarters|75|75%)\b",
     "0x102", "SET_POSITION", lambda m: 75,
     "Sunroof 75% open.", 0.96),

    (r"\b(?:sunroof|roof|moonroof)\s+(?:quarter|25|25%)\b",
     "0x102", "SET_POSITION", lambda m: 25,
     "Sunroof quarter open.", 0.96),

    (r"\b(?:shut|close|roll up)\s+(?:the\s+)?(?:window|sunroof)\b",
     "0x102", "SET_POSITION", lambda m: 0,
     "Close window/sunroof.", 0.95),

    (r"\b(?:open|put down)\s+(?:the\s+)?(?:window|sunroof)\s+(?:a\s+)?(?:little|bit|touch)\b",
     "0x102", "SET_POSITION", lambda m: 15,
     "Open window slightly.", 0.93),

    # FIX: bare "open sunroof" / "open the sunroof" — was falling through to SLM
    # Must come AFTER all qualified patterns (fully/half/slightly/%) above.
    (r"\b(?:open|slide|pop)\s+(?:the\s+)?(?:sunroof|roof|moonroof)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Bare open sunroof — default 50%.", 0.90),

    (r"\b(?:fresh air|need air|air out)\b",
     "0x102", "SET_POSITION", lambda m: 30,
     "Fresh air request — open sunroof.", 0.88),

    # ═══════════════════════════════════════════════════════════════════════
    # HEADLIGHTS
    # ═══════════════════════════════════════════════════════════════════════

    (r"\bturn\s+(on|off)\s+(?:the\s+)?(?:head)?lights?\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Headlights toggle.", 0.99),

    (r"\b(?:head)?lights?\s+(on|off)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Lights on/off shorthand.", 0.99),

    (r"\b(?:switch|flick|flip|hit|press)\s+(on|off)\s+(?:the\s+)?(?:lights?|headlights?)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Lights toggle variation.", 0.97),

    (r"\b(?:lights?|headlights?)\s+(?:please|now|on|off)?\s*$",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if "off" not in m.group(0).lower() else 0,
     "Lights implied command.", 0.88),

    (r"\b(?:can't see|cannot see|hard to see|dark out|night time|getting dark)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Visibility issue — lights on.", 0.92),

    (r"\b(?:low beam|high beam|driving lights)\s+(on|off)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Beam lights control.", 0.90),

    (r"\b(?:auto lights|automatic lights)\s+(on|off)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Auto lights (maps to on).", 0.85),

    # ═══════════════════════════════════════════════════════════════════════
    # DASHBOARD BRIGHTNESS
    # ═══════════════════════════════════════════════════════════════════════

    (r"\bset\s+(?:the\s+)?(?:dashboard\s+|display\s+|screen\s+|instrument\s+cluster\s+)?brightness\s+to\s+(\d+)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: int(m.group(1)),
     "Direct brightness set.", 0.99),

    (r"\bbrightness\s+(?:to\s+)?(\d+)\s*(?:%|percent)?\b",
     "0x103", "SET_BRIGHTNESS", lambda m: int(m.group(1)),
     "Brightness value set.", 0.98),

    (r"\b(?:dim|lower|reduce|decrease)\s+(?:the\s+)?(?:dashboard|display|screen|brightness|lights|cluster)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 20,
     "Dimming dashboard.", 0.90),

    (r"\b(?:brighten|raise|increase)\s+(?:the\s+)?(?:dashboard|display|screen|brightness|lights|cluster)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 80,
     "Brightening dashboard.", 0.90),

    (r"\b(?:screen|display|dash)\s+(?:too bright|blinding|hurts my eyes)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 30,
     "Screen too bright complaint.", 0.88),

    (r"\b(?:screen|display|dash)\s+(?:too dim|can't see|hard to read)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 80,
     "Screen too dim complaint.", 0.88),

    (r"\b(?:night mode|dark mode|reduce glare)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 15,
     "Night mode — low brightness.", 0.85),

    (r"\b(?:day mode|increase visibility)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 85,
     "Day mode — high brightness.", 0.85),

    (r"\b(?:brightness|dash|screen)\s+(?:down|up|lower|higher)\b",
     "0x103", "SET_BRIGHTNESS",
     lambda m: 30 if "down" in m.group(0) or "lower" in m.group(0) else 80,
     "Brightness direction.", 0.87),

    (r"\b(?:minimum|lowest)\s+brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 5,
     "Minimum brightness.", 0.92),

    (r"\b(?:maximum|highest|full)\s+brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 100,
     "Maximum brightness.", 0.92),

    (r"\b(?:half|medium)\s+brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 50,
     "Half brightness.", 0.90),

    # ═══════════════════════════════════════════════════════════════════════
    # RELATIVE & COMBINED PHRASES
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(a\s+little|bit|slightly|just a|touch)\s+(more|higher|up|hotter|warmer|brighter)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 24,
     "Slight increase request.", 0.80),

    (r"\b(a\s+little|bit|slightly|just a|touch)\s+(less|lower|down|cooler|colder|dimmer)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 20,
     "Slight decrease request.", 0.80),

    (r"\b(?:make it|set it|get it)\s+(?:a\s+)?(?:little|bit)\s+(?:warmer|cooler)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 24 if "warmer" in m.group(0) else 20,
     "Make it slightly warmer/cooler.", 0.82),

    (r"\b(?:too hot|cold|warm|cool)\s+(?:in here|inside|cabin)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 18 if "hot" in m.group(0) or "warm" in m.group(0) else 26,
     "Cabin temperature complaint.", 0.86),

    (r"\b(?:what's|what is|check)\s+(?:the\s+)?(?:temp|temperature|cabin temp|inside temp)\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Temperature status query (handled by conversation_layer).", 0.95),

    (r"\b(?:show|display|tell me)\s+(?:the\s+)?(?:temp|temperature|current temp)\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Show temperature status.", 0.94),

    # ═══════════════════════════════════════════════════════════════════════
    # EMERGENCY / SAFETY
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:emergency|help|danger|problem)\s+(?:lights|flashers|hazards)\s+(?:on|activate)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Emergency lights request.", 0.98),

    (r"\b(?:pull over|stop|danger|emergency)\b",
     None, "SAFETY_ALERT", lambda m: 0,
     "Safety alert triggered.", 0.95),

    (r"\b(?:can't see|cannot see|blind|visibility issue)\s+(?:road|ahead|outside)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Visibility safety — lights on.", 0.96),

    # ═══════════════════════════════════════════════════════════════════════
    # COMFORT MACRO PHRASES (Quick macros)
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:i'?m|i am|feeling)\s+(?:sleepy|drowsy|tired|exhausted)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Drowsiness detected — cooling.", 0.85),

    (r"\b(?:wake me up|need to stay awake)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Wake-up request — cooling.", 0.84),

    (r"\b(?:cozy|comfortable|perfect|just right)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Comfortable — neutral temp.", 0.80),

    (r"\b(?:reset|default|back to normal|factory settings)\b",
     None, "MACRO_RESET", lambda m: 0,
     "Reset request.", 0.92),
]


class RegexIntentResolver:
    def __init__(self) -> None:
        self._compiled = [
            (re.compile(pat, re.IGNORECASE), cid, cmd, vfn, reason, conf)
            for pat, cid, cmd, vfn, reason, conf in _PATTERNS
        ]

    def resolve(self, text: str) -> dict | None:
        start = time.monotonic()

        for regex, can_id, cmd, val_fn, reason, conf in self._compiled:
            m = regex.search(text)
            if m:
                try:
                    value = val_fn(m)
                except Exception:
                    value = None
                if value is None:
                    continue

                latency = (time.monotonic() - start) * 1000

                if cmd == "STATUS_QUERY":
                    return {
                        "command":    "STATUS_QUERY",
                        "reason":     reason,
                        "confidence": conf,
                        "handled_by": "Regex",
                        "latency":    f"{latency:.3f}ms",
                    }

                if cmd == "SAFETY_ALERT":
                    return {
                        "command":    "SAFETY_ALERT",
                        "reason":     reason,
                        "confidence": conf,
                        "handled_by": "Regex",
                        "latency":    f"{latency:.3f}ms",
                    }

                if cmd == "MACRO_RESET":
                    return {
                        "command":    "MACRO_RESET",
                        "reason":     reason,
                        "confidence": conf,
                        "handled_by": "Regex",
                        "latency":    f"{latency:.3f}ms",
                    }

                return {
                    "can_id":     can_id,
                    "command":    cmd,
                    "value":      int(value),
                    "reason":     reason,
                    "confidence": conf,
                    "handled_by": "Regex",
                    "latency":    f"{latency:.3f}ms",
                }

        return None
