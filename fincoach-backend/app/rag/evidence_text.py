"""Structural checks for source passages, without inventing or rewriting facts."""

import re

_GAP = re.compile(r"\[\s*\.{3}\s*\]|\.{3}|\u2026")
_LIST_ITEM = re.compile(r"(?:^|\n)\s*(?:[-*•]|\d{1,2}[.)])\s+\S")
_BOUNDARY = r"(?:^|(?<=[.!?])\s+|\n+)"
_PENDING_LABEL = re.compile(_BOUNDARY + r"[^\n.!?]{1,200}:\s*(?:\n[^\n.!?:]{1,35})?\s*$")
_LIST_INTRO = re.compile(
    _BOUNDARY + r"[^\n.!?]*(?:\bfollowing\b|\bbelow\b|\bas follows\b)[^\n.!?]*[.:]",
    re.I,
)
_OPEN_CONDITION = re.compile(
    r"\b(?:if|unless|provided|providing|subject|only|except|conditions?|"
    r"qualifications?|restrictions?|exceptions?|eligib\w*)\b", re.I,
)
_OPEN_END = re.compile(
    r"\b(?:if|unless|that|and|or|to|for|with|have|has|provided|not|cannot|"
    r"(?:must|should|shall|may|can|could|will|would)(?:\s+not)?|"
    r"tidak|bukan|perlu|mesti|wajib|boleh|hendaklah)\s*$", re.I,
)


def _visible_text_with_offsets(text: str) -> tuple[str, list[int]]:
    """Remove presentation syntax while mapping each visible character to its source.

    Only Markdown wrappers and link destinations are removed. Words, numbers,
    punctuation, list items and qualifications remain unchanged. The offset map
    lets a match return the actual fetched passage, rather than trusting the
    model's reconstructed quotation or using a fuzzy similarity threshold.
    """
    hidden = set()
    # Preserve link labels, including parentheses inside bounded destinations.
    for match in re.finditer(r"!?\[([^\]\n]+)\]\((?:[^()\n]|\([^()\n]*\))*\)", text):
        hidden.update(range(match.start(), match.start(1)))
        hidden.update(range(match.end(1), match.end()))
    for match in re.finditer(r"(?m)^ {0,3}#{1,6}[ \t]+", text):
        hidden.update(range(match.start(), match.end()))
    # Paired wrappers only: never delete arithmetic stars or an unpaired label.
    for pattern in (r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1",
                    r"(?<!\w)(\*|_|`)(?=\S)([^\n]+?)(?<=\S)\1(?!\w)"):
        for match in re.finditer(pattern, text):
            hidden.update(range(match.start(), match.start(2)))
            hidden.update(range(match.end(2), match.end()))
    visible, offsets = [], []
    for index, character in enumerate(text):
        if index in hidden:
            continue
        if character.isspace():
            if visible and visible[-1] != " ":
                visible.append(" ")
                offsets.append(index)
        else:
            visible.append(character)
            offsets.append(index)
    if visible and visible[-1] == " ":
        visible.pop()
        offsets.pop()
    return "".join(visible), offsets


def match_evidence_quote(quote: str, source: str) -> str | None:
    """Match literal visible text and recover an exact span of the fetched source.

    Formatting differences are harmless; changed facts and omitted intervening
    conditions cannot match. This never completes, translates or paraphrases a
    passage and never searches outside the excerpt supplied to the checker.
    """
    visible_source, offsets = _visible_text_with_offsets(source)
    visible_quote, _ = _visible_text_with_offsets(quote)
    if not visible_quote:
        return None
    start = visible_source.find(visible_quote)
    if start < 0:
        return None
    return source[offsets[start]:offsets[start + len(visible_quote) - 1] + 1]


def complete_evidence_passages(text: str) -> tuple[str, ...]:
    """Keep exact complete passages; discard obvious snippet/list cutoffs.

    This is a structural backstop, not a semantic verifier. The checker still
    establishes relevance and applicability. Never finish an instruction using
    guessed words, and never remove a dangling qualification to broaden a rule.
    Extraction gaps separate independent passages, rather than joining words
    from different parts of a page into one apparent statement.
    """
    pieces = _GAP.split(text)
    kept = []
    for piece in pieces:
        value = piece.strip()
        if not value:
            continue
        # A label with no actual list (possibly followed by a button name) is
        # not an application instruction. Keep preceding complete sentences.
        label = _PENDING_LABEL.search(value)
        if label and not _LIST_ITEM.search(value[label.start():]):
            if _OPEN_CONDITION.search(label.group()):
                continue  # Removing this condition would broaden the preceding fact.
            value = value[:label.start()].rstrip()
        for intro in _LIST_INTRO.finditer(value):
            if not _LIST_ITEM.search(value[intro.end():]):
                value = "" if _OPEN_CONDITION.search(intro.group()) else value[:intro.start()].rstrip()
                break
        if not value or _OPEN_END.search(value.rstrip("* .!?\"')")):
            continue
        if len(pieces) > 1 and not re.search(r"[.!?][\"')*]*$", value):
            # A gap cut a prose sentence. Salvage only preceding independent
            # sentences; a trailing 'only if ...' invalidates the whole piece.
            endings = list(re.finditer(r"[.!?][\"')*]*(?=\s|$)", value))
            if not endings:
                continue
            end = endings[-1].end()
            tail = value[end:]
            if _OPEN_CONDITION.search(tail) or _LIST_ITEM.search(value):
                continue
            value = value[:end]
        if value:
            kept.append(value)
    return tuple(dict.fromkeys(kept))
