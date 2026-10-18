from dataclasses import replace
import json
from types import SimpleNamespace
from unittest.mock import patch
from app.llm import CoachRequestBudget
from app.llm_provider_session import ProviderSession
from app.rag import research_policy as policy
from scripts.assessment_binding_pilot import fixed_evidence


def test_groups_preserve_literal_ranges_categories_and_parent_conditions():
    from app.rag.evidence_groups import evidence_groups
    _, chunks = fixed_evidence()
    groups = evidence_groups(chunks)
    children = [g for g in groups if 'Anak Kandung' in g.audience_anchor]
    assert len(children) == 1
    child = children[0]
    assert 'Sijil Lahir' in child.content and 'Anak Angkat' not in child.content
    assert 'jika berkaitan' in child.condition_anchor
    assert child.relation == 'all' and child.requirement_kind == 'mandatory'
    assert not any('Anak Kandung' in item for item in child.alternatives)
    assert child.content == chunks[child.source_id-1].content[child.start:child.end]
    assert len({g.group_id for g in groups}) == len(groups)
    assert evidence_groups(chunks) == groups
    adopted = next(g for g in groups if 'Anak Angkat' in g.audience_anchor)
    assert 'muat naik' not in adopted.content
    submission = next(g for g in groups if 'muat naik' in g.content)
    assert 'Anak Angkat' not in submission.audience_anchor


def test_group_ids_resolve_locally_and_preserve_both_requested_parts():
    from app.rag.evidence_groups import evidence_groups
    plan, chunks = fixed_evidence()
    groups = evidence_groups(chunks)
    app_ids = [f'g{i}' for i,g in enumerate(groups,1) if g.source_id == 1]
    doc_ids = [f'g{i}' for i,g in enumerate(groups,1) if g.source_id == 2]
    raw = dict(status='sufficient', missing=[], conflicting=False,
        jurisdiction_matches=True, period_matches=True,
        support=[dict(group_id=f'g{i}') for i,g in enumerate(groups,1)],
        coverage=[dict(part_id='p1', status='confirmed', group_ids=app_ids, resolution='direct', complete=True),
                  dict(part_id='p2', status='confirmed', group_ids=doc_ids, resolution='direct', complete=True)])
    result = policy.assess_evidence(plan, chunks,
        generate=lambda *a, **kw: SimpleNamespace(content=json.dumps(raw)),
        budget=CoachRequestBudget.start(provider_session=ProviderSession()), reserve_after_seconds=0)
    assert result.failure is None and result.status == 'sufficient'
    assert all(p.complete for p in result.parts)
    assert len(result.fact_bindings) == len(groups)
    assert all(b.scope_known for b in result.fact_bindings)


def test_unknown_group_does_not_erase_independent_application_evidence():
    from app.rag.evidence_groups import evidence_groups
    plan, chunks = fixed_evidence()
    app = next(g for g in evidence_groups(chunks) if g.source_id == 1)
    unknown = 'g40'
    raw = dict(status='sufficient', missing=[], conflicting=False,
        jurisdiction_matches=True, period_matches=True,
        support=[dict(group_id='g1'), dict(group_id=unknown)],
        coverage=[dict(part_id='p1', status='confirmed', group_ids=['g1'], resolution='direct', complete=True),
                  dict(part_id='p2', status='confirmed', group_ids=[unknown], resolution='direct', complete=True)])
    result = policy.assess_evidence(plan, chunks,
        generate=lambda *a, **kw: SimpleNamespace(content=json.dumps(raw)),
        budget=CoachRequestBudget.start(provider_session=ProviderSession()), reserve_after_seconds=0)
    assert result.failure is None and result.status == 'partial'
    assert result.parts[0].complete and not result.parts[1].complete


def test_incomplete_unit_never_becomes_complete_through_group_selection():
    from app.rag.evidence_groups import evidence_groups
    _, chunks = fixed_evidence()
    span = replace(chunks[1].source_spans[0], complete=False)
    chunks[1] = replace(chunks[1], source_spans=(span,))
    assert all(not g.complete for g in evidence_groups(chunks) if g.source_id == 2)


def test_group_binding_cannot_borrow_a_different_child_category():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    _, chunks = fixed_evidence()
    child = next(g for g in evidence_groups(chunks) if 'Anak Kandung' in g.audience_anchor)
    binding = EvidenceFactBinding('b1', 1, child.source_span_id,
        audience_anchor='Anak Angkat', scope_known=True)
    assert validate_binding(binding, child.content, chunks[1], group=child) is None


def test_parent_condition_outside_parentheses_is_not_lost():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.retrieval import RetrievedChunk
    from app.rag.research_source_spans import read_source_spans
    page = 'Q: Documents? A: Only foreign spouses qualify. a. Spouses: Provide a passport. b. Children: Provide a certificate.'
    span, = read_source_spans(page, anchors=('passport',))
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, 0, span.content, .8, source_spans=(span,))
    groups = evidence_groups([chunk])
    assert groups and all('Only foreign spouses qualify' in g.condition_anchor for g in groups)


def test_heading_prefix_and_nested_alternative_preserve_required_documents():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.retrieval import RetrievedChunk
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, 0,
        'You must submit these documents. a. Spouses: • passport or identity card • marriage certificate.',
        .8, qualification_context='Required documents')
    group, = evidence_groups([chunk])
    assert group.relation == 'all'
    assert group.alternatives == ('passport or identity card', 'marriage certificate.')
    binding = EvidenceFactBinding('b1', 1, group.source_span_id,
        audience_anchor=group.audience_anchor, requirement_kind=group.requirement_kind,
        alternatives=group.alternatives, relation=group.relation, scope_known=group.complete)
    assert validate_binding(binding, group.content, chunk, group=group) is not None


def test_plain_source_without_qualification_context_can_be_grouped():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.retrieval import RetrievedChunk
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, 0, 'Submit an application online.', .8)
    group, = evidence_groups([chunk])
    assert group.content == chunk.content


def test_separate_literal_parent_conditions_remain_valid_constraints():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.retrieval import RetrievedChunk
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, 0,
        'If married, you must submit documents. a. Spouses: • passport • marriage certificate.',
        .8, qualification_context='Only Malaysian residents.')
    group, = evidence_groups([chunk])
    assert group.condition_anchor.splitlines() == ['Only Malaysian residents', 'If married, you must submit documents']
    binding = EvidenceFactBinding('b1', 1, group.source_span_id,
        audience_anchor=group.audience_anchor, condition_anchor=group.condition_anchor,
        requirement_kind=group.requirement_kind, alternatives=group.alternatives,
        relation=group.relation, scope_known=group.complete)
    assert validate_binding(binding, group.content, chunk, group=group).scope_known
def test_closed_atomic_paragraph_does_not_complete_parent_window():
    from app.rag.research_source_spans import SourceSpan
    from app.rag.retrieval import RetrievedChunk
    from app.rag.evidence_groups import evidence_groups
    text = 'Apply through the portal.\n\nRequired documents include'
    span = SourceSpan(text, 'hash', 0, len(text), '', 'owner', False)
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, None, text, .8,
        confidence='sufficient', source_spans=(span,))
    groups = evidence_groups([chunk])
    fact = next(g for g in groups if g.content == 'Apply through the portal.')
    assert fact.scope_known and not fact.complete
    assert not any(g.scope_known and 'documents include' in g.content for g in groups)


def test_submission_tail_does_not_inherit_document_list_if_applicable():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.retrieval import RetrievedChunk
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, 0,
        'Supporting documents (if applicable): a. Spouses: • Marriage certificate. '
        'Submit the supporting documents online.', .8,
        qualification_context='Only Malaysian residents.')
    groups = evidence_groups([chunk])
    category = next(g for g in groups if 'Spouses' in g.audience_anchor)
    tail = next(g for g in groups if g.content.startswith('Submit'))
    assert '(if applicable)' in category.condition_anchor
    assert '(if applicable)' not in tail.condition_anchor
    assert 'Only Malaysian residents' in tail.condition_anchor


def test_submission_tail_keeps_a_universal_condition_in_list_introduction():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.retrieval import RetrievedChunk
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, 0,
        'Only foreign spouses may submit these documents: a. Spouses: • Passport. '
        'Submit the supporting documents online.', .8)
    tail = next(g for g in evidence_groups([chunk]) if g.content.startswith('Submit'))
    assert 'Only foreign spouses' in tail.condition_anchor


def test_complete_owned_rule_keeps_its_inline_condition_for_semantic_verification():
    from app.rag.evidence_groups import evidence_groups
    from app.rag.retrieval import RetrievedChunk
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    text = 'Programme recipients verified in the eKasih database qualify for assistance.'
    chunk = RetrievedChunk(-1,'Eligibility','official',None,None,text,.8,confidence='established')
    group, = evidence_groups([chunk])
    binding = EvidenceFactBinding('b1',1,group.source_span_id,scope_known=group.scope_known)
    assert validate_binding(binding,group.content,chunk,group=group).scope_known
