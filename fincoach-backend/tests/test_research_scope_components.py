from app.rag.grounding import GroundingClaim
from app.rag.research_fact_bindings import EvidenceFactBinding
from app.rag.research_scope import scope_verdict


def test_composite_category_uses_literal_owned_components():
    binding = EvidenceFactBinding('b1', 1, 'owned', audience_anchor='c. Anak:\ni. Anak Kandung', scope_known=True)
    claim = GroundingClaim(1, 'For biological children, provide identification.', (1,))
    item = dict(scope_relation='preserved', source_qualifier='i. Anak Kandung',
                qualifier_source_index=1, claim_qualifier='biological children')
    assert scope_verdict(item, claim, ['c. Anak:\ni. Anak Kandung: identification.'], bindings=(binding,)) == 'supported'


def test_checker_joined_hierarchy_resolves_only_owned_component_spans():
    binding = EvidenceFactBinding('b1', 1, 'owned', audience_anchor='c. Anak:\nii. Anak Angkat', scope_known=True)
    claim = GroundingClaim(1, 'For adopted children, provide identification.', (1,))
    item = dict(scope_relation='preserved', source_qualifier='ii. Anak Angkat',
        qualifier_source_index=1, claim_qualifier='adopted children',
        qualifier_anchors=[dict(source_index=1, source='c. Anak:\nii. Anak Angkat', claim='adopted children')])
    reference = ['c. Anak: i. Anak Kandung: birth certificate; ii. Anak Angkat: identification.']
    assert scope_verdict(item, claim, reference, bindings=(binding,)) == 'supported'
    item['qualifier_anchors'][0]['source'] = 'c. Anak:\nforeign spouses'
    assert scope_verdict(item, claim, reference, bindings=(binding,)) == 'unsupported'


def test_multiple_conditions_require_each_literal_anchor():
    binding = EvidenceFactBinding('b1', 1, 'owned', condition_anchor='If married\nIf foreign', scope_known=True)
    claim = GroundingClaim(1, 'If married and foreign, provide a passport.', (1,))
    item = dict(scope_relation='preserved', source_qualifier='If married',
                qualifier_source_index=1, claim_qualifier='If married')
    refs = ['If married\nIf foreign: provide a passport.']
    assert scope_verdict(item, claim, refs, bindings=(binding,)) == 'unsupported'
    item['qualifier_anchors'] = [
        dict(source_index=1, source='If married', claim='If married'),
        dict(source_index=1, source='If foreign', claim='foreign'),
    ]
    assert scope_verdict(item, claim, refs, bindings=(binding,)) == 'supported'
    item['qualifier_anchors'][1]['claim'] = 'everyone'
    assert scope_verdict(item, claim, refs, bindings=(binding,)) == 'unsupported'


def test_session_correction_uses_provider_health_instead_of_forcing_fallback():
    from types import SimpleNamespace
    from unittest.mock import patch
    from app.rag.research_answer import _generate_research_correction
    budget = SimpleNamespace(provider_session=object())
    with patch('app.llm.generate_result', return_value='generated') as generate, \
         patch('app.rag.research_answer.generate_fallback_result') as fallback:
        assert _generate_research_correction('rewrite', budget=budget, system_prompt='Explain') == 'generated'
    assert generate.call_args.kwargs['budget'] is budget
    assert fallback.call_count == 0
