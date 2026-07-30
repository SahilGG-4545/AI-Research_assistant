"""
app/utils/text.py
─────────────────
Pure string/text utility functions shared across services.
No side-effects, no external I/O.
"""

import re
import json


def _normalize_for_match(text: str) -> str:
    """Lowercase + strip punctuation for deduplication/matching."""
    clean = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
    return " ".join(clean.split()).strip()


def _parse_year(value) -> int:
    """Extract a 4-digit year from any string representation."""
    text = str(value or "").strip()
    if not text:
        return 0
    match = re.search(r"\d{4}", text)
    if not match:
        return 0
    try:
        return int(match.group(0))
    except Exception:
        return 0


def _title_match_score(title: str, query: str):
    """Return (exact, contains, token_overlap) relevance scores."""
    norm_title = _normalize_for_match(title)
    norm_query = _normalize_for_match(query)

    if not norm_title or not norm_query:
        return (0, 0, 0.0)

    exact = 1 if norm_title == norm_query else 0
    contains = 1 if norm_query in norm_title else 0

    query_tokens = set(norm_query.split())
    title_tokens = set(norm_title.split())
    overlap = (len(query_tokens & title_tokens) / len(query_tokens)) if query_tokens else 0.0

    return (exact, contains, overlap)


def _extract_json_object(text: str) -> dict:
    """Safely extract a JSON object from a raw LLM response string."""
    if not isinstance(text, str):
        return {}

    payload = text.strip()
    if not payload:
        return {}

    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", payload)
    if not match:
        return {}

    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_string_list(value, fallback="Not clearly stated in abstract."):
    """Coerce a value to a clean list of strings (max 5 items)."""
    if isinstance(value, list):
        cleaned = [str(v).strip() for v in value if str(v).strip()]
    elif isinstance(value, str):
        parts = re.split(r"\n|;|,", value)
        cleaned = [p.strip(" -") for p in parts if p.strip()]
    else:
        cleaned = []

    if not cleaned:
        return [fallback]

    return cleaned[:5]


def _clean_text_value(value, fallback="Not specified"):
    """Return a clean single-line string, or fallback if empty."""
    if isinstance(value, str):
        text = " ".join(value.split()).strip()
    else:
        text = str(value).strip() if value is not None else ""
    return text if text else fallback


def _markdown_cell(value, max_len=140):
    """Truncate and sanitize a value for use inside a markdown table cell."""
    text = _clean_text_value(value, fallback="-")
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text.replace("|", "/")
