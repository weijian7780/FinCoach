from dataclasses import replace
import pytest
from app.rag.retrieval import RetrievedChunk
from app.rag.research_source_spans import read_source_spans


def fixture(page, anchor):
    span, = read_source_spans(page, anchors=(anchor,))
    chunk = RetrievedChunk(-1, 'Guidance', 'official', None, None, span.content, .8,
        source_spans=(span,), qualification_context=span.heading_context)
    return span, chunk


def test_literal_audience_belongs_to_the_selected_source_unit():
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    span, chunk = fixture('# Foreign spouses\nProvide a passport or visa.\n\n# Children\nProvide a birth certificate.', 'passport')
    binding = EvidenceFactBinding('b1', 1, span.unit_id, audience_anchor='Foreign spouses',
        alternatives=('passport', 'visa'), relation='any', scope_known=True)
    assert validate_binding(binding, 'Provide a passport or visa.', chunk) == binding
    assert validate_binding(replace(binding, audience_anchor='Children'), 'Provide a passport or visa.', chunk) is None
    assert validate_binding(replace(binding, relation='all'), 'Provide a passport or visa.', chunk) is None


def test_unknown_or_incomplete_scope_cannot_authorize_universal_requirements():
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    span, chunk = fixture('# Adopted children\nProvide an adoption certificate.', 'adoption')
    binding = EvidenceFactBinding('b1', 1, span.unit_id, scope_known=True)
    checked = validate_binding(binding, 'Provide an adoption certificate.', chunk)
    assert checked is not None and not checked.scope_known


def test_optional_document_cannot_be_bound_as_mandatory():
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    span, chunk = fixture('You may attach supporting documents if applicable.', 'attach')
    binding = EvidenceFactBinding('b1', 1, span.unit_id, requirement_kind='mandatory',
        condition_anchor='if applicable', scope_known=True)
    assert validate_binding(binding, chunk.content, chunk) is None


def test_quote_positions_resolve_their_own_sources_not_the_first_span():
    from types import SimpleNamespace
    from app.rag.research_policy import _FactBindingProposal, _validated_fact_bindings
    first_span, first = fixture('# Application\nApply through the portal.', 'Apply')
    second_span, second = fixture('# Married applicants\nProvide a marriage certificate.', 'Provide')
    rows = [_FactBindingProposal(binding_id='b1', quote_index=1,
        source_span_id=first_span.unit_id),
        _FactBindingProposal(binding_id='b2', quote_index=2,
        source_span_id=second_span.unit_id, audience_anchor='Married applicants')]
    result = _validated_fact_bindings(SimpleNamespace(fact_bindings=rows), [first, second],
        ((1, 'Apply through the portal.'), (2, 'Provide a marriage certificate.')))
    assert [binding.binding_id for binding in result] == ['b1', 'b2']


def test_two_quote_positions_can_share_one_source_without_overwriting():
    from types import SimpleNamespace
    from app.rag.research_policy import _FactBindingProposal, _validated_fact_bindings
    span, chunk = fixture('Apply through the portal. Submit the form.', 'Apply')
    rows = [_FactBindingProposal(binding_id=f'b{i}', quote_index=i,
        source_span_id=span.unit_id) for i in (1, 2)]
    result = _validated_fact_bindings(SimpleNamespace(fact_bindings=rows), [chunk],
        ((1, 'Apply through the portal.'), (1, 'Submit the form.')))
    assert [binding.binding_id for binding in result] == ['b1', 'b2']


def test_malay_scope_is_kept_literal_for_later_translation_checks():
    from app.rag.research_fact_bindings import EvidenceFactBinding, validate_binding
    span, chunk = fixture('# Anak angkat\nSalinan sijil pengangkatan diperlukan.', 'sijil')
    binding = EvidenceFactBinding('b1', 1, span.unit_id, audience_anchor='Anak angkat', scope_known=True)
    assert validate_binding(binding, 'Salinan sijil pengangkatan diperlukan.', chunk) == binding


def test_invalid_writer_binding_does_not_erase_an_independent_finished_part():
    import json
    from app.rag.research_blocks import parse_finished_blocks
    records = '\n'.join(json.dumps(r) for r in [
        dict(part_id='p1', section='Recommended action', text='Apply through the portal [S1].', binding_ids=['b1']),
        dict(part_id='p2', section='Insight', text='Provide a passport [S1].', binding_ids=['b9'])])
    blocks = parse_finished_blocks(records, allowed_part_ids=('p1', 'p2'), allowed_binding_ids=('b1',), require_bindings=True)
    assert [b.part_id for b in blocks] == ['p1'] and blocks[0].binding_ids == ('b1',)


def test_source_only_condition_requires_verifier_scope_anchors():
    from app.rag.research_fact_bindings import EvidenceFactBinding
    from app.rag.research_scope import scope_verdict
    from app.rag.grounding import GroundingClaim
    binding = EvidenceFactBinding('b1', 1, 'a' * 64, audience_anchor='Foreign spouses', scope_known=True)
    claim = GroundingClaim(1, 'Spouses must provide a passport.', (1,))
    item = dict(scope_relation='preserved')
    assert scope_verdict(item, claim, ['Foreign spouses must provide a passport.'], bindings=(binding,)) == 'unsupported'
    item['scope_relation'] = 'broadened'
    assert scope_verdict(item, claim, ['Foreign spouses must provide a passport.'], bindings=(binding,)) == 'misapplied'


def test_unknown_binding_scope_rejects_requirement_without_keyword_matching():
    from app.rag.research_fact_bindings import EvidenceFactBinding
    from app.rag.research_scope import scope_verdict
    from app.rag.grounding import GroundingClaim
    binding = EvidenceFactBinding('b1', 1, 'a' * 64, requirement_kind='mandatory', scope_known=False)
    for text in ('Submit a passport.', 'Hantar pasport.', '提交护照。'):
        claim = GroundingClaim(1, text, (1,))
        assert scope_verdict({'scope_relation': 'preserved'}, claim,
            ['A passport is required if applicable.'], bindings=(binding,)) == 'unsupported'


@pytest.mark.parametrize('keep_document_neighbor', [False, True])
@pytest.mark.parametrize('omit_document_coverage', [False, True])
def test_one_malformed_binding_keeps_independent_approved_application_part(keep_document_neighbor, omit_document_coverage):
    import json
    from types import SimpleNamespace
    from app.llm import CoachRequestBudget
    from app.llm_provider_session import ProviderSession
    from app.rag import research_policy as policy
    first_span, first = fixture('# Application\nApply through the official portal.', 'Apply')
    second_span, second = fixture('# Married applicants\nProvide a marriage certificate.', 'Provide')
    chunks = [replace(c, source_type='web', url='https://bantuantunai.hasil.gov.my/guide',
        title='STR 2026 guidance', tier=1, confidence='sufficient') for c in (first, second)]
    def row(binding_id, quote_index, span, **extra):
        return dict(binding_id=binding_id, quote_index=quote_index, source_span_id=span.unit_id,
            requirement_kind='informational', relation='single', jurisdiction='Malaysia',
            period='2026', scope_known=True, **extra)
    bindings = [row('b1', 1, first_span),
        row('b2', 2, second_span, audience_anchor='Married applicants', condition_anchor='x'*161)]
    if keep_document_neighbor:
        bindings.append(row('b3', 2, second_span, audience_anchor='Married applicants'))
    raw = dict(status='sufficient', missing=[], conflicting=False,
        jurisdiction_matches=True, period_matches=True,
        support=[dict(source_id=1, quote='Apply through the official portal.'),
                 dict(source_id=2, quote='Provide a marriage certificate.')],
        coverage=[dict(part_id=f'p{i}', status='confirmed', support_indices=[i],
            resolution='direct', complete=True) for i in (1, 2)], fact_bindings=bindings)
    if omit_document_coverage:
        raw['coverage'] = raw['coverage'][:1]
    plan = policy.QuestionPlan('STR', False, True, 'current', period='2026',
        entities=('STR',), required_facts=('application', 'documents'), part_tracking=True)
    result = policy.assess_evidence(plan, chunks,
        generate=lambda *a, **k: SimpleNamespace(content=json.dumps(raw)),
        budget=CoachRequestBudget.start(provider_session=ProviderSession()), reserve_after_seconds=0)
    assert result.failure is None and result.status == 'partial'
    assert result.parts[0].complete and not result.parts[1].complete
    assert 'b1' in {b.binding_id for b in result.fact_bindings}
    assert 'b2' not in {b.binding_id for b in result.fact_bindings}
