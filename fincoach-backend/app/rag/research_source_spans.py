"""Literal structural units; source identity never comes from model labels."""
from dataclasses import dataclass
from hashlib import sha256
import re

_HEADING = re.compile(r"(?mi)^[ \t]*(?:#{1,6}[ \t]+[^\n]+|\*\*[^\n]+\*\*|"
    r"eligibility(?: criteria)?|who can apply|who is eligible|how to apply|"
    r"application (?:steps|process)|required documents|supporting documents|what you need|"
    r"kelayakan|cara memohon|dokumen (?:sokongan|diperlukan))[ \t]*$")
_FAQ = re.compile(r"(?<!\w)(?:\d{1,3}\.\s*)?[QS]\s*:\s*", re.I)
_LIST = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+")


@dataclass(frozen=True)
class SourceSpan:
    content: str
    document_hash: str
    start: int
    end: int
    heading_context: str
    unit_id: str
    complete: bool


def read_source_spans(page: str, *, anchors: tuple[str, ...], max_chars: int = 1800) -> tuple[SourceSpan, ...]:
    """Expand a located anchor to its FAQ/section/row, retaining literal scope.

    Long units return a bounded fragment with complete=False. Re-reading another
    item retains the same unit ID; no fragment proves a whole requirement list.
    """
    limit = max(0, min(1800, max_chars))
    if not page or not limit:
        return ()
    digest = sha256(page.encode()).hexdigest()
    headings = list(_HEADING.finditer(page))
    markers = sorted({0, *(m.start() for m in headings), *(m.start() for m in _FAQ.finditer(page))})
    if len(markers) == 1:
        markers.extend(m.end() for m in re.finditer(r"\n\s*\n", page)
            if not page[:m.start()].rstrip().endswith(":"))
    markers = sorted(set(markers))
    boundaries = [*markers[1:], len(page)]
    result, seen, remaining = [], set(), limit
    for anchor in anchors:
        position = page.find(anchor)
        if position < 0:
            position = page.casefold().find(anchor.casefold()) if anchor else -1
        if position < 0:
            continue
        start, end = next((s, e) for s, e in zip(markers, boundaries) if s <= position < e)
        unit_start, unit_end = start, end
        context = ""
        preceding = [m for m in headings if m.start() <= start]
        # A generic child heading such as "Required Documents" must retain its
        # Markdown ancestors: otherwise a table from another workflow appears
        # to be an unqualified document list. Sibling headings replace siblings.
        hierarchy = []
        for heading in preceding:
            level = re.match(r"^(#{1,6})[ \t]+", heading.group())
            if level:
                depth = len(level.group(1))
                hierarchy = [(d, h) for d, h in hierarchy if d < depth]
                hierarchy.append((depth, heading))
        if preceding:
            nearest = preceding[-1]
            owners = [h for _, h in hierarchy]
            if not owners or owners[-1] != nearest:
                owners.append(nearest)
            context = "\n".join(h.group().strip() for h in owners if h.start() < start)
        # A table row owns its category column and literal header, not the
        # neighboring row's condition. Keep the delimiter/header as context.
        line_start = page.rfind("\n", 0, position) + 1
        line_end = page.find("\n", position)
        line_end = len(page) if line_end < 0 else line_end
        if page[line_start:line_end].lstrip().startswith("|"):
            table_start = line_start
            while table_start > 0:
                previous_start = page.rfind("\n", 0, table_start - 1) + 1
                if not page[previous_start:table_start].lstrip().startswith("|"):
                    break
                table_start = previous_start
            table_lines = page[table_start:line_start].splitlines()
            header = "\n".join(table_lines[:2])
            if preceding and preceding[-1].start() == start:
                context = "\n".join(p for p in (context, preceding[-1].group().strip()) if p)
            context = "\n".join(p for p in (context, header) if p)
            start, end, unit_start, unit_end = line_start, line_end, line_start, line_end
        key = (unit_start, unit_end)
        if key in seen:
            continue
        seen.add(key)
        complete = len(context) + end - start <= remaining
        if not complete:
            # A repeated literal lead-in keeps list fragments owned by their
            # category even when the desired item occurs later in a long unit.
            lead = _LIST.search(page, unit_start, unit_end)
            if lead and lead.start() - unit_start <= 320:
                context = page[unit_start:lead.start()].strip()
            if len(context) >= remaining:
                context = context[:max(0, remaining // 3)]
            start = max(unit_start, page.rfind("\n", unit_start, position) + 1)
            if start == 0 and position > remaining:
                start = max(unit_start, page.rfind(" ", unit_start, position) + 1)
            end = min(unit_end, start + remaining - len(context))
            if end < unit_end:
                boundary = page.rfind("\n", start, end)
                if boundary > position:
                    end = boundary
        if end <= start:
            continue
        identity = sha256(f"{digest}:{unit_start}:{unit_end}".encode()).hexdigest()
        result.append(SourceSpan(page[start:end], digest, start, end, context, identity, complete))
        remaining -= end - start + len(context)
        if remaining <= 0:
            break
    return tuple(result)
