"""Parse, validate, and resolve LLM-offered coach choice cards.

These are OPTIONAL tappable suggestions the model may append to an ordinary
answer, gated by ``COACH_LLM_CHOICES_ENABLED`` (default off). They are distinct
from read clarifications (:mod:`app.rag.read_clarification`): a clarification
card *resumes* a saved financial read, whereas a choice card *submits a brand-new
query* through the normal routing + authorization path. Nothing here trusts the
model with tool arguments, permissions, or resume state — only a short ``label``
and a complete natural-language ``query`` per option.

The model emits exactly one explicitly tagged block:

    <<<FINCOACH_CHOICES>>>
    {"choices": [{"label": "Review food spending", "query": "How much did I spend on Food this month?"}]}
    <<<END_FINCOACH_CHOICES>>>

Only that dedicated block is parsed — never ordinary bullets, quotations, or
code fences. The block is always stripped from the visible answer so raw metadata
is never shown, even when it is malformed or truncated. Malformed, truncated, or
empty metadata yields usable prose with no cards (fail-open). Option ids are
generated here on the backend; the model never supplies them.

Pure functions: no Supabase, no LLM, no config import (the caller owns the flag).
"""

from __future__ import annotations

import json
import re

PAYLOAD_TYPE = "coach_choices"
STATE_VERSION = 1

# Conservative limits. A choice row is small on purpose; anything larger is
# treated as malformed rather than truncated for display.
MAX_CHOICES = 4
MAX_LABEL = 60
MAX_QUERY = 200

_OPEN = "<<<FINCOACH_CHOICES>>>"
_CLOSE = "<<<END_FINCOACH_CHOICES>>>"
_BLOCK = re.compile(re.escape(_OPEN) + r"(.*?)" + re.escape(_CLOSE), re.DOTALL)


def extract_choice_block(text: str) -> tuple[str, str | None]:
    """Split an answer into (visible_text, raw_choice_json_or_None).

    Every tagged block is removed from the visible text so raw metadata is never
    surfaced, but only the first well-formed block's inner JSON is returned for
    parsing. An opening marker with no closing marker (a truncated stream) is
    stripped from the marker onward and yields no parseable block.
    """
    source = text or ""
    if _OPEN not in source:
        # No metadata: leave an ordinary answer exactly as written.
        return source, None

    match = _BLOCK.search(source)
    if match is None:
        # Opening marker but no matching close: drop the dangling remainder so a
        # partial JSON fragment is never shown, and offer nothing to parse.
        visible = source[: source.index(_OPEN)]
        return visible.strip(), None

    raw = match.group(1)
    # Remove ALL blocks (not just the first) so a second stray block can't leak.
    visible = _BLOCK.sub("", source)
    # A dangling open marker after the last complete block is also scrubbed.
    if _OPEN in visible:
        visible = visible[: visible.index(_OPEN)]
    return _collapse_blank_lines(visible), raw


def _collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def parse_choices(raw: str | None) -> list[dict] | None:
    """Validate the raw block into a list of ``{id, label, query}`` or ``None``.

    Strict: any structurally invalid option invalidates the whole block, so the
    caller falls back to plain prose rather than rendering a partial set.
    """
    if not raw or not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None

    items = data.get("choices") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        return None
    if len(items) > MAX_CHOICES:
        return None

    options: list[dict] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return None
        label = item.get("label")
        query = item.get("query")
        if not isinstance(label, str) or not isinstance(query, str):
            return None
        label = " ".join(label.split())
        query = " ".join(query.split())
        if not label or not query:
            return None
        if len(label) > MAX_LABEL or len(query) > MAX_QUERY:
            return None
        options.append({"id": f"c{index}", "label": label, "query": query})

    return options or None


def build_choices_payload(options: list[dict], *, origin_message_id: str) -> dict:
    """Serialise validated options into a client ui_payload, kept separate from
    read clarifications (its own ``type`` and ``state`` version)."""
    return {
        "type": PAYLOAD_TYPE,
        "input_type": "single_select",
        "options": [
            {"id": option["id"], "label": option["label"], "query": option["query"]}
            for option in options
        ],
        "state": {
            "version": STATE_VERSION,
            "origin_message_id": str(origin_message_id),
        },
    }


def resolve_choice_query(payload: object, option_id: str) -> str | None:
    """Return the server-saved ``query`` for a selected option id, or ``None``.

    The selection is resolved only against the saved payload — never against
    client-supplied text — so a tapped choice runs exactly the query the backend
    validated and stored.
    """
    if not isinstance(payload, dict) or payload.get("type") != PAYLOAD_TYPE:
        return None
    state = payload.get("state")
    if not isinstance(state, dict) or state.get("version") != STATE_VERSION:
        return None
    if not isinstance(option_id, str) or not option_id:
        return None
    for option in payload.get("options") or []:
        if isinstance(option, dict) and option.get("id") == option_id:
            query = option.get("query")
            if isinstance(query, str) and query.strip():
                return query
            return None
    return None
