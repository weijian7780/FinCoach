import json


def test_one_requested_part_can_explain_facts_and_actions_in_distinct_sections():
    from app.rag.research_blocks import parse_finished_blocks, part_unit_keys, unit_binding_ids
    payload = '\n'.join(json.dumps(record) for record in [
        dict(part_id='p2', section='Insight', text='Provide identification [S1].', binding_ids=['b1']),
        dict(part_id='p2', section='Recommended action', text='Upload documents online [S1].', binding_ids=['b2'])])
    blocks = parse_finished_blocks(payload, allowed_part_ids=('p2',),
        allowed_binding_ids=('b1','b2'), require_bindings=True, allowed_source_ids=(1,))
    assert len(blocks) == 2
    assert len(part_unit_keys(blocks)['p2']) == 2
    assert set(unit_binding_ids(blocks).values()) == {('b1',),('b2',)}
import pytest
from app.rag.research_blocks import parse_finished_blocks, render_blocks


def record(part='p1', text='Apply through the official portal [S1].'):
    return json.dumps(dict(part_id=part, section='Recommended action', text=text))


def test_complete_record_survives_incomplete_final_record():
    blocks = parse_finished_blocks(record()+'\n{"part_id":"p2","text":"and', allowed_part_ids=('p1','p2'))
    assert len(blocks)==1 and blocks[0].part_id=='p1'
    assert 'and' not in render_blocks(blocks)


def test_duplicate_unknown_ids_and_extra_fields_are_rejected():
    for text in (record()+'\n'+record(), record('p9'), record().replace('"part_id"', '"invented"')):
        with pytest.raises(ValueError):
            parse_finished_blocks(text, allowed_part_ids=('p1','p2'))


def test_distinct_records_for_same_part_preserve_each_fact_and_binding():
    from app.rag.research_blocks import part_unit_keys, unit_binding_ids
    payload = '\n'.join(json.dumps(dict(part_id='p2', section='Recommended action',
        text=text, binding_ids=[binding])) for text, binding in (
        ('For spouses, provide a marriage certificate [S1].', 'b1'),
        ('For adopted children, provide an adoption certificate [S1].', 'b2')))
    blocks = parse_finished_blocks(payload, allowed_part_ids=('p2',),
        allowed_binding_ids=('b1','b2'), require_bindings=True)
    keys = part_unit_keys(blocks)['p2']
    assert len(keys) == 2
    assert unit_binding_ids(blocks)[keys[0]] == ('b1',)
    assert unit_binding_ids(blocks)[keys[1]] == ('b2',)


def test_overlapping_sentence_records_cannot_overwrite_fact_bindings():
    first = dict(part_id='p1', section='Recommended action',
        text='Apply online [S1].', binding_ids=['b1'])
    second = dict(first, text='Apply online [S1]. Collect a paper form [S1].', binding_ids=['b2'])
    with pytest.raises(ValueError):
        parse_finished_blocks(json.dumps(first)+'\n'+json.dumps(second),
            allowed_part_ids=('p1',), allowed_binding_ids=('b1','b2'))


def test_word_bound_and_dangling_phrase_are_not_displayable():
    with pytest.raises(ValueError):
        parse_finished_blocks(record(text=' '.join(['word']*201)), allowed_part_ids=('p1',))
    assert not parse_finished_blocks(record(text='Provide a copy of spouse’s [S1].'), allowed_part_ids=('p1',))


def test_list_category_survives_rendering_as_shared_verification_group():
    from app.rag.research_answer import _body_units
    blocks = parse_finished_blocks(record(text='For adopted children:\n- Adoption certificate [S1].\n- MyKid copy [S1].'), allowed_part_ids=('p1',))
    units = _body_units(render_blocks(blocks))
    assert len({u[2] for u in units}) == 1


def test_invalid_field_types_fail_closed():
    with pytest.raises(ValueError):
        parse_finished_blocks('{"part_id":"p1","section":[],"text":"Apply [S1]."}', allowed_part_ids=('p1',))


def test_complete_gap_record_survives_until_semantic_check():
    text = 'The sources do not confirm the document list.'
    blocks = parse_finished_blocks(record(text=text), allowed_part_ids=('p1',))
    assert len(blocks) == 1
    assert text in render_blocks(blocks)


def test_correction_retains_completed_parts_without_duplicate_partial_target():
    from app.rag.research_answer import _retained_completed_parts
    from app.rag.research_blocks import part_unit_keys
    blocks = parse_finished_blocks(record()+'\n'+record('p2', 'Provide identification [S1].'), allowed_part_ids=('p1','p2'))
    retained = _retained_completed_parts(render_blocks(blocks), part_unit_keys(blocks), {'p1'})
    assert 'Apply through' in retained
    assert 'Provide identification' not in retained


def test_numeric_citation_format_resolves_only_approved_source_ids():
    blocks = parse_finished_blocks(record(text='Apply through the portal [1].'),
        allowed_part_ids=('p1',), allowed_source_ids=(1,))
    assert blocks[0].text == 'Apply through the portal [S1].'
    assert not parse_finished_blocks(record(text='Apply through the portal [9].'),
        allowed_part_ids=('p1',), allowed_source_ids=(1,))


def test_rejected_optional_sentence_does_not_erase_verified_requested_coverage():
    from unittest.mock import patch
    from dataclasses import replace
    from app.llm import CoachRequestBudget
    from app.rag.research_answer import check_research_draft
    from app.rag.research_blocks import part_unit_keys
    from app.rag.verifier import GroundingVerification
    from app.rag.research_coverage import PartCoverage
    from tests.test_research_answer import decision
    blocks = parse_finished_blocks(record()+'\n'+record('p2',
        'Provide identification [S1]. Upload the unrelated form online [S1].'), allowed_part_ids=('p1','p2'))
    evidence = decision()
    evidence = replace(evidence, assessment=replace(evidence.assessment,
        parts=(PartCoverage('p1','confirmed',(1,),complete=True), PartCoverage('p2','confirmed',(1,),complete=True))))
    def verdict(claims, *_a, **_kw):
        return GroundingVerification({1:'supported',2:'supported',3:'unsupported'}, {1:1,2:1},
            requested_scope_covered=True, answered_part_ids=('p1','p2'),
            answered_part_claims=(('p1',(1,)),('p2',(2,))))
    with patch('app.rag.research_answer.verify_grounding_claims', side_effect=verdict):
        checked = check_research_draft(render_blocks(blocks), public_question='Apply and documents?',
            decision=evidence, budget=CoachRequestBudget.start(), part_units=part_unit_keys(blocks))
    assert checked.is_valid and 'unrelated' not in checked.approved_text
    assert checked.diagnostics['answered_part_ids'] == ['p1','p2']


def test_rejected_second_part_cannot_erase_first_verified_part():
    from unittest.mock import patch
    from app.llm import CoachRequestBudget
    from app.rag.research_answer import check_research_draft
    from app.rag.verifier import GroundingVerification
    from tests.test_research_answer import decision
    blocks = parse_finished_blocks(json.dumps(dict(part_id='p1', section='Insight', text='Apply online through the portal [S1].'))+'\n'+
        json.dumps(dict(part_id='p2', section='Insight', text='For married applicants:\n- An adoption certificate is required [S1].')),
        allowed_part_ids=('p1','p2'))
    def verdict(claims, *_a, **_kw):
        return GroundingVerification({c.id: 'unsupported' if 'adoption' in c.text else 'supported' for c in claims},
            {c.id: 1 for c in claims if 'adoption' not in c.text})
    with patch('app.rag.research_answer.verify_grounding_claims', side_effect=verdict):
        checked = check_research_draft(render_blocks(blocks), public_question='Apply?', decision=decision(), budget=CoachRequestBudget.start())
    assert 'Apply online through the portal' in (checked.approved_text or '')
    assert 'adoption' not in checked.approved_text


def test_rejection_preserves_verified_part_id_for_targeted_correction():
    from unittest.mock import patch
    from dataclasses import replace
    from app.llm import CoachRequestBudget
    from app.rag.research_answer import check_research_draft
    from app.rag.research_blocks import part_unit_keys
    from app.rag.verifier import GroundingVerification
    from app.rag.research_coverage import PartCoverage
    from tests.test_research_answer import decision
    blocks = parse_finished_blocks(record()+'\n'+record('p2', 'Everyone must provide an adoption certificate [S1].'), allowed_part_ids=('p1','p2'))
    evidence = decision()
    evidence = replace(evidence, assessment=replace(evidence.assessment, parts=(PartCoverage('p1','confirmed',(1,),complete=True), PartCoverage('p2','confirmed',(1,),complete=True))))
    def verdict(claims, *_a, **_kw):
        return GroundingVerification({c.id:'unsupported' if 'adoption' in c.text else 'supported' for c in claims},
            {c.id:1 for c in claims if 'adoption' not in c.text}, answered_part_ids=('p1','p2'))
    with patch('app.rag.research_answer.verify_grounding_claims', side_effect=verdict):
        checked = check_research_draft(render_blocks(blocks), public_question='Apply?', decision=evidence,
            budget=CoachRequestBudget.start(), part_units=part_unit_keys(blocks))
    assert checked.diagnostics['approved_part_ids']==['p1']
    assert checked.diagnostics['answered_part_ids']==['p1']
