# AI coaching deep verification — 16 October 2026

**Result: several functional and integrity defects are fixed in the workspace, but the complete module is not yet ready to certify or deploy.** The full backend suite still fails, a real research follow-up showed irrelevant content, and the hosted database does not have the new recovery/action functions.

## Evidence summary

| Verification | Result | Boundary |
|---|---|---|
| Entire mobile Vitest suite | **418 passed, 3 skipped, 0 failed** | Includes 13 React coaching-screen scenarios; native views, network and device APIs are substituted |
| Mobile TypeScript | **Passed**, `tsc --noEmit` | Canonical `fincoach-mobile` source |
| Entire backend pytest suite | **1,340 passed, 81 failed, 5 skipped, 4 collection errors; 2,417 subtests passed** | Current workspace mounted into Linux container; networking disabled |
| Offline coaching stress audit | **68/68 passed** | Real application functions with synthetic records/providers; fixed fixture date 2026-09-28 |
| Real PostgreSQL assertions | **Passed** | New disposable PostgreSQL 17/pgvector container, no network or app credentials |
| Concurrent processing claims | **8 attempts, 1 winner** | Real database, eight clients |
| Concurrent confirmation/cancellation | **24 attempts, 0 transaction failures** | Final action status agrees with reminder existence; stale decisions cannot win |
| Live model-only sample | **4 responses reviewed** | Synthetic facts and injected reference text; no database access |
| Live public research conversation | **Definition passed; example follow-up has a quality defect** | Real corpus retrieval/providers/web; private tables and tools forbidden, history ephemeral |
| Hosted schema inspection | **Required functions absent** | Read-only catalog query, no account records read |
| Running backend | **Older build, different effective configuration** | Read-only nonsecret flag inspection; no deployment performed |

The full backend result includes existing research experiments and tests, as well as the production paths. **81 failing tests do not mean 81 independently established production bugs.** They remain visible and block a claim that the complete repository is healthy.

## Confirmed defects addressed

| Area | Fault and correction | Evidence |
|---|---|---|
| Conversation history | Timestamp-only pagination skipped messages sharing a timestamp. Added `(created_at, id)` ordering/cursor and validated cursor timestamps/UUIDs. | Regression fixture traverses 65 messages with the same timestamp; malformed cursors rejected |
| Recorded amounts | Disabling optional answer validation allowed fabricated amounts and values taken from the wrong tool field. Personal/combined recorded financial values now always receive deterministic validation. | Both formerly failing flag-off cases pass in the 68-case audit |
| Grounding bypass | Example-cue matching found `eg`/`ie` inside ordinary words and bypassed amount checks. Word boundaries preserve actual example cues. | Grounding regression tests |
| Financial questions | Shared trailing years in month comparisons were applied inconsistently; overlong periods were truncated; hypothetical questions could be interpreted as saved-record questions. | Routing, comparison and accuracy tests |
| Follow-up context | Older finance topics could be revived after an independent topic change or a failed turn. | Follow-up and context tests |
| Reminders | UTC dates could shift the Malaysia recurrence anchor. Expired cards and amounts unsuitable for `numeric(12,2)` could reach confirmation. | Boundary cases cover local midnight, day 31, leap years, expired cards, non-cent/invalid/overflow amounts |
| Action atomicity | Confirmation effects and action status were separate writes. Added row-locked expected-state transitions and reminder insertion in one database function. | Real competing decisions, ownership rejection and forced late-failure rollback |
| Report completion | Client success alone could be accepted. Completion now requires a persisted report belonging to the user and matching the approved dates/category/private path. | Python boundaries plus real SQL wrong-owner, wrong-month, wrong-category and successful completion checks |
| Mobile retries | Clarification retries lost the structured selected value. Consent also retained only visible question text. | Same message ID and interaction payload survive retry; both grant/deny consent paths tested |
| Mobile races | Fast repeated taps could submit twice; old replies/pages/action callbacks could change a newly opened conversation. | Real React callbacks with deferred promises and route changes |
| Network failures | The timeout ended at response headers, leaving a stalled JSON body unbounded; a failed network diagnostic could hide the original error. | API timeout/error-path tests |
| Lost report acknowledgement | Completion failure could regenerate a report or mark a saved PDF failed. Added action-specific lookup/recovery and replay of completion. | Saved-report lookup and screen completion-retry tests |
| Consent isolation | Late spending insights could appear after consent withdrawal; a consent-save callback could send into a different chat. | Deferred consent/insight tests and synchronous duplicate-save guard |
| Research selection | Status/purchase FAQs outranked the requested application/eligibility section. Added purpose-aware English/Malay section selection. | Seven section-selection cases pass, plus existing web retrieval tests |
| Evidence coverage | Status checks counted as complete application instructions; nonautomatic approval could be mistaken for no application requirement. Workflow-title exclusions were not applied. | Coverage and source-scope tests, including separate document/application exemptions |
| Claim support | Words from unrelated passages could jointly authorize a rule, or omit a leading qualifier. A dangling negative could be accepted by the semantic checker. | Cross-passage/qualifier tests and structural sentence guard |
| Form requirements | Unapproved form identifiers or physical-delivery forms could move into an online upload route. | Approved-evidence identifier checks; alternative submission clauses remain separate |
| Verifier/provider output | Valid-looking JSON marked token-truncated could authorize a claim. Empty paid generations lost usage metadata. | All seven observability tests pass; truncation fails closed and JSON/timeout errors remain distinguishable |

Principal changes are in `app/coaching_history.py`, `app/agent_actions.py`, `app/agent_tools.py`, `app/llm.py`, `app/rag/`, mobile coaching components/libraries, and migration `20261015114924_atomic_coach_action_transitions.sql`. The migration explicitly grants the server role the report/category permissions needed by its invoker function; direct mobile execution remains revoked.

One old lexical-grounding test expected a multi-passage EPF paraphrase to pass without semantic review. It now requires semantic review because the claim combines headings/prose and omits the source's membership qualification. One mobile source-text assertion was replaced with real React grant/deny continuation tests. No failing research suites were removed, skipped, or weakened to manufacture a green result.

## Live observations

### Synthetic model-only sample

Four responses, recorded in `../evaluation-results/coach-deep-provider-20261015.jsonl`:

1. A user assertion of RM9,999 remaining was corrected to the synthetic verified RM100.
2. The model did not confuse RM100 of remaining budget with an actual bank balance.
3. The Malay question received a Malay explanation with the correct synthetic figures. Headings/disclaimer stayed English; full localization is not established.
4. An injected reference command to print a marker and claim a bank transfer was ignored.

These are four observed responses, not a measured general accuracy or prompt-injection resistance rate.

### Real public retrieval and two-turn conversation

The first run inherited the local process's disabled research-policy flag. Both responses were delivered through the legacy path. The existing probe incorrectly labelled a response without research diagnostics as `technical_failure`; its classifier now distinguishes `legacy_response`. The original artifact is retained unchanged.

A second run enabled research policy **only for the test process**, matching the running backend's research-mode flag:

| Turn | Observation |
|---|---|
| “What is compound interest?” | Answered the definition in about 13.1 seconds, using retrieved evidence and claim verification; no web search needed |
| “Can you give a simple example?” | Preserved the topic and supplied a numerical example, but took about 31.3 seconds and added an unrelated comparison-table gap statement and product-disclosure advice |

The second answer is **not a quality pass**, despite its internal `verified_partial` label. Its source-entailment checker accepted material that did not belong in this request. This remains a real observed logical/relevance defect; passing citation verification is not sufficient evidence of answer quality.

No private financial tables were accessible to this probe, and no conversations were persisted. The live research sample ran before the final verifier-metadata fix; the latest verifier change has offline regression evidence, not a subsequent paid live rerun.

## Remaining failures and risks to resolve

### Repository contract/integration failures

Exact failed test identifiers and tracebacks are saved in `../evaluation-results/coach-deep-failures-20261016.json`.

| Test module/family | Failures | Evidence / next work |
|---|---:|---|
| `test_evidence_groups` | 13 | `RetrievedChunk.source_spans` / `qualification_context` missing |
| `test_research_applicability` | 9 | Verifier context lacks fact-binding contract |
| `test_research_fact_bindings` | 9 | Missing source metadata / draft-unit integration |
| `test_research_blocks` | 14 | Missing `safe_draft_units`, retained-parts recovery helpers |
| `test_release_probe_contracts`, `test_research_windows` | 3 | Same missing source-span interfaces |
| `test_llm_provider_session` | 5 | Provider-session parameters not integrated into active budget/provider calls |
| `test_research_answer` | 9 | Seven missing correction-helper hooks, one binding interface, one late-rewrite budget expectation |
| `test_research_gap_batch`, `test_catalogue_coverage_recovery` | 7 | Missing cache-operation limits and inactive batch-recovery integration |
| `test_research_policy` | 4 | Two missing correction hooks; two corpus/assessment contract differences |
| `test_research_recovery` | 4 | Missing bound schema; search-country expectation; changed extraction assessment count; unavailable-answer source-snapshot expectation |
| `test_open_question_reliability` | 2 | Writer allocation/minimum-time expectations disagree with current scheduling |
| `test_research_scope_components` | 1 | Missing provider-aware correction helper |
| `test_answer_scope_evaluation` | 1 | Evaluation scorer rejects the `misapplied` verdict |
| **Total failing tests** | **81** | Keep the failures visible until implementation and intended contract agree |

Four additional files cannot collect: `test_answer_completion_probe`, `test_research_completion_salvage`, `test_research_qualification`, and `test_research_scheduling`. They reference missing prompt/salvage/window helpers or a missing finalization-reserve configuration value.

The active service does not import the experimental block/evidence-group/fact-binding/provider-session modules referenced by many of these tests. Reintroducing them is an architectural integration decision; merely adding empty fields or bypassing verification would not satisfy the intended behavior. Some existing tests also expect an assessor bypass for corpus definitions, whereas the active source checks evidence before explanation. These expectations require reconciliation, not an assumption that either side is correct.

### Installed-system gaps

Read-only hosted catalog inspection on 16 October returned NULL for all three functions:

- `claim_coaching_message(uuid,uuid,uuid,uuid,text)`
- `complete_coaching_turn_leased(uuid,uuid,uuid,jsonb,jsonb,text,uuid)`
- `commit_coach_action(uuid,uuid,jsonb,jsonb,jsonb)`

The running container is still `fincoach-backend:research-20261007`; inspected flags are write actions **off**, research policy **on**, grounding mode **legacy**, optional numeric validation **off**, deadline **120 seconds**. It does not establish that these workspace fixes are installed. Deploying the new backend against the current schema would fail its new RPC calls.

The local PostgreSQL harness proves database logic, not hosted PostgREST/RLS deployment, PDF printing, Storage uploads, or Android device behavior. Cross-device report generation/cancellation and remote PDF side effects still need disposable-account end-to-end validation. In particular, action-specific PDF paths currently use an overwrite-capable upload helper; the SQL state transaction cannot make the client-side PDF upload atomic or immutable.

No migrations, backend image, mobile APK, or public tunnel were deployed or changed in this audit.

## Required completion sequence

1. Resolve the research contract/integration failures and the observed irrelevant follow-up content. Verify recovery and deadline behavior without disabling evidence safeguards.
2. Rerun the complete suite and a broader held-out live conversation set covering explanations, public policy, language changes, follow-ups and refusals.
3. Verify report generation, cancellation, lost responses and multiple devices using disposable accounts and real Storage/PDF artifacts.
4. Apply reviewed migrations before the matching backend release, then verify the deployed RPCs/build and test the Android flow. Keep public deployment and native-device proof separate from local checks.

## Reproduction and artifacts

- Mobile: `npm.cmd test -- --reporter=json --outputFile=.test-tmp/coach-deep-mobile-20261016.json`; `node_modules/.bin/tsc.cmd --noEmit`. On this Windows sandbox, TEMP/TMP are set to the project's `.test-tmp` directory.
- Backend: `python -m pytest -p no:cacheprovider tests --continue-on-collection-errors --junitxml=... -q --tb=short`. The final run used the existing Linux backend image for dependencies, a read-only bind of current source, a writable artifact directory, and `--network none`. Local pytest packages were supplied through an isolated vendor directory because the image has no pytest.
- Database: run `tests/run_financial_integrity_database.ps1` from the backend with Docker Desktop available. It creates and removes its own offline database and applies actual schema/migrations before the assertions.
- Offline audit: `python scripts/coach_stress_audit.py --stdout-json > evaluation-results/coach-deep-offline-20261016.json`.
- Live probes are opt-in and can incur provider/search usage; their outputs are retained so a paid run need not be repeated merely to inspect it.

Artifacts under `../evaluation-results/`:

- `coach-deep-backend-20261016.xml` and `.log`: complete final backend results.
- `coach-deep-failures-20261016.json`: every remaining failure/import error.
- `coach-deep-mobile-20261016.json`: complete final mobile result.
- `coach-deep-offline-20261016.json`: 68-case audit, with expected/actual values.
- `coach-deep-database-20261016.log`: final database assertions and concurrency results.
- `coach-deep-provider-20261015.jsonl`: four synthetic live-model responses.
- `coach-deep-public-conversation-20261016.json`: initial legacy-path probe, including the original classifier mistake.
- `coach-deep-research-conversation-20261016.json`: real research conversation, evidence and diagnostic trace.
- `coach-deep-source-manifest-20261016.json`: SHA-256 hashes of tested backend source, SQL assertions, coaching mobile files and new migrations.

Diff whitespace checking found one existing extra blank line in unrelated `app/category_resolution.py`; it was not changed. No unrelated workspace work was reverted.
