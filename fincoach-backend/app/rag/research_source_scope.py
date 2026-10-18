"""Source workflow titles constrain evidence; they never establish policy facts."""
import re

# A different lifecycle operation cannot establish first-application rules.
# This vocabulary describes workflows, not any programme's requirements.
_OPERATIONS = (
    r'\badd(?:ing)?\s+(?:a\s+|an\s+)?(?:facility|loan|debt)\b',
    r'\b(?:appeal|appealing|rayuan)\b',
    r'\b(?:renew(?:al|ing)?|pembaharuan)\b',
    r'\b(?:terminat(?:e|ion|ing)|penamatan)\b',
    r'\b(?:update\s+(?:an?\s+)?application|kemas\s+kini\s+permohonan)\b',
)


def source_workflow_conflicts(plan, chunk) -> bool:
    """Reject an explicit mismatched operation, without guessing from a URL.

    General definitions/services may legitimately discuss several workflows.
    A page explicitly describing a different operation cannot support a user's
    application/document request merely because the institution matches.
    """
    if not plan.part_tracking or not any(re.search(
        r'\b(?:application|apply|applying|documents?|eligibility|qualifies|permohonan|dokumen|kelayakan|syarat)\b', part, re.I)
        for part in plan.required_facts):
        return False
    requested = ' '.join((plan.topic, plan.original_question, *plan.required_facts))
    title = chunk.title or ''
    other_operations = title
    for pattern in _OPERATIONS:
        other_operations = re.sub(pattern, '', other_operations, flags=re.I)
    if (re.search(r'\b(?:applications?|apply|permohonan)\b', other_operations, re.I)
            and re.search(r'\b(?:and|dan)\b|[&/,]', title)):
        # Mixed guides need section-level ownership and semantic checking;
        # their title alone cannot exclude the first-application section.
        return False
    return any(re.search(pattern, title, re.I)
        and not re.search(pattern, requested, re.I) for pattern in _OPERATIONS)
