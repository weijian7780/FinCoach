import json
from types import SimpleNamespace as NS
from unittest.mock import patch
from app.rag.verifier import verify_grounding_claims, ResearchVerificationContext
from app.rag.grounding import GroundingClaim


def verify(item, source='For foreign spouses: provide a passport copy.', claim='Every spouse needs a passport copy.', bindings=()):
    payload = dict(claims=[dict(id=1, verdict='supported', source_index=1, **item)],
                   quality_errors=[], requested_scope_covered=True, unanswered_requested_parts=[])
    response = NS(choices=[NS(message=NS(content=json.dumps(payload)), finish_reason='stop')], usage=None)
    client = NS(chat=NS(completions=NS(create=lambda **_: response)))
    with patch('app.rag.verifier._create_verifier_client', return_value=client):
        return verify_grounding_claims([GroundingClaim(1, claim, (1,))], [source], timeout_seconds=5,
            research_context=ResearchVerificationContext('Documents?', claim, (), fact_bindings=bindings,
                claim_bindings=((1, tuple(b.binding_id for b in bindings)),) if bindings else ()))


def test_broadened_requirement_is_misapplied():
    result = verify(dict(scope_relation='broadened', source_qualifier='foreign spouses',
                         qualifier_source_index=1, claim_qualifier='Every spouse'))
    assert result.verdicts[1] == 'misapplied' and 1 not in result.source_indices


def test_missing_scope_and_fabricated_anchor_never_approve():
    assert verify({}).verdicts[1] == 'unsupported'
    assert verify(dict(scope_relation='preserved', source_qualifier='citizen spouses',
                       qualifier_source_index=1, claim_qualifier='Every spouse')).verdicts[1] == 'unsupported'


def test_faithful_translation_and_extra_fields_are_accepted():
    result = verify(dict(scope_relation='preserved', source_qualifier='pasangan asing',
        qualifier_source_index=1, claim_qualifier='foreign spouses', irrelevant='ignored'),
        source='Untuk pasangan asing: salinan pasport.', claim='For foreign spouses, provide a passport copy.')
    assert result.verdicts[1] == 'supported'


def test_unrelated_category_in_source_does_not_demote_plain_fact():
    result = verify(dict(scope_relation='preserved'),
        source='SARA credit is available on eligible recipients’ MyKad. For foreign spouses: passport copies are required.',
        claim='SARA credit is available on eligible recipients’ MyKad.')
    assert result.verdicts[1] == 'supported'


def test_formatting_only_anchors_cannot_prove_scope():
    assert verify(dict(scope_relation='preserved', source_qualifier='**',
                       qualifier_source_index=1, claim_qualifier='**')).verdicts[1]=='unsupported'


def test_sentence_selects_only_its_owned_binding_from_part_union():
    from app.rag.research_fact_bindings import EvidenceFactBinding
    bindings = (EvidenceFactBinding('b1', 1, 's1', audience_anchor='Foreign spouses', scope_known=True),
                EvidenceFactBinding('b2', 2, 's2', audience_anchor='Adopted children', scope_known=True))
    item = dict(scope_relation='preserved', source_qualifier='Foreign spouses',
        qualifier_source_index=1, claim_qualifier='foreign spouses', supporting_binding_ids=['b1'])
    assert verify(item, 'Foreign spouses: passport. Adopted children: adoption certificate.',
        'For foreign spouses, provide a passport.', bindings).verdicts[1] == 'supported'
    item['supporting_binding_ids'] = ['invented']
    result = verify(item, bindings=bindings)
    assert result.error_code == 'invalid_verifier_response'


def test_invalid_checker_anchor_is_rechecked_without_rewriting_valid_draft():
    from unittest.mock import Mock
    from app.rag.research_fact_bindings import EvidenceFactBinding
    binding = EvidenceFactBinding('b1', 1, 'owned', scope_known=True)
    claim = GroundingClaim(1, 'Apply online or collect the paper form.', (1,))
    context = ResearchVerificationContext('How to apply?', claim.text, (),
        fact_bindings=(binding,), claim_bindings=((1, ('b1',)),))
    base = dict(id=1, verdict='supported', source_index=1,
        scope_relation='preserved', supporting_binding_ids=['b1'])
    responses = [dict(base, source_qualifier='Apply online; collect the paper form',
        qualifier_source_index=1, claim_qualifier=claim.text), base]
    def response(item):
        payload = dict(claims=[item], quality_errors=[], requested_scope_covered=True,
            unanswered_requested_parts=[])
        return NS(choices=[NS(message=NS(content=json.dumps(payload)), finish_reason='stop')], usage=None)
    create = Mock(side_effect=[response(item) for item in responses])
    client = NS(chat=NS(completions=NS(create=create)))
    with patch('app.rag.verifier._create_verifier_client', return_value=client):
        result = verify_grounding_claims([claim], ['Apply online. Alternatively, collect the paper form.'],
            timeout_seconds=8, research_context=context)
    assert result.verdicts[1] == 'supported'
    assert create.call_count == 2
    assert 'literal' in create.call_args.kwargs['messages'][1]['content'].lower()


def test_checker_repair_cannot_promote_a_separate_misapplied_claim():
    from unittest.mock import Mock
    from app.rag.research_fact_bindings import EvidenceFactBinding
    bindings = (EvidenceFactBinding('b1', 1, 'owned', scope_known=True),)
    claims = [GroundingClaim(1, 'Apply online.', (1,)),
        GroundingClaim(2, 'Everyone must provide a passport.', (1,))]
    context = ResearchVerificationContext('How to apply?', '', (), fact_bindings=bindings,
        claim_bindings=((1, ('b1',)), (2, ('b1',))))
    initial = [dict(id=1, verdict='supported', source_index=1, scope_relation='preserved',
        source_qualifier='invented anchor', qualifier_source_index=1,
        claim_qualifier='Apply online', supporting_binding_ids=['b1']),
        dict(id=2, verdict='misapplied', source_index=None, scope_relation='broadened')]
    repair = [dict(id=i, verdict='supported', source_index=1, scope_relation='preserved',
        supporting_binding_ids=['b1']) for i in (1,2)]
    def response(items):
        payload = dict(claims=items, quality_errors=[], requested_scope_covered=True,
            unanswered_requested_parts=[])
        return NS(choices=[NS(message=NS(content=json.dumps(payload)), finish_reason='stop')], usage=None)
    create = Mock(side_effect=[response(initial), response(repair)])
    with patch('app.rag.verifier._create_verifier_client',
        return_value=NS(chat=NS(completions=NS(create=create)))):
        result = verify_grounding_claims(claims, ['Apply online. Foreign spouses need passports.'],
            timeout_seconds=8, research_context=context)
    assert create.call_count == 2
    assert result.verdicts == {1:'unsupported', 2:'misapplied'}


def test_failed_checker_repair_is_once_with_shared_timeout_and_billed_usage():
    from unittest.mock import Mock
    from app.rag.research_fact_bindings import EvidenceFactBinding
    binding = EvidenceFactBinding('b1', 1, 'owned', scope_known=True)
    claim = GroundingClaim(1, 'Apply online.', (1,))
    context = ResearchVerificationContext('How?', '', (), fact_bindings=(binding,),
        claim_bindings=((1, ('b1',)),))
    payload = dict(claims=[dict(id=1, verdict='supported', source_index=1,
        scope_relation='preserved', source_qualifier='invented anchor',
        qualifier_source_index=1, claim_qualifier='Apply online', supporting_binding_ids=['b1'])],
        quality_errors=[], requested_scope_covered=True, unanswered_requested_parts=[])
    clock = [0.0]
    def create_response(**kwargs):
        clock[0] += 2
        return NS(choices=[NS(message=NS(content=json.dumps(payload)), finish_reason='stop')],
            usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15))
    create = Mock(side_effect=create_response)
    client = NS(chat=NS(completions=NS(create=create)))
    with patch('app.rag.verifier.monotonic', side_effect=lambda:clock[0]), \
        patch('app.rag.verifier._create_verifier_client', return_value=client) as factory:
        result = verify_grounding_claims([claim], ['Apply online.'],
            timeout_seconds=8, research_context=context)
    assert [c.kwargs['timeout_seconds'] for c in factory.call_args_list] == [8,6]
    assert create.call_count == 2 and result.verdicts[1] == 'unsupported'
    assert result.prompt_tokens == 20 and result.completion_tokens == 10
