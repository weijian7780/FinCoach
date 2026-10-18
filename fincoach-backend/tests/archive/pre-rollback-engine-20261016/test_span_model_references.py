"""Archived reference: tests whose targets were removed in the engine rollback.

Two tests moved out of their live files on 2026-10-16. Both asserted on the
rolled-back span model (``RetrievedChunk.source_spans``) that the current
coaching entrypoints no longer carry. They are retained here as a record.

Excluded from collection (see ``tests/conftest.py``).

1. ``test_pilot_uses_complete_fixed_public_units`` (was in
   ``tests/test_release_probe_contracts.py``):
   imported ``scripts/assessment_binding_pilot.py``, which builds
   ``RetrievedChunk(..., source_spans=...)`` and now raises ``TypeError``. The
   pilot script is part of the rolled-back engine tooling.
   Replacement: the three live probe contracts that stayed in
   ``tests/test_release_probe_contracts.py`` (``public_source_acceptance``,
   ``answer_applicability_probe``, ``tunnel_deadline_probe``).

2. ``test_ranked_long_list_preserves_known_incomplete_structural_read`` (was in
   ``tests/test_research_windows.py``):
   built a long document list and asserted ``window.source_spans`` carried an
   ``complete=False`` marker.
   Replacement: the live structural backstop
   ``check_research_draft`` -> ``complete_evidence_passages`` rejects unfinished
   claim fragments (``incomplete_statement``), covered by
   ``tests/test_research_answer.py::test_dangling_document_list_introduction_is_never_displayable``.
   The live bounded window selection keeps its own coverage in the remaining
   ``tests/test_research_windows.py`` tests.

# --- original tests (verbatim, superseded) ------------------------------------
#
# def test_pilot_uses_complete_fixed_public_units():
#     from scripts.assessment_binding_pilot import fixed_evidence
#     plan, chunks = fixed_evidence()
#     assert not plan.needs_personal and len(chunks) == 2
#     assert all(c.source_type == 'web' and c.source_spans[0].complete for c in chunks)
#     assert sum(len(c.content) for c in chunks) <= 10800
#
#
# def test_ranked_long_list_preserves_known_incomplete_structural_read():
#     from app.rag.research_source_spans import read_source_spans
#     text = '## Married applicants\nRequired documents:\n' + '\n'.join(
#         '- Document ' + str(i) + ': ' + ('supporting details ' * 10) + '.' for i in range(30))
#     p = QuestionPlan('STR', False, True, 'stable', required_facts=('required documents',), part_tracking=True)
#     window, = select_part_windows((page(text),), p)
#     span, = read_source_spans(text, anchors=(window.content,))
#     assert not span.complete
#     assert window.source_spans and any(not s.complete for s in window.source_spans)
