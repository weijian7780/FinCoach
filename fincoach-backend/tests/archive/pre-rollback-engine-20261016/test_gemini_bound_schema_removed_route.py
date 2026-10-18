"""Archived reference: bound-schema Gemini compatibility test for the rolled-back engine.

Moved out of ``tests/test_research_recovery.py`` on 2026-10-16. The test imported
``_BoundEvidenceProposal`` and ``_FactBindingProposal`` from
``app.rag.research_policy``; both proposal types were removed with the larger
research engine, and the SDK boundary no longer rewrites a nested ``maxItems``
schema on the way to the provider.

Retained here only as a record of the removed contract. It is excluded from
collection (see ``tests/conftest.py``). Replacement coverage: the active
research policy uses the local applicability checks asserted in
``tests/test_research_applicability.py`` and the bounded writer budgets pinned in
``tests/test_research_answer.py``; live SDK-boundary behaviour is covered by
``tests/test_research_recovery.py`` (structured failover) and
``tests/test_llm_observability.py``.

# --- original test (verbatim, superseded) -------------------------------------
#
# def test_gemini_bound_schema_avoids_rejected_nested_limit_without_relaxing_local_checks():
#     from copy import deepcopy
#     from pydantic import ValidationError
#     from app import llm
#     from app.rag.research_policy import _BoundEvidenceProposal, _FactBindingProposal
#
#     schema = _BoundEvidenceProposal.model_json_schema()
#     original = deepcopy(schema)
#     expected = deepcopy(schema)
#     expected['$defs']['_FactBindingProposal']['properties']['alternatives'].pop('maxItems')
#     provider = SimpleNamespace(base_url='https://generativelanguage.googleapis.com/v1beta/openai/',
#         api_key='test', model='gemini-3.5-flash-lite', role='primary')
#     factory = MagicMock()
#     def sdk_completion(**request):
#         wire = request['response_format']['json_schema']['schema']
#         if 'maxItems' in wire['$defs']['_FactBindingProposal']['properties']['alternatives']:
#             raise ValueError('HTTP 400: nested alternatives bound')
#         return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{}'))], usage=None)
#     factory.return_value.chat.completions.create.side_effect = sdk_completion
#     llm._generate_with_provider(factory, provider, 'fixed public evidence', reasoning_effort='low',
#         timeout_seconds=15, structured=True, response_schema=schema, max_tokens=2200)
#     sent = factory.return_value.chat.completions.create.call_args.kwargs
#     assert sent['response_format']['json_schema']['schema'] == expected
#     assert schema == original
#     assert factory.return_value.chat.completions.create.call_count == 1
#     assert factory.call_args.kwargs['max_retries'] == 0
#     row = dict(binding_id='b1', quote_index=1, source_span_id='a'*64,
#         requirement_kind='informational', alternatives=['literal anchor']*7,
#         relation='all', jurisdiction='Malaysia', scope_known=True)
#     with pytest.raises(ValidationError) as failure:
#         _FactBindingProposal.model_validate(row)
#     assert any(e['loc'] == ('alternatives',) and e['type'] == 'too_long'
#                for e in failure.value.errors())
