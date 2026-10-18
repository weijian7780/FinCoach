"""Bind approved positive quotations to literal, owned source qualifications."""
from dataclasses import dataclass, replace
from hashlib import sha256
import re

_CONDITION = re.compile(r'\b(?:if|when|only|foreign|married|adopted|eKasih|jika|sekiranya|asing|angkat|berkahwin)\b', re.I)


@dataclass(frozen=True)
class EvidenceFactBinding:
    binding_id: str
    quote_index: int
    source_span_id: str
    audience_anchor: str = ''
    condition_anchor: str = ''
    requirement_kind: str = 'informational'
    alternatives: tuple[str, ...] = ()
    relation: str = 'single'
    jurisdiction: str = 'Malaysia'
    period: str | None = None
    scope_known: bool = False


def source_identity(chunk) -> str:
    return sha256(((chunk.qualification_context or '') + '\n' + chunk.content).encode()).hexdigest()


def _literal(anchor, text):
    return ' '.join(anchor.casefold().split()) in ' '.join(text.casefold().split())


def validate_binding(binding: EvidenceFactBinding, quote: str, chunk, *, group=None) -> EvidenceFactBinding | None:
    owners = [s for s in chunk.source_spans if s.unit_id == binding.source_span_id and _literal(quote, s.content)]
    if owners:
        context = owners[0].heading_context + '\n' + owners[0].content
        complete = owners[0].complete
    elif binding.source_span_id == source_identity(chunk) and not chunk.source_spans:
        # Without structural ownership, a neighboring heading cannot supply a
        # condition. The approved quote must carry its own literal qualifiers.
        context, complete = quote, True
    else:
        return None
    if group is not None:
        # Groups are resolved by the backend registry, never supplied as text
        # by the model. Verify literal ownership before narrowing scope.
        if (group.source_span_id != binding.source_span_id
                or chunk.content[group.start:group.end] != group.content
                or not _literal(quote, group.content)):
            return None
        context = group.context + '\n' + group.content
        complete = complete and group.complete
    anchors = (binding.audience_anchor, binding.condition_anchor, *binding.alternatives)
    if group is not None:
        # Locally built composite qualifiers retain individual literal spans;
        # punctuation between conditions need not occur in their joined label.
        # This exception never applies to legacy model-written anchors.
        anchors = (*binding.audience_anchor.splitlines(),
                   *binding.condition_anchor.splitlines(), *binding.alternatives)
    if any(a and not _literal(a, context) for a in anchors):
        return None
    if binding.relation == 'any' and (len(binding.alternatives) < 2 or not re.search(r'\b(?:or|atau)\b', quote, re.I)):
        return None
    if group is None and binding.relation == 'all' and len(binding.alternatives) >= 2 and re.search(r'\b(?:or|atau)\b', quote, re.I):
        return None
    if binding.requirement_kind == 'mandatory' and re.search(r'\b(?:optional|may|boleh)\b', quote, re.I):
        return None
    # Group scope and requested-part completeness are independent contracts.
    # Only backend-owned closed atomic groups may retain known scope inside an
    # incomplete parent; legacy model-written bindings keep the old guard.
    known = binding.scope_known and (group.scope_known if group is not None else complete)
    if (_CONDITION.search(context) and not (binding.audience_anchor or binding.condition_anchor)
            and (group is None or _CONDITION.search(group.context))):
        # A complete backend-owned rule may state its condition inside the
        # approved quote itself. This is known source scope, not approval of a
        # draft: semantic verification must still preserve that condition.
        # Conditions outside the quoted rule need separate literal bindings.
        known = False
    return replace(binding, scope_known=known)
