"""Complete per-part records from one model call; records are not factual approval."""
from __future__ import annotations
from dataclasses import dataclass, field
import json
import re


@dataclass(frozen=True)
class ResearchBlock:
    part_id: str
    section: str
    text: str
    binding_ids: tuple[str, ...] = field(default=(), kw_only=True)


def unit_key(text: str) -> str:
    from app.rag.research_answer import _MARKER
    return ' '.join(_MARKER.sub('', text).split())


def part_unit_keys(blocks: tuple[ResearchBlock, ...]) -> dict[str, tuple[str, ...]]:
    from app.rag.research_answer import _body_units
    result: dict[str, list[str]] = {}
    for block in blocks:
        # Each fact record retains its own bindings; coverage must include all
        # records for a part rather than silently replacing earlier facts.
        result.setdefault(block.part_id, []).extend(
            unit_key(u[1]) for u in _body_units(f'**{block.section}**\n{block.text}'))
    return {part: tuple(dict.fromkeys(keys)) for part, keys in result.items()}


def parse_finished_blocks(text: str, *, allowed_part_ids: tuple[str, ...],
    allowed_binding_ids: tuple[str, ...] = (), require_bindings: bool = False,
    allowed_source_ids: tuple[int, ...] = ()) -> tuple[ResearchBlock, ...]:
    from app.rag.research_answer import safe_draft_units, _body_units
    if len(text) > 24000:
        raise ValueError('Record payload too large')
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 6:
        raise ValueError('Too many part records')
    result, seen, seen_units, words = [], set(), set(), 0
    for index, line in enumerate(lines):
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            if index == len(lines)-1:
                break  # The final unfinished record cannot erase earlier records.
            raise ValueError('Malformed nonfinal record')
        if (not isinstance(raw, dict) or set(raw) not in ({'part_id','section','text'}, {'part_id','section','text','binding_ids'})
                or not isinstance(raw['part_id'], str) or not isinstance(raw['section'], str)
                or raw['part_id'] not in allowed_part_ids
                or raw['section'] not in {'Insight','Recommended action'}
                or not isinstance(raw['text'], str) or not raw['text'].strip()
                or '**' in raw['text']):
            raise ValueError('Invalid part record contract')
        # Numeric citation presentation does not create source authority.
        # Resolve only already-approved IDs; the semantic checker still proves
        # the claim and unknown IDs remain unusable.
        raw['text'] = re.sub(r'\[(\d{1,2})\]', lambda m: f'[S{int(m.group(1))}]'
            if int(m.group(1)) in allowed_source_ids else m.group(), raw['text'])
        if re.search(r'\[\d{1,2}\]', raw['text']):
            continue  # Unresolved numeric markers cannot become uncited facts.
        identity = (raw['part_id'], unit_key(raw['text']))
        # A requested part can contain explanatory facts and procedural actions.
        # Their presentation section does not change source ownership. Reject
        # duplicate/overlapping facts below, rather than valid section changes.
        if identity in seen:
            raise ValueError('Duplicate part record')
        bindings = raw.get('binding_ids', [])
        if (not isinstance(bindings, list) or len(bindings) > 10 or
                any(not isinstance(i, str) or i not in allowed_binding_ids for i in bindings)):
            continue
        if require_bindings and not bindings and '[S' in raw['text']:
            continue
        seen.add(identity)
        words += len(raw['text'].split())
        if words > 200:
            raise ValueError('Part answer exceeds word budget')
        body = f"**{raw['section']}**\n{raw['text']}"
        safe = safe_draft_units(body, allow_gap_notes=True)
        if not safe or len(safe) != len(_body_units(body)):
            continue  # Complete JSON cannot complete a dangling natural-language phrase.
        keys = {unit_key(u[1]) for u in _body_units(body)}
        if keys & seen_units:
            raise ValueError('Overlapping fact records would overwrite bindings')
        seen_units.update(keys)
        result.append(ResearchBlock(raw['part_id'], raw['section'], raw['text'].strip(),
            binding_ids=tuple(dict.fromkeys(bindings))))
    return tuple(result)


def unit_binding_ids(blocks: tuple[ResearchBlock, ...]) -> dict[str, tuple[str, ...]]:
    return {key: block.binding_ids for block in blocks
        for key in part_unit_keys((block,)).get(block.part_id, ())}


def render_blocks(blocks: tuple[ResearchBlock, ...], *, retained_verified_text: str = '') -> str:
    from app.rag.research_answer import _render, safe_draft_units, _MARKER
    units = safe_draft_units(retained_verified_text, allow_gap_notes=True) if retained_verified_text else []
    seen = {u[1] for u in units}
    for block in blocks:
        incoming = safe_draft_units(f'**{block.section}**\n{block.text}', allow_gap_notes=True)
        if incoming and all(u[1] in seen for u in incoming):
            continue
        # A list and its category retain one shared identity. Offsetting each
        # item separately would detach its condition during verification.
        offset = max((u[2] for u in units), default=0)+1
        for section, text, group in incoming:
            seen.add(text)
            units.append((section, text, offset+group))
    rendered = _render(units)
    if len(_MARKER.sub('', rendered).split()) > 220:  # headings/disclaimer also consume output
        raise ValueError('Merged answer exceeds word budget')
    return rendered
