"""Mixed public intent must keep useful research separate from clarification."""
from dataclasses import replace
from types import SimpleNamespace
import json
import pytest
from app.rag import research_policy as policy, research_coverage as coverage


def proposal(**changes):
    value = dict(topic='ICU JPM duties and application', needs_personal=False,
        needs_external=True, time_scope='stable', entities=['ICU JPM'],
        required_facts=['main duties of ICU JPM', 'application procedure'],
        clarification='Which programme do you want to apply for?',
        clarification_facts=['application procedure'])
    return dict(value, **changes)


def interpret(value, question='confirm the duties or application now for ICU, JPM'):
    return policy.interpret_question(question, [], base_personal=False, base_external=True,
        generate=lambda *a, **k: SimpleNamespace(content=json.dumps(value)))


def test_mixed_clarification_researches_clear_part():
    plan = interpret(proposal())
    assert plan.interpreted
    assert not coverage.requires_full_clarification(plan)
    assert [(p.id, p.label) for p in coverage.researchable_parts(plan)] == [('p1', 'main duties of ICU JPM')]
    assert len(coverage.requested_parts(plan)) == 2


def test_duties_and_application_keep_both_parts():
    plan = interpret(proposal(), 'what are the duties of ICU JPM and how do I apply?')
    assert plan.required_facts == ('main duties of ICU JPM', 'application procedure')
    assert plan.clarification_facts == ('application procedure',)


def test_unknown_clarification_fact_rejected():
    assert not interpret(proposal(clarification_facts=['unknown programme'])).interpreted


def test_full_ambiguity_asks_once_without_research():
    plan = interpret(proposal(required_facts=['application procedure']))
    assert coverage.requires_full_clarification(plan)
    assert not coverage.researchable_parts(plan)


def test_old_plan_retains_full_clarification():
    plan = policy.QuestionPlan('agency', False, True, 'stable', clarification='Which programme?')
    assert coverage.requires_full_clarification(plan)


def test_explicit_programme_survives_role_scope_guard():
    plan = interpret(proposal(entities=['ICU JPM','SejaTi MADANI'], clarification=None,
        clarification_facts=[]), 'what are ICU JPM duties for SejaTi MADANI and how do I apply?')
    assert 'SejaTi MADANI' in plan.entities
    assert 'application procedure' in plan.required_facts


def test_new_subject_does_not_inherit_old_programme():
    plan = interpret(proposal(entities=['ICU JPM', 'STR'], clarification=None,
        clarification_facts=[]), 'what are the duties of ICU JPM?')
    assert plan.entities == ('ICU JPM',)


def test_roles_and_application_are_not_reclassified_as_definition():
    plan = interpret(proposal(), 'what is ICU JPM and how do I apply?')
    assert not plan.definitional
    assert len(plan.required_facts) == 2


def test_ids_survive_filtering_first_part():
    plan = interpret(proposal(clarification_facts=['main duties of ICU JPM']))
    assert coverage.researchable_parts(plan)[0].id == 'p2'


def test_agency_application_without_programme_requires_targeted_question():
    plan=interpret(proposal(subject_kind='agency',application_subject=None,
        clarification=None,clarification_facts=[]))
    assert plan.interpreted
    assert plan.clarification_facts==('application procedure',)
    assert plan.clarification and '?' in plan.clarification
    assert [part.id for part in coverage.researchable_parts(plan)]==['p1']


def test_explicit_agency_service_does_not_force_programme_clarification():
    plan=interpret(proposal(subject_kind='agency',application_subject='SejaTi MADANI',
        clarification=None,clarification_facts=[]), 'duties of ICU JPM and apply for SejaTi MADANI')
    assert plan.interpreted and not plan.clarification


def test_search_keeps_original_institution_acronym():
    plan=interpret(proposal(entities=['Implementation Coordination Unit'],
        clarification=None,clarification_facts=[]), 'what is ICU JPM do for?')
    assert 'ICU' in policy.research_query(plan)
    assert plan.required_facts==('main role and functions of the institution',)


def test_clarification_labels_use_same_sanitization_as_part_ids():
    plan=policy.QuestionPlan('agency',False,True,'stable',
        required_facts=('duties','application for account 1234567890'),
        clarification='Which programme?',clarification_facts=('application for account 1234567890',))
    assert [part.id for part in coverage.researchable_parts(plan)]==['p1']


def test_prior_explicit_selection_resolves_it_follow_up():
    history=[{'role':'assistant','content':'', 'ui_payload':{'research_context':
        {'topic':'SejaTi MADANI','entities':['ICU JPM','SejaTi MADANI'],
         'application_subject':'SejaTi MADANI','subject_kind':'programme'}}}]
    value=proposal(subject_kind='agency',application_subject='SejaTi MADANI',
        required_facts=['application procedure'],clarification=None,clarification_facts=[])
    plan=policy.interpret_question('How do I apply for it?',history,base_personal=False,base_external=True,
        generate=lambda *a,**k:SimpleNamespace(content=json.dumps(value)))
    assert plan.application_subject=='SejaTi MADANI' and not plan.clarification
