"""Literal requirement groups selected by ID, never reconstructed by a model."""
from dataclasses import dataclass, replace
from hashlib import sha256
import re
from app.rag.evidence_text import complete_evidence_passages
from app.rag.research_fact_bindings import source_identity

_CATEGORY = re.compile(r'(?<!\w)[a-z]\.\s+[^:/\.!?\n]{1,80}:(?=\s|$)', re.I)
_CHILD = re.compile(r'(?<!\w)[ivx]{1,5}\.\s+[^•.;:\n]{1,80}(?=\s*•)', re.I)
_TAIL = re.compile(r'(?<!\w)(?:Borang\s+[^.!?\n]{1,100}?\s+(?:perlu|hendaklah)\b|(?:Submit|Upload|Complete)\s+(?:the|your|these)\b)', re.I)
_CONDITION = re.compile(r'\([^)]*\b(?:if|when|jika|sekiranya)\b[^)]*\)|'
    r'\b(?:if|when|only|unless|provided|subject to|except|jika|sekiranya|hanya|tertakluk)\b[^.!?\n]*', re.I)
_MEMBER = re.compile(r'(?<!\w)[ivx]{1,5}\.\s+|•\s*', re.I)


@dataclass(frozen=True)
class EvidenceGroup:
    group_id: str
    source_id: int
    source_span_id: str
    start: int
    end: int
    content: str
    context: str
    audience_anchor: str
    condition_anchor: str
    requirement_kind: str
    alternatives: tuple[str, ...]
    relation: str
    complete: bool
    scope_known: bool = False


def evidence_groups(chunks) -> tuple[EvidenceGroup, ...]:
    """Split recognizable owned categories; preserve ambiguous prose as one unit.

    Offsets refer to the original chunk. Parent qualifiers are literal context,
    not newly approved facts. A fragment or oversized anchor is never promoted
    to a complete requirement merely because its ID is valid.
    """
    result = []
    for source_id, chunk in enumerate(chunks[:10], 1):
        if not chunk.content.strip() or chunk.confidence == 'insufficient':
            continue
        spans = chunk.source_spans
        units = [(s.unit_id, chunk.content.find(s.content), s.content,
                  s.heading_context, s.complete) for s in spans if s.content in chunk.content]
        if not spans:
            units = [(source_identity(chunk), 0, chunk.content, chunk.qualification_context or '',
                      complete_evidence_passages(chunk.content) == (chunk.content.strip(),))]
        for owner, offset, text, heading, complete in units:
            categories = list(_CATEGORY.finditer(text))
            children = list(_CHILD.finditer(text)) if categories else []
            tails = [m for m in _TAIL.finditer(text)
                     if categories and m.start() > categories[-1].end()]
            markers = sorted([(m.start(), 'category', m.group()) for m in categories]
                + [(m.start(), 'child', m.group()) for m in children]
                + [(m.start(), 'tail', '') for m in tails])
            # No known hierarchy: leave this literal unit intact, rather than
            # guessing category ownership from a document name or keyword.
            if not markers:
                markers = [(0, 'unit', heading)]
                if not complete and '\n\n' in text:
                    # A closed paragraph can supply one independent fact while
                    # the parent extraction remains incomplete. Never split a
                    # requirement list or a condition from its dependent body.
                    boundaries = [0] + [m.end() for m in re.finditer(r'\n\s*\n', text)]
                    if not re.search(r'(?m)^\s*(?:[-•]|\d+[.)])\s|:\s*(?:\n|$)', text):
                        markers = [(p, 'atomic', heading) for p in boundaries if text[p:].strip()]
            prefix = text[:markers[0][0]]
            condition = '\n'.join(m.group() for m in _CONDITION.finditer(heading+'\n'+prefix))
            parent = ''
            for i, (start, kind, label) in enumerate(markers):
                group_prefix = prefix
                if kind == 'tail' and prefix.rstrip().endswith(':'):
                    # A colon introduces the following category list. Its last
                    # introductory clause qualifies that list, not a new
                    # standalone submission procedure. Earlier sentences and
                    # the owned heading remain universal constraints.
                    boundaries = list(re.finditer(r'[.!?]\s+', prefix))
                    candidate = prefix[:boundaries[-1].end()] if boundaries else ''
                    introduction = prefix[len(candidate):]
                    local_conditions = [m.group() for m in _CONDITION.finditer(introduction)]
                    # Only a document list's generic applicability annotation
                    # is local to that list. Residency, audience and other
                    # substantive eligibility conditions remain in force.
                    if (re.search(r'\b(?:documents?|dokumen)\b', introduction, re.I)
                            and all(re.fullmatch(r'\(\s*(?:if applicable|jika berkaitan)\s*\)',
                                c, re.I) for c in local_conditions)):
                        group_prefix = candidate
                condition = '\n'.join(m.group() for m in _CONDITION.finditer(heading+'\n'+group_prefix))
                end = markers[i+1][0] if i+1 < len(markers) else len(text)
                if kind == 'category':
                    parent = label
                elif kind == 'tail':
                    parent = ''
                audience = '\n'.join(dict.fromkeys(x for x in (heading, parent,
                                      label if kind in {'child', 'unit'} else '') if x))
                body = text[start:end].strip()
                if not body or (kind == 'category' and body == label.strip()):
                    continue
                # Trim offsets with exactly the same whitespace as the text.
                left = len(text[start:end])-len(text[start:end].lstrip())
                right = len(text[start:end])-len(text[start:end].rstrip())
                start, end = start+left, end-right
                # Keep the literal owned audience components contiguous. The
                # introductory conditions remain separate qualification text.
                context = '\n'.join(x for x in (audience, group_prefix) if x)
                necessary = bool(re.search(r'\b(?:must|required|wajib|hendaklah|perlu)\b', context+'\n'+body, re.I))
                optional = bool(re.search(r'\b(?:optional|pilihan|tidak wajib)\b', body, re.I))
                # "Can upload" describes a channel; it does not prove that
                # documents elsewhere in the parent FAQ are optional.
                channel = bool(re.search(r'\b(?:may|boleh)\b', body, re.I))
                requirement = 'optional' if optional else 'mandatory' if necessary and not channel else 'informational'
                member_body = body[len(label.strip()):].lstrip() if kind == 'child' else body
                members = tuple(p.strip(' ;\n') for p in _MEMBER.split(member_body)[1:] if p.strip(' ;\n')) if requirement == 'mandatory' else ()
                safe_members = len(members) <= 6 and all(len(p) <= 160 for p in members)
                # An "or" within one bullet does not join separate bullets:
                # (passport OR ID) AND marriage certificate stays an all-list.
                joins = [bool(re.search(r'\b(?:or|atau)\s*$', p, re.I)) for p in members[:-1]]
                explicit_any = bool(joins) and all(joins)
                relation = 'any' if explicit_any else 'all' if len(members) >= 2 else 'single'
                ambiguous_join = any(joins) and not explicit_any
                safe_scope = len(audience) <= 160 and len(condition) <= 160 and safe_members and not ambiguous_join
                closed_atomic = (kind == 'atomic' and i+1 < len(markers)
                    and bool(re.search(r'[.!?][*\"\')]*$', body))
                    and complete_evidence_passages(body) == (body,)
                    and not re.match(r'(?:it|this|these|they|such|and|or)\b', body, re.I)
                    and not re.search(r'\b(?:if|only|unless|provided|subject to|jika|hanya)\b', text[:start], re.I))
                known = safe_scope and (complete or closed_atomic)
                identity = sha256(f'{owner}:{offset+start}:{offset+end}'.encode()).hexdigest()
                result.append(EvidenceGroup(identity, source_id, owner, offset+start, offset+end,
                    body, context, audience if len(audience) <= 160 else '',
                    condition if len(condition) <= 160 else '', requirement,
                    members if safe_members else (), relation, complete and safe_scope, known))
    if len(result) > 40:
        omitted_sources = {g.source_id for g in result[40:]}
        result = [replace(g, complete=False) if g.source_id in omitted_sources else g for g in result[:40]]
    return tuple(result)
