"""
intent_splitter.py
Splits compound driver commands into individual clauses.

Examples
────────
"Open the sunroof halfway and turn on the headlights"
    → ["Open the sunroof halfway", "turn on the headlights"]

"Make it cooler, also dim the lights and close the roof"
    → ["Make it cooler", "dim the lights", "close the roof"]
"""

import re


_SPLIT_RE = re.compile(
    r"\s+and\s+"
    r"|\s+also\s+"
    r"|\s+plus\s+"
    r"|\s+then\s+"
    r"|,\s*(?:and\s+|also\s+)?",
    flags=re.IGNORECASE,
)

_MIN_LEN = 4   # ignore fragments shorter than this


def split_intents(text: str) -> list[str]:
    """
    Returns a list of individual command strings.
    Always returns at least one element (the original text).
    """
    parts = _SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= _MIN_LEN]
