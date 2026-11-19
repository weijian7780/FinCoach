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
# Two complete endings a generated sentence may have although its last word is
# otherwise a dangling one: "…whether you qualify or not." and a preposition
# closing an earlier what/which/that clause ("…what the grace period is for.").
# Unfinished modal or negative rules ("Applicants cannot.") stay incomplete.
_CLOSING = r"\s*[\"')*]*[.!?][\"')*]*\s*$"
_COMPLETE_OR_NOT = re.compile(r"\b(?:or\s+not|atau\s+tidak)" + _CLOSING, re.I)
_COMPLETE_STRANDED_PREPOSITION = re.compile(
    r"\b(?:what|which|who|whom|where|that)\b[^.!?]*\s"
    r"(?:for|with|of|on|about|from|in|at|into)" + _CLOSING, re.I,
)


def allowed_generated_ending(sentence: str) -> bool:
    """Whether a finished generated sentence legitimately ends on a dangling word."""
    text = str(sentence or "").strip()
    return bool(_COMPLETE_OR_NOT.search(text) or _COMPLETE_STRANDED_PREPOSITION.search(text))


_LINE_BULLET = re.compile(r"(?m)^[ \t]*(?P<marker>[-*•]|\d{1,3}[.)])(?=[ \t]+\S)")


def _bullet_kinds(text: str) -> set[str]:
    return {"number" if marker[0].isdigit() else marker
            for match in _LINE_BULLET.finditer(text)
            if (marker := match.group("marker"))}


def _visible_text_with_offsets(text: str, *, inline_bullets: set[str] | None = None) -> tuple[str, list[int]]:
    """Remove presentation syntax while mapping each visible character to its source.

    Markdown wrappers, link destinations and list markers are presentation;
    words, factual numbers, punctuation, items and qualifications stay literal.
    Inline markers are removed only when the other text has that line-list style.
    The offset map
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
    for match in _LINE_BULLET.finditer(text):
        hidden.update(range(match.start("marker"), match.end("marker")))
    for kind in inline_bullets or ():
        marker = r"\d{1,3}[.)]" if kind == "number" else re.escape(kind)
        for match in re.finditer(r"(?<!\S)" + marker + r"(?=\s+\S)", text):
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
    # Never infer inline source markers from the quote: a number or arithmetic
    # operator in a source sentence is a fact, not list formatting.
    visible_source, offsets = _visible_text_with_offsets(source)
    visible_quote, _ = _visible_text_with_offsets(quote, inline_bullets=_bullet_kinds(source))
    if not visible_quote:
        return None
    start = visible_source.find(visible_quote)
    if start < 0:
        return None
    return source[offsets[start]:offsets[start + len(visible_quote) - 1] + 1]


def complete_evidence_passages(text: str, *, generated: bool = False) -> tuple[str, ...]:
    """Keep exact complete passages; discard obvious snippet/list cutoffs.

    This is a structural backstop, not a semantic verifier. The checker still
    establishes relevance and applicability. Never finish an instruction using
    guessed words, and never remove a dangling qualification to broaden a rule.
    Extraction gaps separate independent passages, rather than joining words
    from different parts of a page into one apparent statement. A generated
    answer sentence (``generated=True``) may also end with one of the complete
    endings in ``allowed_generated_ending``; source passages never may.
    """
    pieces = _GAP.split(text)
    kept = []
    for piece in pieces:
        kept.extend(_complete_piece(piece, gapped=len(pieces) > 1, generated=generated))
    return tuple(dict.fromkeys(kept))


# A one-word reply that answers the question just before it ("…? Tidak.") and a
# passive participle closing a sentence ("…must be provided.") are finished,
# although their last word otherwise marks an unfinished rule.
_SHORT_ANSWER_AFTER_QUESTION = re.compile(
    r"\?[\s\"')*]*(?:\w{1,2}\s*:\s*)?(?:tidak|bukan)\s*[.!][\"')*]*\s*$", re.I)
_PASSIVE_PROVIDED = re.compile(
    r"\b(?:be|been|being|is|are|was|were)\s+provided\s*\.[\"')*]*\s*$", re.I)


def _unfinished(value: str, *, generated: bool) -> bool:
    if not _OPEN_END.search(value.rstrip("* .!?\"')")):
        return False
    if _SHORT_ANSWER_AFTER_QUESTION.search(value) or _PASSIVE_PROVIDED.search(value):
        return False
    return not (generated and allowed_generated_ending(value))


# A sentence points at a list only when the cue closes it: "…shown below.",
# "…as follows.", "…the following:". "following" with a few words after it
# points at a list when the sentence ends in ':', states a condition
# ("…eligible if the following are met."), or names several things
# ("upload the following documents."). A single thing ("credited in the
# following month.") is an ordinary sentence, and "below" followed by more
# words ("income below RM5,000 qualify") is an ordinary comparison.
_POINTER_END = re.compile(r"(?:\bbelow|\bas\s+follows|\bthe\s+following)\s*[.:]\s*$", re.I)
_FOLLOWING_TAIL = re.compile(
    r"\bfollowing(?:\s+(?P<noun>[^\W\d]+))?(?:\s+[^\W\d]+){0,2}\s*(?P<end>[.:])\s*$", re.I)


def _is_list_pointer(sentence: str) -> bool:
    text = sentence.strip()
    if _POINTER_END.search(text):
        return True
    tail = _FOLLOWING_TAIL.search(text)
    if not tail:
        return False
    noun = (tail.group("noun") or "").casefold()
    names_several = len(noun) > 3 and noun.endswith("s") and not noun.endswith("ss")
    return tail.group("end") == ":" or names_several or bool(_OPEN_CONDITION.search(text))


def _complete_piece(piece: str, *, gapped: bool, generated: bool) -> list[str]:
    """Complete passages of one gap-free piece, each an exact span of it."""
    value = piece.strip()
    if not value:
        return []
    # A label with no actual list (possibly followed by a button name) is
    # not an application instruction. Keep preceding complete sentences.
    label = _PENDING_LABEL.search(value)
    if label and not _LIST_ITEM.search(value[label.start():]):
        if _OPEN_CONDITION.search(label.group()):
            return []  # Removing this condition would broaden the preceding fact.
        value = value[:label.start()].rstrip()
    after = ""
    for intro in _LIST_INTRO.finditer(value):
        if not _is_list_pointer(intro.group()):
            continue  # "below RM5,000", "the following month": ordinary words
        if not _LIST_ITEM.search(value[intro.end():]):
            if _OPEN_CONDITION.search(intro.group()):
                return []  # Removing this condition would broaden the preceding fact.
            # A finished sentence pointing at a missing list ("…shown below.")
            # is the only text removed; independent sentences after it are
            # returned as their own span, never joined to the text before it.
            # After an intro ending in ':' the text is that missing list's
            # content, which cannot be checked for completeness.
            if intro.group().rstrip().endswith("."):
                after = value[intro.end():]
            value = value[:intro.start()].rstrip()
            break
    passages = []
    if value and not _unfinished(value, generated=generated):
        if gapped and not re.search(r"[.!?][\"')*]*$", value):
            # A gap cut a prose sentence. Salvage only preceding independent
            # sentences; a trailing 'only if ...' invalidates the whole piece.
            endings = list(re.finditer(r"[.!?][\"')*]*(?=\s|$)", value))
            end = endings[-1].end() if endings else 0
            tail = value[end:]
            if not endings or _OPEN_CONDITION.search(tail) or _LIST_ITEM.search(value):
                value = ""
            else:
                value = value[:end]
        if value:
            passages.append(value)
    if after.strip():
        passages.extend(_complete_piece(after, gapped=gapped, generated=generated))
    return passages
