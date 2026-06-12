"""
intent_parser.py
Resilient JSON extractor for raw SLM output.

Handles every known Qwen3 0.6B failure mode in order:
  1. <think>...</think> reasoning blocks
  2. Markdown code fences  ```json ... ```
  3. Free prose before the first '{'
  4. Truncated JSON missing closing brace
  5. Field-by-field regex extraction as last resort
"""

import re
import json


def extract_json(raw: str) -> dict | None:
    """Return a parsed dict or None if unrecoverable."""
    if not raw:
        return None

    # 1. Strip Qwen3 thinking blocks
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    text = re.sub(r"</think>", "", text)

    # 2. Strip markdown fences
    text = re.sub(r"```json\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()

    # 3. Happy path
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 4. Find first '{' and parse from there
    brace = text.find("{")
    if brace != -1:
        cand = text[brace:]
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass

        # 5. Truncation recovery
        suffixes = ['"}', '}']
        for suffix in suffixes:
            try:
                return json.loads(cand + suffix)
            except json.JSONDecodeError:
                continue

    # 6. Field-by-field regex
    result = {}
    for field, pat in [
        ("can_id",   r'"can_id"\s*:\s*"([^"]+)"'),
        ("function", r'"function"\s*:\s*"([^"]+)"'),
        ("value",    r'"value"\s*:\s*(\d+)'),
        ("reason",   r'"reason"\s*:\s*"([^"]+)"'),
    ]:
        m = re.search(pat, text)
        if m:
            result[field] = int(m.group(1)) if field == "value" else m.group(1)

    return result if len(result) >= 2 else None
