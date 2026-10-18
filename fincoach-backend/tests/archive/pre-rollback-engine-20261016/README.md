# Archived tests — rolled-back research engine (2026-10-16)

These test files were moved out of the maintained suite during the coach
stabilization work (Stage 1). They targeted the **larger research engine that was
deliberately rolled back**: the span/group/block/batch model built on
`RetrievedChunk.source_spans`, `qualification_context`, per-part record blocks
and parallel gap batches. That model is gone from the live coaching entrypoints,
so the files failed at import or on removed attributes. They are kept here as a
record of the removed contracts and are excluded from collection by
`collect_ignore_glob` in `tests/conftest.py`.

Nothing in this directory is expected to pass. Do not re-enable it without first
restoring the engine it tests — the stabilization spec forbids that.

## Files moved whole

| Archived file | Tests | Superseded target | Why it cannot run | Replacement coverage on current entrypoints |
| --- | --- | --- | --- | --- |
| `test_evidence_groups.py` | 13 | `app/rag/evidence_groups.py`, `RetrievedChunk.source_spans` / `qualification_context` | fields removed from the live chunk model; module has no live importer | `tests/test_research_applicability.py` (misapplied / scope relation), `tests/test_research_scope_components.py` (deterministic scope verdicts), `tests/test_research_answer.py` (qualification-safe handover and adopted-child scope) |
| `test_research_blocks.py` | 14 | `app/rag/research_blocks.py` record engine, `research_answer.safe_draft_units` | `safe_draft_units` removed | `tests/test_research_answer.py` (verified parts survive rejection/timeout; no quote substitution), `tests/test_open_question_reliability.py`, `tests/test_research_definition_recovery.py` (partial retains verified part) |
| `test_research_fact_bindings.py` | 11 | `app/rag/research_fact_bindings.py` span bindings | module has no live importer; span model removed | `tests/test_research_applicability.py` (per-claim binding union, misapplied, checker repair), `tests/test_research_scope_components.py` |
| `test_llm_provider_session.py` | 11 (5 failing) | `app/llm_provider_session.py` + rolled-back `CoachRequestBudget.start(provider_session=...)` / `_generate_with_provider(provider_session=...)` wiring | module has no live importer; SDK-boundary attempt ceilings were rolled back | `tests/test_research_answer.py::test_recovery_semantic_calls_share_request_start_and_caps`, `tests/test_research_recovery.py` (structured failover, one call timeout), `tests/test_llm_observability.py` |
| `test_research_gap_batch.py` | 6 (5 failing) | `app/rag/research_gap_batch.py` parallel batches | module has no live importer | `tests/test_research_recovery.py` (operation-slot and deadline recovery), `tests/test_open_question_reliability.py` |
| `test_catalogue_coverage_recovery.py` | 2 | gap-batch catalogue coverage | same rolled-back batch engine | `tests/test_research_definition_recovery.py` (part coverage, purpose search), `tests/test_research_scope_components.py` |
| `test_answer_completion_probe.py` | import error | `app/rag/prompts.build_research_block_prompt` | symbol removed with the block engine | `scripts/answer_applicability_probe.py` contracts in `tests/test_release_probe_contracts.py`; completion checks in `tests/test_research_answer.py` |
| `test_research_completion_salvage.py` | import error | `research_answer.safe_draft_units` salvage | symbol removed | `tests/test_research_answer.py` (`test_initial_verified_partial_survives_recovery_timeout_and_filters_cards`, `test_unavailable_recovery_keeps_source_snapshot_without_quote_body`) |
| `test_research_qualification.py` | import error | `research_windows.qualification_window` | symbol removed | `tests/test_research_windows.py` (live bounded window selection), `tests/test_research_applicability.py` (scope/qualification relation) |

## Individual tests extracted (their files stayed live)

| Archived test | Was in | Superseded assertion | Replacement coverage |
| --- | --- | --- | --- |
| `test_gemini_bound_schema_avoids_rejected_nested_limit_without_relaxing_local_checks` | `tests/test_research_recovery.py` | `_BoundEvidenceProposal` / `_FactBindingProposal` schema rewrite at the SDK boundary | `tests/test_research_applicability.py`, `tests/test_research_recovery.py` (structured failover), `tests/test_llm_observability.py` |
| `test_pilot_uses_complete_fixed_public_units` | `tests/test_release_probe_contracts.py` | `scripts/assessment_binding_pilot.py` + `chunk.source_spans` | the three live probe contracts that remain in `tests/test_release_probe_contracts.py` |
| `test_ranked_long_list_preserves_known_incomplete_structural_read` | `tests/test_research_windows.py` | `window.source_spans[].complete` marker | `tests/test_research_answer.py::test_dangling_document_list_introduction_is_never_displayable` (live `incomplete_statement` backstop) |

See `docs/stabilize-20261016-plan.md` for the full Stage 1 mapping and
`evaluation-results/stabilize-20261016/failures-list.txt` for the baseline.
