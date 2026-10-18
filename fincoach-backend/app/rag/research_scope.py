"""Local checks of the verifier's scope contract, not a semantic overlap oracle."""
import re

RELATIONS = {'preserved', 'broadened', 'wrong_category', 'unjustifiably_exclusive', 'unclear'}
MISAPPLIED_RELATIONS = RELATIONS - {'preserved', 'unclear'}
_CONDITION = re.compile(r'\b(?:if|when|only|foreign|married|adopted|citizen|non[- ]citizen|eKasih|jika|sekiranya|asing|angkat|warganegara|berkahwin)\b', re.I)
_REQUIREMENT = re.compile(r'\b(?:need|required?|must|eligible|qualif\w*|spouse|children|document|provide|only|perlu|layak|pasangan|anak|dokumen)\b', re.I)


def normalized_anchor(text):
    text = re.sub(r'\[S\d+\]', '', text)
    text = re.sub(r'[*_`#]', '', text)
    return ' '.join(text.casefold().split())


def _owned_source_anchor(anchor, reference, bindings):
    if normalized_anchor(anchor) in normalized_anchor(reference):
        return True
    # A checker may concatenate a parent/child path. Resolve it only when it
    # exactly names a backend-proven hierarchy and every component is literal.
    # Arbitrary omitted text, ellipses and reconstructed conditions still fail.
    return any(b.scope_known and '\n' in b.audience_anchor
        and normalized_anchor(anchor) == normalized_anchor(b.audience_anchor)
        and all(normalized_anchor(a) in normalized_anchor(reference)
            for a in b.audience_anchor.splitlines() if a.strip()) for b in bindings)


def needs_scope_anchor(claim, sources):
    # A condition elsewhere on a multi-topic page must not qualify every fact.
    # Reported anchors are checked separately, and the semantic verifier must
    # report relevant source-only conditions even when omitted from the claim.
    return bool(_REQUIREMENT.search(claim) and _CONDITION.search(claim))


def scope_verdict(item, claim, references, *, bindings=()):
    """Fail just this claim on missing/invalid scope fields; retain independent facts.

    Literal anchors prove that the verifier cited real context. They cannot
    establish whether an unreported qualifier was missed; live semantic controls
    and manual review are still necessary.
    """
    relation = item.get('scope_relation')
    if relation not in RELATIONS or relation == 'unclear':
        return 'unsupported'
    if relation in MISAPPLIED_RELATIONS:
        return 'misapplied'
    # An explicitly unknown binding cannot authorize a positive assertion in
    # any language. Wording must not turn unknown applicability into certainty.
    if bindings and any(not b.scope_known for b in bindings):
        return 'unsupported'
    if bindings and all(b.requirement_kind == 'optional' for b in bindings) and re.search(r'\b(?:must|required|wajib)\b', claim.text, re.I):
        return 'misapplied'
    sources = [references[i-1] for i in claim.cited_indices if 1 <= i <= len(references)]
    detail_fields = ('source_qualifier', 'qualifier_source_index', 'claim_qualifier')
    conditional = any(b.audience_anchor or b.condition_anchor for b in bindings)
    if conditional or needs_scope_anchor(claim.text, sources) or any(key in item for key in detail_fields):
        source_index = item.get('qualifier_source_index')
        source_anchor, claim_anchor = item.get('source_qualifier'), item.get('claim_qualifier')
        if (type(source_index) is not int or source_index not in claim.cited_indices
                or not 1 <= source_index <= len(references)
                or not isinstance(source_anchor, str) or not source_anchor.strip()
                or not isinstance(claim_anchor, str) or not claim_anchor.strip()
                or not normalized_anchor(source_anchor) or not normalized_anchor(claim_anchor)
                or not _owned_source_anchor(source_anchor, references[source_index-1], bindings)
                or normalized_anchor(claim_anchor) not in normalized_anchor(claim.text)):
            return 'unsupported'
        # Category paths are hierarchical: the leaf identifies the audience,
        # while every independent condition still needs its own literal pair.
        # Never require a concatenated heading path to occur in one sentence.
        pairs = item.get('qualifier_anchors', [dict(source_index=source_index,
            source=source_anchor, claim=claim_anchor)])
        if not isinstance(pairs, list) or not 1 <= len(pairs) <= 10:
            return 'unsupported'
        verified_anchors = []
        for pair in pairs:
            if not isinstance(pair, dict):
                return 'unsupported'
            idx, source, target = pair.get('source_index'), pair.get('source'), pair.get('claim')
            if (type(idx) is not int or idx not in claim.cited_indices
                    or not 1 <= idx <= len(references)
                    or not isinstance(source, str) or not isinstance(target, str)
                    or not normalized_anchor(source) or not normalized_anchor(target)
                    or not _owned_source_anchor(source, references[idx-1], bindings)
                    or normalized_anchor(target) not in normalized_anchor(claim.text)):
                return 'unsupported'
            verified_anchors.append(normalized_anchor(source))
        required = []
        for binding in bindings:
            audience = [a.strip() for a in binding.audience_anchor.splitlines() if a.strip()]
            if audience:
                required.append(audience[-1])
            required.extend(a.strip() for a in binding.condition_anchor.splitlines() if a.strip())
        if any(not any(normalized_anchor(a) in anchor for anchor in verified_anchors) for a in required):
            return 'unsupported'
    return 'supported'


def research_verifier_cap(claims, references):
    qualified = sum(needs_scope_anchor(c.text, [references[i-1] for i in c.cited_indices
                    if 1 <= i <= len(references)]) for c in claims)
    return min(4096, max(1500, 128 + 80*len(claims) + 120*qualified))
