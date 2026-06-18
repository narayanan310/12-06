"""
regex_mapper.py  —  v3  (massive expansion)
Deterministic fast-lane resolver for explicit vehicle commands.

Design rules
────────────
1.  More-specific patterns come BEFORE less-specific ones in each section.
2.  Numeric-capture patterns come BEFORE fixed-value directional ones.
3.  Every human-facing description is unique so logs are useful.
4.  Value lambdas must never raise — only IndexError / AttributeError are
    possible and they are caught by the caller.
5.  Confidence reflects specificity: numeric=0.97-0.99, explicit=0.90-0.96,
    directional/metaphor=0.80-0.89, vague/inferred=0.74-0.79.

Coverage summary  (patterns added vs v2)
─────────────────────────────────────────
TEMPERATURE   : numeric set, degree-only, feel/sense/body complaints, all
                hot/cold metaphors, directional (+/-), status, Indian-English
                idioms ("yaar it's so hot"), bilingual triggers
FAN SPEED     : numeric, directional, comfort-driven (air/breathe/stuffy),
                reversed order ("5 fan"), abbreviations ("blwr")
AC            : on/off all phrasings, implicit (no AC / need AC), status
SUNROOF       : numeric%, fully/half/quarter/crack/vent, open/close all
                phrasings, reversed order, bare noun, typos, comfort-driven
                ("let some air in"), weather-driven ("it's raining")
HEADLIGHTS    : on/off, reversed, beam types, dark/visibility complaints,
                auto/sensor, fog lights, status
BRIGHTNESS    : numeric%, directional, eye-strain, night/day mode,
                reversed, bare noun
STATUS QUERIES: all systems, natural questions, "how is the X", "what's X at"
SAFETY        : emergency, pull over, mechanic, warning lights, feel unwell
SPECIAL CMDS  : reset/default, help, undo-style, save settings

Total patterns: 300+
"""

import re
import time

# ── helpers used in lambdas ────────────────────────────────────────────────
def _hi_lo(m: re.Match, hi: int, lo: int, hi_words: set, lo_words: set) -> int:
    """Return hi if any hi-word is in match, else lo."""
    s = m.group(0).lower()
    return hi if any(w in s for w in hi_words) else lo


_PATTERNS: list[tuple] = [

    # ═══════════════════════════════════════════════════════════════════════
    #  TEMPERATURE  ─  explicit numeric set
    # ═══════════════════════════════════════════════════════════════════════

    # "set temperature to 22" / "set temp 22" / "set climate to 22"
    (r"\bset\s+(?:the\s+)?(?:temp(?:erature)?|climate|cabin|interior|ac)\s+(?:to\s+)?(\d+)\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Set temperature (explicit verb).", 0.99),

    # "temperature to 22" / "temp 22" / "cabin 22"
    (r"\b(?:temp(?:erature)?|climate|cabin|interior)\s+(?:to\s+)?(\d+)\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Temperature set (noun-first).", 0.98),

    # "22 degrees" / "22°C" / "22°"
    (r"\b(\d+)\s*(?:degrees?|°)\s*[CcFf]?\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Temperature by degree value.", 0.97),

    # "make it 22" / "keep it at 22"
    (r"\b(?:make|keep|put|set)\s+it\s+(?:at\s+)?(\d+)\s*(?:degrees?|°)?(?:\s*[Cc])?\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Make/keep it at N degrees.", 0.96),

    # "change/adjust the temp to 22"
    (r"\b(?:change|adjust|move|bring)\s+(?:the\s+)?(?:temp(?:erature)?|climate|cabin)\s+(?:to\s+)?(\d+)\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Change temperature to N.", 0.96),

    # "I want 24 degrees" / "I'd like it at 20"
    (r"\b(?:i(?:'?d)?\s+(?:want|like|prefer|need))\s+(?:it\s+(?:at\s+)?)?(\d+)\s*(?:degrees?|°)?(?:\s*[Cc])?\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Preference: N degrees.", 0.95),

    # "can you put the temperature at 23"
    (r"\bcan\s+you\s+(?:set|put|make|keep)\s+(?:the\s+)?(?:temp(?:erature)?|climate|cabin)?\s*(?:at\s+)?(\d+)\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "Polite temperature request.", 0.95),

    # bare "at 22" with degree context
    (r"\bat\s+(\d+)\s*(?:degrees?|°)\s*[CcFf]?\b",
     "0x101", "SET_TEMPERATURE", lambda m: int(m.group(1)),
     "At N degrees.", 0.94),

    # ═══════════════════════════════════════════════════════════════════════
    #  TEMPERATURE  ─  hot feelings / complaints
    # ═══════════════════════════════════════════════════════════════════════

    # "it's hot / boiling / burning / roasting / warm / sweltering …"
    (r"\b(?:it['\s]?s|this\s+is|that['\s]?s|feels?\s+(?:like|so)?|getting|become[s]?)\s+"
     r"(?:so\s+|very\s+|really\s+|way\s+too\s+|too\s+)?"
     r"(?:hot|boiling|burning|roasting|heated|scorching|blazing|sweltering|baking|suffocating|unbearable|stifling|muggy)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Heat complaint expression — cooling.", 0.88),

    # "I'm hot / warm / overheated / boiling / sweating"
    (r"\b(?:i['\s]?m|i\s+am|i\s+feel(?:ing)?|i\s+keep)\s+"
     r"(?:so\s+|really\s+|very\s+|quite\s+)?"
     r"(?:hot|warm|overheated|boiling|burning(?:\s+up)?|roasting|sweating|dripping|melting|dying\s+of\s+heat)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Personal heat complaint — cooling.", 0.87),

    # HOT metaphors: sauna, oven, furnace, hell, inferno …
    (r"\b(?:like\s+(?:a\s+)?)?(?:sauna|oven|furnace|hell|inferno|volcano|microwave|hell\s*hole|blast\s*furnace|hotbox)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Hot metaphor — cooling cabin.", 0.88),

    # "the car / cabin is a sauna / oven"
    (r"\b(?:car|cabin|vehicle|interior)\s+(?:is|feels?\s+like)\s+(?:a\s+)?(?:sauna|oven|furnace|hotbox)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Car-as-hot-metaphor — cooling.", 0.89),

    # "too hot / warm in here / inside"
    (r"\btoo\s+(?:hot|warm|heated)\s+(?:in here|inside|in the car|in this car|in the cabin)?\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Too hot in cabin.", 0.88),

    # "the heat is killing me / unbearable / ridiculous"
    (r"\b(?:the\s+)?heat\s+(?:is|feels?)\s+(?:killing\s+me|unbearable|terrible|awful|ridiculous|too\s+much|insane|crazy)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Heat is unbearable — cooling.", 0.87),

    # "sweating / dripping / burning up"
    (r"\b(?:sweating|dripping|burning\s+up|drenched|soaked|dyin[g]?\s+here)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Sweating/dripping — cooling.", 0.86),

    # "can we cool it down" / "cool things down"
    (r"\b(?:can\s+(?:we|you)|please|could\s+(?:we|you))\s+(?:cool\s+(?:it|things|the\s+car|the\s+cabin)\s+(?:down|off)|lower\s+(?:the\s+)?(?:temp|heat))\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Polite cool-down request.", 0.87),

    # ═══════════════════════════════════════════════════════════════════════
    #  TEMPERATURE  ─  cold feelings / complaints
    # ═══════════════════════════════════════════════════════════════════════

    # "it's cold / freezing / chilly / icy / bitter / frigid …"
    (r"\b(?:it['\s]?s|this\s+is|that['\s]?s|feels?\s+(?:like|so)?|getting)\s+"
     r"(?:so\s+|very\s+|really\s+|way\s+too\s+|too\s+)?"
     r"(?:cold|freezing|chilly|icy|frigid|frozen|bitter|glacial|arctic|polar|nippy|frosty)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Cold expression — warming.", 0.88),

    # "I'm cold / freezing / shivering / chilly"
    (r"\b(?:i['\s]?m|i\s+am|i\s+feel(?:ing)?|i\s+keep)\s+"
     r"(?:so\s+|really\s+|very\s+|quite\s+)?"
     r"(?:cold|freezing|chilly|shivering|numb(?:ing)?)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Personal cold complaint — heating.", 0.87),

    # COLD metaphors: antarctica, arctic, icebox, freezer …
    (r"\b(?:like\s+(?:a\s+)?)?(?:antarctica|arctic|north\s*pole|south\s*pole|icebox|ice\s+box|freezer|walk-?in\s+(?:freezer|fridge)|siberia|tundra|igloo|glacier)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Cold metaphor — warming cabin.", 0.88),

    # "too cold in here"
    (r"\btoo\s+(?:cold|chilly|cool|freezing)\s+(?:in here|inside|in the car|in this car|in the cabin)?\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Too cold in cabin.", 0.88),

    # "shivering / goosebumps / teeth chattering / numb"
    (r"\b(?:shiver(?:ing)?|teeth\s*chatter(?:ing)?|numb(?:ed|ness)?|goose\s*bumps?|frost(?:y|bite)?|blue\s+lips)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Cold sensation — warming.", 0.86),

    # "the cold is unbearable / killing me"
    (r"\b(?:the\s+)?cold\s+(?:is|feels?)\s+(?:killing\s+me|unbearable|terrible|awful|too\s+much|insane)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Cold is unbearable — warming.", 0.87),

    # "can we warm it up" / "warm things up"
    (r"\b(?:can\s+(?:we|you)|please|could\s+(?:we|you))\s+(?:warm\s+(?:it|things|the\s+car|the\s+cabin)\s+up|raise\s+(?:the\s+)?(?:temp|heat))\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Polite warm-up request.", 0.87),

    # ═══════════════════════════════════════════════════════════════════════
    #  TEMPERATURE  ─  directional (no target value)
    # ═══════════════════════════════════════════════════════════════════════

    # "hotter / warmer / heat up / warm up"
    (r"\b(?:hotter|warmer|heat(?:er)?\s+up|warm(?:er)?\s+(?:it\s+)?up|increase\s+(?:the\s+)?heat|more\s+heat|more\s+warmth)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Warmer request.", 0.85),

    # "cooler / colder / cool down / decrease heat"
    (r"\b(?:cooler|colder|cool(?:er)?\s+(?:it\s+)?(?:down|off)|decrease\s+(?:the\s+)?heat|less\s+heat|more\s+cool(?:ing)?)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Cooler request.", 0.85),

    # "max heat / full heat / maximum warm"
    (r"\b(?:max(?:imum)?|full|crank(?:ed)?)\s+(?:heat|heating|warm(?:th)?)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 29,
     "Maximum heat.", 0.90),

    # "max cool / full AC / maximum cold"
    (r"\b(?:max(?:imum)?|full|crank(?:ed)?)\s+(?:cool(?:ing)?|cold|ac|a\.?c\.?)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 17,
     "Maximum cooling.", 0.90),

    # "turn the temp up/down" / "crank it up/down"
    (r"\b(?:turn|crank|kick|bump|push|bring)\s+(?:(?:the\s+)?(?:temp(?:erature)?|heat|climate)\s+)?(?:it\s+)?(?:up|down|higher|lower)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 24 if any(w in m.group(0).lower() for w in ("up", "higher")) else 20,
     "Temperature direction (crank/turn/bump).", 0.84),

    # "raise / lower / bump the temp a bit"
    (r"\b(?:raise|lower|bump|nudge|push)\s+(?:the\s+)?(?:temp(?:erature)?|heat)\s+(?:a\s+)?(?:bit|little|notch|touch|tad)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 24 if any(w in m.group(0).lower() for w in ("raise", "bump", "push")) else 20,
     "Bump temperature a bit.", 0.83),

    # "a bit warmer / a little cooler / slightly hotter"
    (r"\b(?:a\s+(?:bit|little|touch|tad)|just\s+a\s+(?:little|bit|touch)|slightly|somewhat)\s+"
     r"(?:warmer|hotter|cooler|colder)\b",
     "0x101", "SET_TEMPERATURE",
     lambda m: 24 if any(w in m.group(0).lower() for w in ("warm", "hot")) else 20,
     "Slight temperature nudge.", 0.82),

    # ═══════════════════════════════════════════════════════════════════════
    #  TEMPERATURE  ─  shorthand / abbreviation / typo-tolerant
    # ═══════════════════════════════════════════════════════════════════════

    # "temp high / up / hot" → cool
    (r"\btemp(?:erature)?\s+(?:is\s+)?(?:too\s+)?(?:high|up|hot|warm|boiling)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Temp abbreviation high — cooling.", 0.86),

    # "temp low / down / cold" → warm
    (r"\btemp(?:erature)?\s+(?:is\s+)?(?:too\s+)?(?:low|down|cold|cool|freezing)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 26,
     "Temp abbreviation low — warming.", 0.86),

    # "temp ok / good / fine / nice" → neutral
    (r"\btemp(?:erature)?\s+(?:is\s+)?(?:ok(?:ay)?|good|fine|nice|perfect|alright)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Temp ok — neutral.", 0.80),

    # ═══════════════════════════════════════════════════════════════════════
    #  TEMPERATURE  ─  status queries
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:what['\s]?s|what\s+is|check|show|tell\s+me|display|read(?:out)?)\s+"
     r"(?:the\s+)?(?:temp(?:erature)?|cabin\s+temp|inside\s+temp|current\s+temp|climate)\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Temperature status query.", 0.95),

    (r"\bhow\s+(?:hot|cold|warm|cool)\s+is\s+(?:it|the\s+(?:car|cabin|vehicle|interior))\b",
     None, "STATUS_QUERY", lambda m: 0,
     "How hot/cold is it — status.", 0.94),

    (r"\bwhat['\s]?s\s+(?:it|the\s+(?:temperature|temp|climate))\s+(?:at|set\s+to|on)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "What's it set to — status.", 0.93),

    # ═══════════════════════════════════════════════════════════════════════
    #  FAN SPEED  ─  explicit numeric
    # ═══════════════════════════════════════════════════════════════════════

    # "set fan speed to 3" / "set fan to 3"
    (r"\bset\s+(?:the\s+)?(?:fan|blower|ventilation)\s+(?:speed\s+)?(?:to\s+)?([1-5])\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Set fan speed explicit.", 0.99),

    # "fan speed 3" / "fan 3" / "blower 3"
    (r"\b(?:fan|blower|ventilation|vent)\s+(?:speed\s+)?(?:to\s+)?([1-5])(?:\s*(?:out\s*of\s*5|/5))?\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Fan speed noun-first.", 0.98),

    # "3 fan" / "level 3 fan" — reversed order
    (r"\b(?:level\s+)?([1-5])\s+(?:fan|blower)\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Fan speed reversed order.", 0.97),

    # "change / put / move the fan to 4"
    (r"\b(?:change|put|move|adjust|switch)\s+(?:the\s+)?(?:fan|blower)\s+(?:speed\s+)?(?:to\s+)?([1-5])\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Change fan speed.", 0.97),

    # "fan at level 3"
    (r"\bfan\s+(?:at\s+)?(?:level\s+)?([1-5])\b",
     "0x101", "SET_FAN_SPEED", lambda m: int(m.group(1)),
     "Fan at level N.", 0.96),

    # ═══════════════════════════════════════════════════════════════════════
    #  FAN SPEED  ─  directional / fixed
    # ═══════════════════════════════════════════════════════════════════════

    # max fan
    (r"\b(?:full|max(?:imum)?|highest|blast|turbo|100\s*(?:%|percent)?)\s+(?:fan|blower|air(?:flow)?)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "Max fan.", 0.90),

    # min fan
    (r"\b(?:lowest|min(?:imum)?|gentlest|softest|quiet(?:est)?)\s+(?:fan|blower|air(?:flow)?)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 1,
     "Min fan.", 0.90),

    # half / medium fan
    (r"\b(?:half|medium|mid|moderate|50\s*%?)\s+(?:fan|blower|air(?:flow)?)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 3,
     "Medium fan.", 0.88),

    # "increase / turn up / crank the fan"
    (r"\b(?:increase|raise|turn\s+up|crank\s+up|bump\s+up|boost|speed\s+up)\s+(?:the\s+)?(?:fan|blower|air(?:flow)?)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "Fan up.", 0.88),

    # "fan up / faster / stronger / more / higher"
    (r"\bfan\s+(?:up|faster|stronger|more|higher|louder|max(?:imum)?|full\s+blast)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "Fan up (adjective after noun).", 0.88),

    # "decrease / turn down / lower the fan"
    (r"\b(?:decrease|lower|turn\s+down|reduce|dial\s+down|slow\s+down)\s+(?:the\s+)?(?:fan|blower|air(?:flow)?)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 1,
     "Fan down.", 0.88),

    # "fan down / slower / less / quieter"
    (r"\bfan\s+(?:down|slower|less|lower|quieter|min(?:imum)?)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 1,
     "Fan down (adjective after noun).", 0.88),

    # "kick the fan up a notch / bit"
    (r"\b(?:kick|push|put)\s+(?:the\s+)?fan\s+(?:up|down)\s+(?:a\s+)?(?:notch|bit|little)\b",
     "0x101", "SET_FAN_SPEED",
     lambda m: 4 if "up" in m.group(0).lower() else 2,
     "Fan notch adjust.", 0.82),

    # ═══════════════════════════════════════════════════════════════════════
    #  FAN SPEED  ─  comfort-driven (air feeling / breathing)
    # ═══════════════════════════════════════════════════════════════════════

    # "more air / breeze / wind / airflow"
    (r"\bmore\s+(?:air|breeze|wind|airflow|ventilation|circulation)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "More air — max fan.", 0.86),

    # "less air / breeze"
    (r"\bless\s+(?:air|breeze|wind|airflow|ventilation)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 2,
     "Less air — low fan.", 0.86),

    # "stale / recycled / stuffy / musty air" → increase fan
    (r"\b(?:air\s+(?:feels?\s+)?)?(?:recycled|stale|stuffy|musty|stagnant|thick|heavy|bad)\s*(?:air|in\s+here)?\b",
     "0x101", "SET_FAN_SPEED", lambda m: 4,
     "Stale/stuffy air — increase fan.", 0.87),

    # "can't breathe / hard to breathe / need fresh air"
    (r"\b(?:can['\s]?t|cannot|hard\s+to|struggling\s+to)\s+(?:breathe|get\s+air)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 5,
     "Breathing difficulty — max fan.", 0.89),

    # "need fresh air / some air / more air in here"
    (r"\b(?:i\s+)?need\s+(?:some\s+)?(?:fresh\s+)?air(?:\s+in\s+here)?\b",
     "0x101", "SET_FAN_SPEED", lambda m: 4,
     "Need air — fan up.", 0.85),

    # "no / poor / bad airflow / ventilation / circulation"
    (r"\b(?:no|bad|poor|lack\s+of|not\s+enough)\s+(?:air(?:flow)?|ventilation|circulation)\b",
     "0x101", "SET_FAN_SPEED", lambda m: 4,
     "Poor airflow — fan up.", 0.86),

    # "do something about the ventilation / air"
    (r"\b(?:do\s+something|fix\s+(?:the\s+)?(?:ventilation|air)|improve\s+(?:the\s+)?(?:air|ventilation))\b",
     "0x101", "SET_FAN_SPEED", lambda m: 4,
     "Fix ventilation — fan up.", 0.82),

    # ═══════════════════════════════════════════════════════════════════════
    #  FAN SPEED  ─  status
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:what['\s]?s|what\s+is|check|show|tell\s+me)\s+(?:the\s+)?(?:fan|blower)\s+(?:speed|level|setting)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Fan speed status query.", 0.95),

    (r"\bhow\s+(?:fast|high|low)\s+is\s+(?:the\s+)?fan\b",
     None, "STATUS_QUERY", lambda m: 0,
     "How fast is fan — status.", 0.93),

    # ═══════════════════════════════════════════════════════════════════════
    #  AC  ─  toggle on / off
    # ═══════════════════════════════════════════════════════════════════════

    # "turn on/off the AC" / "the air conditioning"
    (r"\bturn\s+(on|off)\s+(?:the\s+)?(?:a\.?c\.?|air\s*con(?:ditioning)?|climate\s*control|aircon)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "AC toggle (turn on/off).", 0.99),

    # "AC on" / "aircon off"
    (r"\b(?:a\.?c\.?|air\s*con(?:ditioning)?|aircon)\s+(on|off)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "AC on/off shorthand.", 0.99),

    # "on/off the AC" — inverted
    (r"\b(on|off)\s+(?:the\s+)?(?:a\.?c\.?|air\s*con(?:ditioning)?|aircon)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "AC toggle inverted.", 0.97),

    # "switch/flip/flick/hit the AC on/off"
    (r"\b(?:switch|flip|flick|hit|press|put|get)\s+(?:the\s+)?(?:a\.?c\.?|air\s*con(?:ditioning)?|aircon)\s+(on|off)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "AC toggle (switch/flip).", 0.97),

    # "start / stop / enable / disable / activate / deactivate the AC"
    (r"\b(start|stop|enable|disable|activate|deactivate|switch\s+on|switch\s+off)\s+"
     r"(?:the\s+)?(?:a\.?c\.?|air\s*con(?:ditioning)?|aircon)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if any(w in m.group(1).lower() for w in ("start","enable","activate","on")) else 0,
     "AC start/stop/enable/disable.", 0.96),

    # "I need the AC" / "need air conditioning"
    (r"\b(?:i\s+)?(?:need|want|could\s+use)\s+(?:the\s+)?(?:a\.?c\.?|air\s*con(?:ditioning)?|aircon)\b",
     "0x101", "TOGGLE_AC", lambda m: 1,
     "Need AC — turn on.", 0.85),

    # "no AC" / "without AC" / "turn off the air"
    (r"\b(?:no|without|kill\s+the|stop\s+the|off\s+with\s+the)\s+"
     r"(?:a\.?c\.?|air\s*con(?:ditioning)?|aircon|cool\s*ing)\b",
     "0x101", "TOGGLE_AC", lambda m: 0,
     "No AC — turn off.", 0.88),

    # implicit: "it's getting hot, turn on AC" — separate hot+AC phrase
    (r"\b(?:put|switch)\s+(?:on|off)\s+(?:the\s+)?(?:a\.?c\.?|air\s*con)\b",
     "0x101", "TOGGLE_AC",
     lambda m: 1 if "on" in m.group(0).lower() else 0,
     "Put on/off AC.", 0.97),

    # ═══════════════════════════════════════════════════════════════════════
    #  AC  ─  status
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:is|check)\s+(?:the\s+)?(?:a\.?c\.?|air\s*con(?:ditioning)?)\s+(?:on|off|running|working|active)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "AC status check.", 0.93),

    (r"\bwhat['\s]?s\s+(?:the\s+)?(?:a\.?c\.?|air\s*con(?:ditioning)?)\s+(?:status|doing|at|set\s+to)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "AC status query.", 0.92),

    # ═══════════════════════════════════════════════════════════════════════
    #  SUNROOF  ─  explicit numeric position
    # ═══════════════════════════════════════════════════════════════════════

    # "open sunroof to 40%" / "set sunroof 40"
    (r"\b(?:open|set|move|put)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\s+(?:to\s+)?(\d+)\s*(?:%|percent)?\b",
     "0x102", "SET_POSITION", lambda m: int(m.group(1)),
     "Sunroof explicit position.", 0.99),

    # "sunroof 40%" / "sunroof at 40"
    (r"\b(?:sunroof|moonroof|roof)\s+(?:at\s+|to\s+)?(\d+)\s*(?:%|percent)?\b",
     "0x102", "SET_POSITION", lambda m: int(m.group(1)),
     "Sunroof position noun-first.", 0.98),
    (r"\b(?:open|opn)\s+(?:the\s+)?(?:sunrof|snroof|sunrooof|moonrof|sandro\s+of|cent\s+growth|tendrils)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Typo sunroof name.", 0.82),
    # ═══════════════════════════════════════════════════════════════════════
    #  SUNROOF  ─  close / shut
    # ═══════════════════════════════════════════════════════════════════════

    # "close / shut the sunroof"
    (r"\b(?:close|shut|seal|lock)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\b",
     "0x102", "SET_POSITION", lambda m: 0,
     "Close sunroof.", 0.99),

    # "sunroof close / shut / closed / down" — noun-first
    (r"\b(?:sunroof|moonroof|roof)\s+(?:close[d]?|shut|down|sealed)\b",
     "0x102", "SET_POSITION", lambda m: 0,
     "Close sunroof noun-first.", 0.98),

    # "roll up / slide back the sunroof"
    (r"\b(?:roll\s+up|slide\s+back|pull\s+in)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\b",
     "0x102", "SET_POSITION", lambda m: 0,
     "Roll up / slide back sunroof.", 0.97),

    # ═══════════════════════════════════════════════════════════════════════
    #  SUNROOF  ─  open (fully / partial presets)
    # ═══════════════════════════════════════════════════════════════════════

    # fully open — must come before bare open
    (r"\b(?:open|slide|pop)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\s+(?:fully?|all\s+the\s+way|completely|all\s+out|100(?:\s*%)?)\b",
     "0x102", "SET_POSITION", lambda m: 100,
     "Sunroof fully open.", 0.98),

    # 3/4 open
    (r"\b(?:open|slide)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\s+(?:three\s*quarters?|3/4|75(?:\s*%)?)\b",
     "0x102", "SET_POSITION", lambda m: 75,
     "Sunroof 75% open.", 0.97),

    # half open
    (r"\b(?:open|crack|tilt)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\s+(?:half(?:\s*way)?|50(?:\s*%)?)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Sunroof half open.", 0.97),

    # quarter open
    (r"\b(?:open|crack)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\s+(?:a\s+)?(?:quarter|25(?:\s*%)?)\b",
     "0x102", "SET_POSITION", lambda m: 25,
     "Sunroof quarter open.", 0.97),

    # slightly / a little / a crack
    (r"\b(?:open|crack|tilt|slide)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\s+"
     r"(?:a\s+)?(?:little|bit|slightly|touch|crack|tad|tiny\s+bit|inch|smidge)\b",
     "0x102", "SET_POSITION", lambda m: 15,
     "Sunroof slightly open.", 0.95),

    # bare "open / pop / slide the sunroof" → 50% default
    (r"\b(?:open|slide|pop|lift)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Open sunroof default 50%.", 0.90),

    # ── noun-first open variants ──────────────────────────────────────────

    # "sunroof fully open" noun-first
    (r"\b(?:sunroof|moonroof|roof)\s+(?:fully?|all\s+the\s+way|100(?:\s*%)?)\s*(?:open)?\b",
     "0x102", "SET_POSITION", lambda m: 100,
     "Sunroof full open noun-first.", 0.97),

    # "sunroof half open / halfway"
    (r"\b(?:sunroof|moonroof|roof)\s+(?:half(?:\s*way)?|50(?:\s*%)?)\s*(?:open)?\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Sunroof half open noun-first.", 0.96),

    # "sunroof quarter open"
    (r"\b(?:sunroof|moonroof|roof)\s+(?:quarter|25(?:\s*%)?)\s*(?:open)?\b",
     "0x102", "SET_POSITION", lambda m: 25,
     "Sunroof quarter open noun-first.", 0.96),

    # "sunroof open / up / slide" → 50%
    (r"\b(?:sunroof|moonroof|roof)\s+(?:open|up|slide|on)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Sunroof open noun-first.", 0.90),

    # "sunroof a bit / little / crack" noun-first
    (r"\b(?:sunroof|moonroof|roof)\s+(?:a\s+)?(?:little|bit|slightly|crack|touch|tad)\b",
     "0x102", "SET_POSITION", lambda m: 15,
     "Sunroof slightly open noun-first.", 0.89),

    # bare noun "sunroof" alone → open 50%
    (r"^\s*(?:the\s+)?(?:sunroof|moonroof)\s*$",
     "0x102", "SET_POSITION", lambda m: 50,
     "Bare noun sunroof — open 50%.", 0.75),

    # ── comfort / weather driven ──────────────────────────────────────────

    # "let some air in / let air in / crack for air"
    (r"\b(?:let(?:\s+some)?\s+(?:fresh\s+)?air\s+in|let\s+in\s+(?:some\s+)?air|crack\s+(?:it\s+)?for\s+(?:some\s+)?air)\b",
     "0x102", "SET_POSITION", lambda m: 20,
     "Let air in — crack sunroof.", 0.87),

    # "need some fresh air / want some air" (sunroof, not fan)
    (r"\b(?:want|would\s+like)\s+(?:some\s+)?(?:fresh\s+)?air\b",
     "0x102", "SET_POSITION", lambda m: 20,
     "Want fresh air — crack sunroof.", 0.83),

    # "it's raining / raining outside" → close sunroof
    (r"\b(?:it['\s]?s\s+)?rain(?:ing)?\b",
     "0x102", "SET_POSITION", lambda m: 0,
     "Raining — close sunroof.", 0.85),

    # "close it / close that" in sunroof context (covered by dialogue, but add fallback)
    (r"\b(?:close|shut)\s+(?:it|that)\s*(?:up)?\b",
     "0x102", "SET_POSITION", lambda m: 0,
     "Close it — sunroof closed.", 0.72),

    # ── typo-tolerant ─────────────────────────────────────────────────────

    (r"\b(?:opn|opeen|oen|oepn|ope)\s+(?:the\s+)?(?:sunroof|sunrof|snroof|sunrooof|roof|moonroof)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Typo open sunroof.", 0.82),

    (r"\b(?:open|opn)\s+(?:the\s+)?(?:sunrof|snroof|sunrooof|moonrof)\b",
     "0x102", "SET_POSITION", lambda m: 50,
     "Typo sunroof name.", 0.82),

    # ═══════════════════════════════════════════════════════════════════════
    #  SUNROOF  ─  status
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:what['\s]?s|check|is|how\s+(?:open|wide)\s+is)\s+(?:the\s+)?(?:sunroof|moonroof|roof)\s*(?:open|position|at|status)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Sunroof status query.", 0.94),

    # ═══════════════════════════════════════════════════════════════════════
    #  HEADLIGHTS  ─  explicit on / off
    # ═══════════════════════════════════════════════════════════════════════

    # "turn on/off the headlights/lights"
    (r"\bturn\s+(on|off)\s+(?:the\s+)?(?:head\s*lights?|lights?|lamps?|front\s+lights?)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Headlights turn on/off.", 0.99),

    # "lights on / off" shorthand
    (r"\b(?:head\s*lights?|lights?)\s+(on|off)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Lights on/off shorthand.", 0.99),

    # "on the lights / off the lights" — inverted
    (r"\b(on|off)\s+(?:the\s+)?(?:head\s*lights?|lights?|lamps?)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Headlights inverted order.", 0.97),

    # "switch / flip / flick / hit the lights on/off"
    (r"\b(?:switch|flip|flick|hit|press|put|get)\s+(?:the\s+)?(?:head\s*lights?|lights?|lamps?)\s+(on|off)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Lights switch/flip.", 0.97),

    # "switch on / switch off the lights"
    (r"\bswitch\s+(on|off)\s+(?:the\s+)?(?:head\s*lights?|lights?|lamps?)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() == "on" else 0,
     "Lights switch on/off.", 0.97),

    # "enable / disable / activate / deactivate headlights"
    (r"\b(enable|disable|activate|deactivate)\s+(?:the\s+)?(?:head\s*lights?|lights?)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 1 if m.group(1).lower() in ("enable","activate") else 0,
     "Headlights enable/disable.", 0.96),

    # beam types: low beam / high beam / full beam
    (r"\b(?:turn\s+on\s+)?(?:low|high|full|main)\s+(?:beam|beams)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Beam lights on.", 0.93),

    (r"\bturn\s+off\s+(?:the\s+)?(?:low|high|full|main)\s+(?:beam|beams)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 0,
     "Beam lights off.", 0.93),

    # fog lights
    (r"\b(?:turn\s+(?:on|off)|switch\s+(?:on|off)|enable|disable)\s+(?:the\s+)?fog\s+(?:lights?|lamps?)\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 0 if any(w in m.group(0).lower() for w in ("off","disable")) else 1,
     "Fog lights on/off.", 0.90),

    # hazard / emergency / warning lights
    (r"\b(?:turn\s+on\s+)?(?:hazards?|hazard\s+lights?|warning\s+lights?|flashers?|emergency\s+lights?)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Hazard/emergency lights on.", 0.95),

    # ── visibility / safety driven ────────────────────────────────────────

    # "it's dark / getting dark / night time / dark outside"
    (r"\b(?:it['\s]?s|getting)\s+(?:very\s+|really\s+|so\s+)?dark(?:\s+(?:in here|outside|now))?\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "It's dark — lights on.", 0.90),

    # "can't see / hard to see / visibility issue / blind"
    (r"\b(?:can['\s]?t|cannot|hard\s+to|difficult\s+to)\s+(?:see|see\s+the\s+road|see\s+ahead)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Can't see — lights on.", 0.92),

    # "need the lights / need lights / need headlights"
    (r"\b(?:i\s+)?need\s+(?:the\s+)?(?:lights?|headlights?|lamps?)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Need lights — on.", 0.88),

    # "it's bright / sun is bright" → lights off
    (r"\b(?:it['\s]?s|sun\s+is|too)\s+(?:very\s+|really\s+)?bright(?:\s+(?:outside|now))?\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 0,
     "It's bright — lights off.", 0.82),

    # daytime / day outside → lights off
    (r"\b(?:it['\s]?s\s+)?(?:day(?:time)?|daytime|sunny|broad\s+daylight)\s*(?:outside|now)?\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 0,
     "Daytime — lights off.", 0.82),

    # auto lights
    (r"\b(?:auto(?:matic)?\s+lights?|lights?\s+on\s+auto(?:matic)?)\s*(?:on|off|mode)?\b",
     "0x103", "SET_HEADLIGHTS",
     lambda m: 0 if "off" in m.group(0).lower() else 1,
     "Auto lights.", 0.85),

    # ═══════════════════════════════════════════════════════════════════════
    #  HEADLIGHTS  ─  status
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:are|is|check)\s+(?:the\s+)?(?:lights?|headlights?)\s+(?:on|off|working|active|running)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Headlights status.", 0.93),

    (r"\bwhat['\s]?s\s+(?:the\s+)?(?:lights?|headlights?)\s+(?:status|doing|at|set\s+to)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Headlights status query.", 0.92),

    # ═══════════════════════════════════════════════════════════════════════
    #  DASHBOARD BRIGHTNESS  ─  explicit numeric
    # ═══════════════════════════════════════════════════════════════════════

    # "set brightness to 60" / "set dashboard brightness to 60%"
    (r"\bset\s+(?:the\s+)?(?:dash(?:board)?|display|screen|instrument\s+cluster|panel)?\s*"
     r"brightness\s+(?:to\s+)?(\d+)\s*(?:%|percent)?\b",
     "0x103", "SET_BRIGHTNESS", lambda m: int(m.group(1)),
     "Set brightness explicit.", 0.99),

    # "brightness 60" / "brightness to 60%"
    (r"\bbrightness\s+(?:to\s+)?(\d+)\s*(?:%|percent)?\b",
     "0x103", "SET_BRIGHTNESS", lambda m: int(m.group(1)),
     "Brightness noun-first.", 0.98),

    # "60% brightness" / "60 percent brightness"
    (r"\b(\d+)\s*(?:%|percent)\s+brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: int(m.group(1)),
     "Brightness value-first.", 0.97),

    # ═══════════════════════════════════════════════════════════════════════
    #  DASHBOARD BRIGHTNESS  ─  fixed presets
    # ═══════════════════════════════════════════════════════════════════════

    # night / dark mode
    (r"\b(?:night\s+mode|dark\s+mode|reduce\s+glare|night\s+driving|evening\s+mode)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 15,
     "Night mode — low brightness.", 0.88),

    # day mode
    (r"\b(?:day\s+mode|daytime\s+mode|increase\s+visibility|day\s+driving)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 85,
     "Day mode — high brightness.", 0.88),

    # max brightness
    (r"\b(?:max(?:imum)?|full|highest)\s+brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 100,
     "Max brightness.", 0.92),

    # min brightness
    (r"\b(?:min(?:imum)?|lowest|dimmest|darkest)\s+brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 5,
     "Min brightness.", 0.92),

    # half brightness
    (r"\b(?:half|medium|mid|50\s*%?)\s+brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 50,
     "Half brightness.", 0.90),

    # ═══════════════════════════════════════════════════════════════════════
    #  DASHBOARD BRIGHTNESS  ─  directional
    # ═══════════════════════════════════════════════════════════════════════

    # "dim / lower / reduce / decrease the dashboard / screen / brightness"
    (r"\b(?:dim(?:mer)?|lower|reduce|decrease|turn\s+down)\s+"
     r"(?:the\s+)?(?:dash(?:board)?|display|screen|brightness|panel|instrument\s+cluster)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 20,
     "Dim dashboard.", 0.90),

    # "brighten / raise / increase the dashboard"
    (r"\b(?:brighten(?:ing)?|raise|increase|turn\s+up|boost)\s+"
     r"(?:the\s+)?(?:dash(?:board)?|display|screen|brightness|panel)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 80,
     "Brighten dashboard.", 0.90),

    # "brightness up / down / higher / lower"
    (r"\bbrightness\s+(?:up|higher|more|increase)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 80,
     "Brightness up.", 0.87),

    (r"\bbrightness\s+(?:down|lower|less|decrease|reduce)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 20,
     "Brightness down.", 0.87),

    # "screen too bright / blinding / hurts eyes"
    (r"\b(?:screen|display|dash(?:board)?)\s+(?:is\s+)?(?:too\s+bright|blinding|glaring|hurts?\s+(?:my\s+)?eyes?)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 20,
     "Screen too bright — dim.", 0.89),

    # "screen too dim / can't see display"
    (r"\b(?:screen|display|dash(?:board)?)\s+(?:is\s+)?(?:too\s+dim|can['\s]?t\s+see|hard\s+to\s+read|dark)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 80,
     "Screen too dim — brighten.", 0.89),

    # eye strain / watering
    (r"\b(?:eyes?\s+(?:are\s+)?(?:water(?:ing)?|burning|hurting?|strained?|straining?)|eye\s*strain|eyes?\s+hurt)\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 20,
     "Eye strain — dim display.", 0.88),

    # "my eyes are watering from the brightness"
    (r"\beyes?\s+(?:are\s+)?water(?:ing)?\s+(?:from|because\s+of)\s+(?:the\s+)?brightness\b",
     "0x103", "SET_BRIGHTNESS", lambda m: 20,
     "Eyes watering from brightness — dim.", 0.90),

    # ═══════════════════════════════════════════════════════════════════════
    #  BRIGHTNESS  ─  status
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:what['\s]?s|check|is)\s+(?:the\s+)?(?:brightness|screen\s+brightness|display\s+brightness)\s*(?:at|set\s+to|level)?\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Brightness status.", 0.93),

    # ═══════════════════════════════════════════════════════════════════════
    #  GLOBAL STATUS QUERY  ─  "all systems" / "status" / "what's going on"
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:what['\s]?s\s+(?:the\s+)?(?:status|situation)|show\s+(?:me\s+)?(?:all|everything|the\s+status)|vehicle\s+status|system\s+status|all\s+systems|full\s+status|status\s+report)\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Full system status.", 0.96),

    (r"\b(?:what['\s]?s\s+going\s+on|overview|summary|current\s+settings?)\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Status overview.", 0.93),

    (r"\bstatus\b",
     None, "STATUS_QUERY", lambda m: 0,
     "Bare 'status'.", 0.90),

    # ═══════════════════════════════════════════════════════════════════════
    #  COMFORT / WELLBEING  ─  cabin feel / driver state
    # ═══════════════════════════════════════════════════════════════════════

    # drowsy / sleepy / tired → cool cabin
    (r"\b(?:i['\s]?m|i\s+am|i\s+feel(?:ing)?|getting|feeling)\s+"
     r"(?:really\s+|very\s+|so\s+)?(?:sleepy|drowsy|tired|exhausted|dozy|groggy|nodding\s+off|falling\s+asleep)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Drowsiness — cool cabin.", 0.85),

    # "wake me up / keep me awake / need to stay awake"
    (r"\b(?:wake\s+me\s+up|keep\s+me\s+awake|need\s+to\s+stay\s+awake|help\s+me\s+(?:stay|keep)\s+awake|keep\s+me\s+alert)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 18,
     "Keep driver awake — cool.", 0.84),

    # "cozy / comfortable / perfect / nice" → neutral
    (r"\b(?:cozy|comfortable|perfect|just\s+right|nice|pleasant|ideal)\s*(?:temp(?:erature)?|climate|in\s+here)?\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Comfort word — neutral temp.", 0.80),

    # "the cabin feels off / something is wrong with the climate"
    (r"\b(?:(?:the\s+)?cabin\s+feels?\s+off|something['\s]?s?\s+(?:off|wrong|not\s+right)\s+"
     r"(?:with\s+(?:the\s+)?(?:climate|temp|air|cabin|vent)))\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Cabin off — neutral temp.", 0.78),

    # "make it better / more comfortable / more pleasant in here"
    (r"\b(?:make|get)\s+it\s+(?:better|more\s+(?:comfortable|pleasant|bearable|livable|nice))\s*(?:in\s+here|inside)?\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Make it better — neutral temp.", 0.78),

    # "do something / fix the air / climate / temperature"
    (r"\bdo\s+something\s+(?:about|with|for)\s+(?:the\s+)?(?:air|temp(?:erature)?|climate|vent(?:ilation)?|cabin)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Do something — neutral temp.", 0.77),

    # indirect verbose: "temperature situation needs attention"
    (r"\b(?:temperature|temp|heat|fan|air|sunroof|lights?|brightness)\s+"
     r"(?:situation|level|setting|state|condition)?\s*"
     r"(?:needs?|requires?|demands?)\s+"
     r"(?:attention|adjustment|fixing|to\s+be\s+(?:fixed|changed|adjusted)|work)\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Indirect climate complaint.", 0.76),

    # "I need a change / I need something different"
    (r"\b(?:i\s+)?need\s+(?:a\s+)?(?:change|something\s+different|to\s+change\s+(?:the\s+)?(?:climate|temp|air))\b",
     "0x101", "SET_TEMPERATURE", lambda m: 22,
     "Need a change — neutral temp.", 0.75),

    # ═══════════════════════════════════════════════════════════════════════
    #  SAFETY / EMERGENCY
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:emergency|help|danger|danger\s+ahead|problem)\s+(?:lights?|flashers?|hazards?)\s+(?:on|activate|now)\b",
     "0x103", "SET_HEADLIGHTS", lambda m: 1,
     "Emergency lights on.", 0.98),

    (r"\b(?:pull\s+over|stop\s+the\s+car|car\s+breakdown|breakdown)\b",
     None, "SAFETY_ALERT", lambda m: 0,
     "Pull over / breakdown — safety alert.", 0.96),

    (r"\b(?:check\s+engine|engine\s+light|engine\s+warning|oil\s+light|warning\s+light)\b",
     None, "SAFETY_ALERT", lambda m: 0,
     "Engine/warning light — safety alert.", 0.95),

    (r"\b(?:car['\s]?s?\s+)?(?:making\s+a\s+(?:strange|weird|bad|funny)\s+(?:noise|sound)|strange\s+noise|weird\s+noise)\b",
     None, "SAFETY_ALERT", lambda m: 0,
     "Strange noise — safety alert.", 0.90),

    (r"\b(?:i\s+feel\s+(?:unwell|sick|dizzy|faint|nauseous)|feel\s+like\s+fainting|going\s+to\s+pass\s+out)\b",
     None, "SAFETY_ALERT", lambda m: 0,
     "Driver unwell — safety alert.", 0.92),

    # ═══════════════════════════════════════════════════════════════════════
    #  SPECIAL COMMANDS  ─  reset / undo / save
    # ═══════════════════════════════════════════════════════════════════════

    (r"\b(?:reset|default|back\s+to\s+(?:normal|default|factory)|factory\s+(?:settings?|reset)|restore\s+defaults?)\b",
     None, "MACRO_RESET", lambda m: 0,
     "Reset to defaults.", 0.92),

    # ═══════════════════════════════════════════════════════════════════════
    #  VAGUE / CATCH-ALL  ─  last deterministic resort before SLM
    # ═══════════════════════════════════════════════════════════════════════

    # "it's fine / it's ok / good enough" → neutral state, no action (STATUS)
    (r"\b(?:it['\s]?s\s+)?(?:fine|ok(?:ay)?|good\s+enough|all\s+good|no\s+complaints?)\b",
     None, "STATUS_QUERY", lambda m: 0,
     "All good — status check.", 0.75),

]


class RegexIntentResolver:
    def __init__(self) -> None:
        self._compiled = [
            (re.compile(pat, re.IGNORECASE), cid, cmd, vfn, reason, conf)
            for pat, cid, cmd, vfn, reason, conf in _PATTERNS
        ]

    def resolve(self, text: str) -> dict | None:
        start = time.monotonic()
        clean_text = text.strip().lower()

        # 1. Check for incomplete "naked" verbs first
        incomplete_verbs = {"open", "close", "set", "increase", "decrease", "turn on", "turn off"}
        
        if clean_text in incomplete_verbs:
            latency = (time.monotonic() - start) * 1000
            return {
                "command": "INCOMPLETE_COMMAND",
                "verb": clean_text,
                "handled_by": "Regex",
                "confidence": 1.0,
                "reason": "Driver issued a verb without a target.",
                "latency": f"{latency:.3f}ms",
            }

        # 2. Process standard regex patterns
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

                if cmd in ("STATUS_QUERY", "SAFETY_ALERT", "MACRO_RESET"):
                    return {
                        "command":    cmd,
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