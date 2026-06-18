"""
intent_splitter.py
Splits compound driver commands into individual clauses safely.

Examples
────────
"Open the sunroof halfway and turn on the headlights"
    → ["Open the sunroof halfway", "turn on the headlights"]

"Make it cooler, then dim the lights"
    → ["Make it cooler", "dim the lights"]
"""

import re


# We explicitly look for conjunctions rather than bare commas
# to avoid breaking descriptive phrases like "long, relaxing drive".
_SPLIT_RE = re.compile(
    r",?\s+and\s+"
    r"|,?\s+also\s+"
    r"|,?\s+plus\s+"
    r"|,?\s+then\s+"
    r"|\.|;",
    flags=re.IGNORECASE,
)

_MIN_LEN = 4   # ignore fragments shorter than this


def split_intents(text: str) -> list[str]:
    """
    Returns a list of individual command strings.
    Always returns at least one element (the original text).
    """
    parts = _SPLIT_RE.split(text.strip())
    
    # Clean up whitespace and remove short fragments
    clauses = [p.strip() for p in parts if len(p.strip()) >= _MIN_LEN]
    
    # Fallback to the original text if everything was somehow stripped out
    return clauses if clauses else [text.strip()]