# FinCoach Evidence-Validation Re-Architecture — Plan

Status: **PLAN — locked for implementation.**
Last updated: 2026-09-19
Branch: `codex/financial-report-analytics`

Supersedes the ad-hoc web-fallback shipped earlier this session (see
`web-research-fallback-plan.md`). That code stays on disk but is reworked by
Tasks 3 and 6 below; do not treat it as final.

## Task 0 — Restore a clean baseline (DONE 2026-09-19)

The shipped fallback left the tree failing its own suite. Fixed before anything
else, because Task 1 cannot measure against a crashing tree:

- **`UnboundLocalError: web_fallback_used`** at `service.py:1644`. The
  `interaction_reply` branch (`service.py:1191-1211`) set `chunks = []` but never
  initialised `web_fallback_used`; that variable was only set in the `else`
  branch at line 1278, yet the `coach_pipeline` logger reads it unconditionally.
  Every structured interaction reply crashed (reminder date-confirmation resume,
  disabled-write-action rejection). **Fix:** initialise `web_fallback_used = False`
  beside `chunks = []` in the interaction branch. Both previously-failing tests
  (`test_agent_tools.py`) now pass.
- **Coverage gap that let it ship (now closed):** `test_web_research.py` is
  pure-function only; it had zero coverage of the `service.py` trigger. Added
  `tests/test_web_fallback_trigger.py` (6 tests) driving `send_message` with the
  trigger's collaborators patched — no network. **4 passing guards:** corpus
  adequate → no fire; corpus empty → fires once, web evidence reaches prompt;
  low-similarity corpus → fires; no web results → still grounded, no crash. **2
  `xfail(strict=True)` tripwires** pin the shipped defects Task 3 fixes: raw
  `content` reaching Tavily (PII leak, invariant #7) and `chunks = web_chunks`
  wholesale replace. They pass as expected-failures now; when Task 3 lands they
  flip to unexpected-pass and fail the suite, forcing the marker's removal.
- **Environment:** `tavily-python` is not installed here (live fallback degrades
  to `[]`, as designed). The suite is **pytest**, not unittest. Two test files
  need `supabase`/`google.genai` to import; those failures are environment-only.

### Before Task 1: checkpoint the untracked work (recoverability)

The grounding/verifier layer this plan edits has **no git history** and no
checkpoint. Verified 2026-09-19 against `HEAD = 3fdb993`:

- **Untracked (zero history):** `app/rag/grounding.py`, `verifier.py`,
  `web_research.py`, `query_analysis.py`, `routing.py`, `action_policy.py`,
  `app/agent_tools.py`, `app/agent_actions.py`, and all of `corpus/`.
- `app/rag/service.py` is **+1629 / −76 vs HEAD** — 119 untracked + 92 modified
  paths total. `git diff` cannot show what the re-architecture changes in the
  untracked files: there is no baseline to diff against.
- **`.gitignore` does NOT exclude any of them** (`git check-ignore` clears them;
  it only ignores `__pycache__`, `.pyc`, `.venv`, secrets, `node_modules`). A
  commit or `git stash create` **would** capture the whole layer. The review's
  caution about a silent ignore does not apply.

Consequence: Task 7's "prove `evidence` beats `legacy` against the same tree"
premise needs a real baseline, and the layer is unrecoverable if lost. **Make a
checkpoint before Task 1 edits begin.** Do NOT `git add -A && commit` blindly —
that folds in unrelated mobile/`.env` edits; prefer a labelled WIP checkpoint on
`codex/financial-report-analytics` (undo with `git reset --soft HEAD~1`) or
`git stash create` (leaves the working tree untouched). Neither resets nor
overwrites the existing edits.

## 0. Locked decisions (2026-09-19)

Three product decisions were made by the user and are binding for this plan:

1. **Factual naming from ANY cited source.** The coach MAY state a specific
   provider/product name as a *plain fact* when it is supported by any cited
   source, of any tier — not only tier-1/2. It still may NOT recommend, rank,
   endorse, or tell the user to open/choose/switch to/buy a named product. The
   tier of the source governs the *confidence label on the fact*, not whether
   the name may appear. (This widens the tier-1/2 prompt rule already shipped in
   `prompts.py:182-186`, which must be rewritten in Task 6.)
2. **Full 7-task scope.** All seven tasks below are in scope for this work.
3. **Search + extract passages.** Web research uses Tavily's *extract* endpoint
   to pull real passage text from result pages, not just search snippets, so the
   entailment verifier has genuine source text to check claims against.

## 1. Non-negotiable invariants (carried from spec + security constraints)

The design fails review if any of these is violated.

1. **Corpus first.** Web research runs only when internal RAG cannot answer.
2. **Never fabricate** numbers, product names, policies, citations, or evidence.
   If it is not in a real retrieved source, it does not appear in the answer.
3. **Label every claim by trust tier / confidence.** Community/forum content is
   *anecdotal*, never dressed as established fact.
4. **Cite links.** Every web-sourced claim carries the link it came from.
5. **Explain disagreements** rather than silently picking a winner.
6. **Say "insufficient evidence"** when neither corpus nor web establishes it.
7. **Privacy — de-identified queries only.** `TAVILY_API_KEY` stays server-side.
   Only a de-identified *topic* query goes to Tavily. NEVER send raw conversation
   history, account identifiers, financial records, balances, receipts, or any
   PII to Tavily. (This fixes the raw-message leak in the shipped
   `service.py` fallback trigger, which passes `content` — the raw user
   message — straight to `research_web(...)`.)
8. **Shared 30s deadline.** `COACH_REQUEST_DEADLINE_SECONDS=30` is preserved.
   Every network call (search, extract, verifier batch, repair) draws down the
   *same* budget. No unbounded loops.
9. **Rollback flag.** `COACH_GROUNDING_MODE=legacy|evidence`, defaulting to
   `legacy`. The new path is only reachable under `evidence`; `legacy` must
   behave byte-for-byte as today.
10. **Out of scope this work:** no retrieval tuning (`RETRIEVE_K=3`,
    `RETRIEVE_THRESHOLD=0.45`, `RETRIEVE_CANDIDATES=5`, `RETRIEVE_SCORE_MARGIN=0.10`
    stay put), no embedding change, no reranker, no corpus ingest/prune, no DB
    schema migration. Financial-record ownership/consent/action-confirmation and
    successful-tool-result checks are preserved.

## 2. Confidence classes

| Class | Meaning | Source basis |
|-------|---------|--------------|
| `established` | Verifiable, high-trust | gov/regulatory or official institution (tier 1-2) |
| `reported` | Credible but secondary | reputable publication / academic (tier 3-4) |
| `anecdotal` | Individual experience, not authoritative | community / forum (tier 5) |
| `insufficient` | Neither corpus nor web could establish it | no adequate source found |

Domain→tier is deterministic and allowlist-driven. **Unknown domains map to
`confidence = insufficient` (tier unknown), NOT tier 5.** Tier 5 is reserved for
domains positively known to be community/forum (Reddit, Lowyat, etc.). This
fixes the shipped `classify_tier` behavior where any unknown host returned 5.

---

## Task 1 — Evaluation baseline + harness

**Goal:** Be able to measure whether `evidence` mode is actually better than
`legacy` before adopting it. Nothing else in this plan is trustworthy without
this.

- **Reconcile with the existing harness — do NOT build a parallel one.**
  `rag_evaluation.py` already records `dataset_sha256`, `local_corpus_sha256`,
  `generated_at`, `schema_version`; already gates on `label_status ==
  "human_reviewed"` via `--require-reviewed`; already exports `metrics.json` /
  `per-query.csv` / `report.md` with `passes_acceptance(...)`. And
  `docs/rag-evaluation-protocol.md` already declares financial-answer
  correctness a *separate test layer* with two-reviewer adjudication. Add
  `score_answer_counts(...)` as a **new module beside** `rag_evaluation.py` and
  **reuse** its fingerprint/export/report conventions — this is that second
  layer, not a new system.
- **Blocker (not a coding task): no answer-layer gold labels exist yet.**
  `rag_retrieval_cases.json` has no `label_status`; `rag_fyp_candidate_cases.json`
  is entirely `candidate_unreviewed`. The held-out answer set needs actual human
  review (two reviewers per the protocol) before the harness can emit admissible
  numbers. Decide who reviews before scoping Task 1 as codeable.
- Add a small held-out question set (corpus-answerable, web-answerable, and
  unanswerable buckets) with **human-reviewed** gold labels.
- Implement `score_answer_counts(...)` returning raw counts, not just rates:
  supported / unsupported / refused / fabricated-flag per bucket.

**1(a) DONE 2026-09-19** (codeable half): `app/rag/answer_eval.py` — pure,
offline scorer beside `rag_evaluation.py` (not a parallel harness). Four verdicts
(`supported`/`unsupported`/`fabricated`/`refused`) partition each case; `None`
grounding precision for all-refusal buckets (never 1.0); `compare_answer_arms`
emits the Task 7 three-arm diff vs the `legacy` baseline. Fixture scaffold
`tests/fixtures/answer_eval_cases.json` — 12 cases across the 3 buckets, all
`candidate_unreviewed`, gold labels empty as a review template. Tests
`tests/test_answer_eval.py` (12) green.
**1(b) STILL BLOCKED** (human half): the gold labels need two-reviewer sign-off
per `docs/rag-evaluation-protocol.md` before the harness emits admissible
numbers. Not a coding task; blocks Task 7 adoption, not the intermediate tasks.
- **`None` denominators for refusals** — a refusal must not score as perfect
  precision. Precision is undefined (`None`), not `1.0`, when the answer count
  is zero.
- Record the **baseline revision** and **dirty-file hashes** at run start so a
  later comparison run is provably against the same tree. Do not reset, stash,
  or overwrite the substantial existing edits in the workspace.
- Output: a comparison table (`legacy` vs `evidence`) the later tasks read.

**Acceptance:** harness runs offline (no network) against recorded fixtures and
produces stable counts; refusals show `None` precision.

---

## Task 2 — Separate presentation from statement evidence (DONE 2026-09-19)

**Goal:** Stop conflating "the answer text" with "the checkable claims in it."

**DONE 2026-09-19.** `app/rag/answer_statements.py` (new): the three
`StrictModel` types (`AnswerStatement`, `StatementAssessment`,
`AnswerAssessment`), `split_answer_statements` (reuses grounding's `_HEADING` /
`_PASSAGE_BOUNDARY` / `_line_references` / `_SOURCE_MARKER` so decomposition
tracks exactly what `validate_coach_answer` sees; disclaimer treated as
boilerplate, not a statement), and `format_coach_answer` (reassembles into the
locked 3-heading format AND enforces the ≤120-word cap by dropping whole trailing
statements — Recommended-action first, then Insight while keeping ≥1 — so a
`[Sn]` marker is never orphaned). `count_answer_words` strips markers/bold and
excludes headings + disclaimer. Tests `tests/test_answer_statements.py` (8)
green: split preserves section+markers, format output passes
`validate_coach_answer`, idempotent normal form `format(split(format(x)))==format(x)`,
word cap drops Recommended action before Insight (keeps the answer sentence), and
StrictModels reject extra fields / unknown verdicts.

`StatementAssessment`/`AnswerAssessment` are defined here but *populated* by Task 4
(`assess_answer`); Task 2 only establishes the contracts + decomposition.

- New types (`StrictModel`, `extra="forbid"`):
  - `AnswerStatement` — one atomic statement + its cited source markers.
  - `StatementAssessment` — verdict for one statement (`supported` /
    `unsupported` / `needs_source`) + which source entailed it.
  - `AnswerAssessment` — the roll-up over all statements + overall confidence.
- `split_answer_statements(answer) -> list[AnswerStatement]` — split the LLM
  answer into checkable statements, preserving `[Sn]` markers.
- `format_coach_answer(...)` — reassemble the validated statements back into the
  locked 3-heading / ≤120-word / fixed-disclaimer format. The presented format
  does not change; only the internal decomposition does.

**Acceptance (corrected):** byte-identical round-trip is NOT achievable —
`validate_coach_answer` (`grounding.py:377-503`) enforces format by regex
(headings in order, response must *end* with the exact disclaimer, `[Sn]`
indices within `len(reference_contents)`), and split/reassemble will not
reproduce original whitespace/line-breaks. The real criterion:
`format_coach_answer(...)` output **passes `validate_coach_answer`** AND is
**idempotent** — `format(split(format(x))) == format(x)`. Not "byte-identical to
the legacy draft."

**Word-count enforcement (from review).** The ≤120-word limit is a *prompt
instruction only* (`prompts.py:188`) — `validate_coach_answer` has no word-count
check (verified). So `format_coach_answer` must enforce length itself, or the
"≤120-word" half of the criterion is untestable. `StrictModel`
(`extra="forbid"`) already exists at `models.py:9-10` for the new types.

---

## Task 3 — Preserve and improve research evidence (DONE 2026-09-19)

**Goal:** Give the verifier real passage text, from de-identified queries, merged
with corpus — not snippets, not a replace.

**DONE 2026-09-19.** Tavily extract shape verified against the live docs
(`docs.tavily.com/.../extract`): page text is `results[].raw_content`; failures
surface in `failed_results[].{url,error}` even on HTTP 200; extract accepts a
`query` to rerank chunks + up to 20 URLs. `web_research.py` rewritten:
- `classify_tier -> int | None` — unknown host = `None`/`insufficient`, NOT tier
  5. Tier 5 now requires a known `_COMMUNITY_HOSTS` match. `tier_to_confidence`,
  `tier_label`, sort key, and `prompts._format_reference` all handle `None`.
- `build_research_query` — de-identifies (invariant #7): strips sign-off blocks
  (+ trailing names/refs), emails, phones, ref/account numbers, RM amounts, long
  digit runs; caps length; uses only the current question, never history. Keeps
  in-topic years. Returns `""` when only PII survives.
- `extract_passages` — Tavily extract keyed by URL, `raw_content` capped per page
  (`_MAX_PASSAGE_CHARS`), skips `failed_results`, forwards the de-identified query.
- `merge_evidence` — corpus PRIMARY and whole; web appended in tier order until
  `_MAX_MERGED_CHARS`; corpus is never dropped for web (fixes wholesale replace).
- `research_evidence -> ResearchOutcome` (chunks + `web_ran` + `reason`);
  `research()` kept as the backward-compatible list wrapper.
- `service.py` trigger: sends `build_research_query(content)` (not raw `content`)
  and `merge_evidence(chunks, web_chunks)` (not `chunks = web_chunks`).

**Both `xfail(strict=True)` tripwires flipped to passing** and their markers
removed. Tests: `test_web_research.py` (de-identify ×4, extract mapping/skip-fail,
research_evidence prefers-passage/reason-codes, merge keeps-corpus ×2, unknown =
insufficient) + `test_web_fallback_trigger.py` (de-identified query, merge keeps
corpus) — 45 in those two files, 79 across the evidence suite, all green.

- `build_research_query(question, ...)` — produce a **de-identified topic query**
  (invariant #7). Strip names, amounts, account refs, and conversation history;
  send only the general finance topic. Unit-test that no PII survives.
- `research_evidence(query, ...)` — Tavily **search then extract**: search for
  candidate pages, then call the **extract endpoint** to pull real passage text
  from the top pages (decision #3). Degrade to `[]` on no-key/timeout/error.
  **Prerequisite (unverified):** confirm the Tavily extract SDK response shape
  against official docs before coding — specifically the `raw_content` field and
  how `failed_results` surfaces. This was not reachable in the review session;
  it must be verified, and it is independent of the other findings.
- `merge_evidence(corpus_chunks, web_chunks)` — **merge, do not replace, corpus
  primary.** Per invariant #1 "corpus first" means corpus is the *primary*
  evidence and is never discarded when web fires; web augments it. Fixes the
  shipped `service.py` wholesale replace (`chunks = web_chunks`).
- **Budget interaction (must address):** `verify_grounding_claims`
  (`verifier.py:80-104`) sends **all claims in one batch against the whole
  `reference_contents` list**. Merging corpus + extracted passages lengthens the
  source block; the merged block must stay within the verifier's context budget
  or claims silently truncate. Cap total merged evidence length; if it would
  overflow, prefer corpus passages and the highest-tier web passages.
- `ResearchOutcome` — typed result carrying merged chunks + whether web ran +
  why (for logging/eval).
- **Unknown domain → `insufficient`, not tier 5** (see §2). Only known
  community hosts are tier 5.

**Acceptance:** de-identify test proves no PII leaves; merge keeps corpus chunks;
extract passages (not snippets) reach the prompt; unknown host is `insufficient`.

---

## Task 4 — Verify meaning once per statement (DONE 2026-09-19)

**Goal:** The entailment verifier checks each statement against its cited source
text — once — with enough tokens to actually read a passage.

**DONE 2026-09-19.** `app/rag/answer_assessment.py` (new): `assess_answer` turns
each cited `AnswerStatement` into a `GroundingClaim` and runs
`verify_grounding_claims` in ONE batch (verifier runs at most once per turn,
covering every statement). Fail-closed: any non-"supported" verdict or verifier
error → `unsupported`; uncited statements → `needs_source` (no verifier call).
Overall `AnswerAssessment.confidence` = weakest confidence among the sources that
actually entailed a supported statement (corpus = established; web carries its
tier's label; `insufficient` if nothing supported) — a mix of established +
anecdotal is labeled anecdotal, never dressed up (invariant #3).
`verify_grounding_claims` gained an optional `max_tokens` (defaults to legacy 256
so existing callers are byte-identical); `assess_answer` passes
`GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS=1536`. Tests
`tests/test_answer_assessment.py` (6) green: supported passes + carries entailing
source; fabricated/unsupported rejected; verifier error fails closed; uncited =
needs_source + no verifier call; ≤1 batch for multiple cited statements;
confidence = weakest source relied upon.

- `assess_answer(statements, evidence, ...)` — for each `AnswerStatement`, run
  the fail-closed entailment verifier against the cited source's extracted text;
  return `StatementAssessment`s and the `AnswerAssessment` roll-up.
- **Raise `GROUNDING_VERIFIER_MAX_TOKENS` 256 → 1536** so the verifier can read a
  real extracted passage instead of a snippet. A verifier that truncates fails
  closed — it silently degrades answers — so 256 is likely too small even for
  corpus passages.
- **Measurement-validity caveat (from review):** `legacy` keeps 256 to honor the
  byte-for-byte rollback (invariant #9), but that means Task 7 would compare a
  256-token baseline against a 1536-token new path — the token bump, not the
  architecture, could carry the win. **Task 7 must isolate the token budget as
  its own arm** (legacy@256, legacy@1536, evidence@1536) so the architecture
  change is measured independently of the budget change. Do not attribute a
  win to `evidence` if legacy@1536 already captures it.
- The verifier prompt stays: *"Use only the supplied sources; do not use world
  knowledge."* A statement with no entailing source fails closed — this is what
  enforces invariant #2 by construction, including for a bare named product.

**Acceptance:** a fabricated web claim with no entailing passage is rejected; a
claim entailed by an extracted passage passes; verifier runs at most once per
statement.

---

## Task 5 — Recover a useful answer within one shared budget (DONE 2026-09-19)

**Goal:** When the first answer has unsupported statements, try to recover —
bounded, inside the 30s deadline.

**DONE 2026-09-19.**
- **Budget-role prerequisite fixed.** `CoachRequestBudget.timeout_for`
  (`llm.py`) now handles explicit `"research"` and `"verifier"` roles: each gets
  its own cap (`WEB_FALLBACK_TIMEOUT_SECONDS` / `GROUNDING_VERIFIER_TIMEOUT_SECONDS`)
  clamped by `min(cap, remaining)` against the shared 30s deadline — no longer the
  fixed 18s fallback branch that ignored elapsed time. Each call draws down the
  shared budget and exhaustion raises `TimeoutError` (invariant #8).
- `_ground_with_evidence` (`service.py`) orchestrates, reachable only under
  `COACH_GROUNDING_MODE == "evidence"` (same `(result, retry, fallback)` return
  contract as the legacy path, so the caller is unchanged). Caps: the single
  upstream search+extract is the ≤1 research round; ≤1 repair re-write; ≤2
  verifier batches (initial assess + post-repair assess). Flow: `validate_coach_
  answer` still guards format/product/numerics; on top, `assess_answer` verifies
  entailment; `_keep_after_assessment` drops unsupported cited statements and
  unsupported uncited *facts* (external-fact cue or numeric) while keeping plain
  advice; `format_coach_answer` rebuilds the locked format. If no Insight
  statement survives → one repair; if still nothing → `safe_grounding_fallback`
  (insufficient evidence, invariant #6).
- Wired at `service.py`: `ground_educational = _ground_with_evidence if
  COACH_GROUNDING_MODE == "evidence" else _ground_educational_answer`.

Tests `tests/test_ground_with_evidence.py` (4) green: fully-supported ships
unchanged (no repair); unsupported statement dropped + rebuilt (no repair);
repair runs exactly once then succeeds (`assess` called twice = ≤2 batches);
nothing survives → insufficient fallback, `assess` ≤2 batches.

- **Prerequisite — give Tavily + verifier calls a real budget role (from
  review).** `CoachRequestBudget.timeout_for(role)` (`llm.py:92-104`) only
  special-cases `"primary"`; every other role falls through to the fixed 18s
  `LLM_FALLBACK_TIMEOUT_SECONDS` cap (verified). Tavily search/extract and
  verifier batches currently ride that fallback branch, so "shared 30s budget"
  (invariant #8) is only nominal for them. Add an explicit role or cap for
  research + verifier calls so each genuinely draws down the shared deadline.
- `_ground_with_evidence(...)` orchestrates, with **hard caps**:
  - **≤1 research round** (one search+extract pass).
  - **≤1 repair** (one LLM re-write dropping/citing the unsupported statements).
  - **≤2 verifier batches** total.
  - Every call subtracts from the shared `COACH_REQUEST_DEADLINE_SECONDS` budget;
    on exhaustion, stop and return what is grounded so far.
- If, after the caps, statements remain unsupported, drop them; if nothing
  survives, route through the existing `safe_grounding_fallback(has_sources)` →
  "insufficient evidence" wording (invariant #6).

**Acceptance:** worst case stays under the deadline; recovery never loops; a
partially-grounded answer keeps only its supported statements.

---

## Task 6 — Align product behavior + prompts to "factual naming, any source" (DONE 2026-09-19)

**Goal:** Implement decision #1 in prompt + guard, coherently.

**DONE 2026-09-19.** `prompts.py` education rule rewritten: naming a specific
provider/product as a plain fact is allowed when a cited source of ANY tier
supports it (was tier-1/2 only), with the tier's confidence label attached;
recommend / rank / endorse / "open/choose/switch to/buy" stays absolutely
prohibited regardless of source, and the factual-vs-endorsement line is explicit.
Deterministic guard `_SPECIFIC_PRODUCT_RECOMMENDATION` left UNCHANGED (imperative
only) as the backstop. Casual prompt keeps its strict no-naming rule
(`prompts.py:86`); factual naming is scoped to the education/combined route where
cited sources exist. Tests `tests/test_financial_grounding.py`: prompt permits
any-tier factual naming + keeps the absolute recommend prohibition + drops the
old tier-1/2 wording; the guard still hard-blocks "you should open a Maybank
account". (Known residual gap unchanged: a bare named provider can still slip the
verb+noun regex — mitigated by the verifier requiring an entailing source.)

- **Rewrite the prompt product rule** (`prompts.py:182-186`). Replace the
  tier-1/2 restriction with: *the coach MAY name a specific provider/product as a
  plain fact when a cited source supports the naming, of any tier; it must attach
  the source's confidence label; it must NOT recommend, rank, endorse, or tell
  the user to open/choose/switch to/buy it.* Keep the factual-vs-endorsement
  distinction explicit.
- **Do NOT weaken the deterministic guard.** `_SPECIFIC_PRODUCT_RECOMMENDATION`
  matches only *imperative* recommendations ("open/choose/buy … account/fund"),
  so it already permits factual naming and still blocks "you should open X." Leave
  it as the backstop. (Known residual gap: a bare named provider can still slip
  the verb+noun regex — mitigated, not closed, by the verifier requiring an
  entailing source for the name.)
- **Casual-route conflict (must specify, from review).** Casual keeps "never name
  a specific product" (`prompts.py:86`), but `contains_specific_product_
  recommendation` runs **route-independently** as a backstop. Once education
  permits factual naming, a factual name and a recommendation must be told apart
  with no source context to arbitrate on the casual/agent path. **Intended
  behavior:** the factual-naming allowance is scoped to the education/combined
  route where cited sources exist; casual and agent replies stay under the strict
  no-naming rule. The route-independent guard continues to block imperative
  recommendations everywhere; factual naming is permitted only where a citation
  is present to back it. State this in both prompts so the rule cannot drift.

**Acceptance:** prompt permits "KWSP's 2024 dividend was X% [S1]" from any cited
tier with the right confidence label; prompt + guard still block "you should open
Maybank"; casual-route rule unchanged.

---

## Task 7 — Compare quality and adopt only after passing (BLOCKED — needs data + live run)

**Goal:** Flip `evidence` on only if Task 1 says it wins.

**Status 2026-09-19: code-ready, adoption blocked.** What is in place:
- The three-arm scaffolding exists (`answer_eval.compare_answer_arms`), the token
  arms are isolable (`GROUNDING_VERIFIER_MAX_TOKENS=256` legacy vs
  `GROUNDING_VERIFIER_EVIDENCE_MAX_TOKENS=1536` evidence), and the flag defaults
  to `legacy`.
- **Rollback verified by construction:** with `COACH_GROUNDING_MODE=legacy`
  (default), `service.py` selects `_ground_educational_answer` and the verifier
  keeps its 256-token default — the evidence path is unreachable, so legacy is
  byte-for-byte the prior behaviour. Adopting `evidence` is a single config flip.

**Blockers (not codeable in this environment):**
1. **Gold labels** — Task 1(b): the held-out answer set still needs two-reviewer
   human sign-off per `docs/rag-evaluation-protocol.md` before the harness emits
   admissible numbers.
2. **Live run** — the three-arm comparison needs a live primary LLM key AND a
   Tavily key; neither is set here (`tavily-python` is not installed, and the
   env has no `supabase`/`google.genai`). The run must happen where those are
   configured.

Do the run across `legacy@256`, `legacy@1536`, `evidence@1536`; adopt only if all
hold: no rise in fabricated-claim flags; supported-answer count up on the
web-answerable bucket; refusal rate on the unanswerable bucket does not drop; p95
latency within 30s.

- Run the Task 1 harness across **three arms** to separate the token-budget
  variable from the architecture (see Task 4 caveat): `legacy@256`,
  `legacy@1536`, `evidence@1536`.
- **Acceptance targets** (adopt only if all hold):
  - No increase in fabricated-claim flags vs `legacy`.
  - Supported-answer count on web-answerable bucket goes up.
  - Refusal rate on unanswerable bucket does not drop (no papering over gaps).
  - p95 latency stays within the 30s deadline.
- Ship with `COACH_GROUNDING_MODE=legacy` as the default. Adopting `evidence` is a
  config flip with a working, tested rollback to `legacy`.

**Acceptance:** comparison table recorded; flag defaults to `legacy`; rollback
verified.

---

## Rework checklist for already-shipped code

These edits from earlier this session must be revised by the tasks above:

- `service.py` fallback trigger passes raw `content` to `research_web` →
  **de-identify** (Task 3 / invariant #7).
- `service.py` replaces `chunks` with web results → **merge** (Task 3).
- `web_research.py` `classify_tier` returns 5 for unknown hosts → **unknown =
  `insufficient`, tier unknown** (Task 3 / §2).
- `prompts.py:182-186` tier-1/2 naming rule → **any-cited-source factual naming**
  (Task 6).
- Web sources still not persisted (`coaching_retrievals` has no web columns) —
  **deferred**, DB migration is hazardous and out of scope (§1.10).

## Allowlist expansion — licensed commercial entities (DONE 2026-09-19)

Implemented in the EXISTING tier architecture, not a new JSON-config system (the
frozenset tiers already separate tier-1 statutory from tier-2 commercial; a
versioned config + Shariah flags + auto SC-register checks is more than a
flag-gated fallback needs — revisit if the list grows large).

- **Tier 1:** added `akpk.org.my` (AKPK, a BNM subsidiary; `.org.my` so it needed
  an explicit host entry).
- **Tier 2 (`_OFFICIAL_INSTITUTIONS`):** added `stashaway.my`, `gxbank.my`,
  `aeonbank.com.my`, `kenanga.com.my` — each verified 2026-09-19 against the
  entity's own official site (StashAway = SC DIM eCMSL/A0352/2018; GX Bank + AEON
  Bank = BNM digital banks, PIDM members). Only canonical apex domains.
- **Prompt guardrail:** tier-2 commercial pages are trusted for that
  institution's own factual product details (fees, minimums, eligibility,
  mechanics, licensing/Shariah status) ONLY — never for promotional/performance
  claims, and never to override a tier-1 statutory figure (tier-1 wins a
  conflict). `unknown` tier = insufficient.
- Tests: `classify_tier` cases for the 5 new domains; a prompt test for the
  tier-2 factual-only scope. Live check confirms `stashaway.my` → tier 2
  established (was `insufficient`), non-finance `rocketreach.co` stays insufficient.

- **Added 2026-09-19 (user-verified against SC register + Investor Alert
  clearance):** `versa.com.my` (Versa Asia Sdn Bhd — SC RMO e-Services Platform;
  a 2022 clone-entity scam was alerted, the official domain is clear),
  `wahed.com` + `wahedinvest.com` (Wahed Technologies Sdn Bhd — SC DIM; both apex
  domains share routing, `.com` matches subdomains like `malaysia.wahed.com` via
  the suffix rule), `digitalinvesting.com.my` (Kenanga Digital Investing / KDI
  product portal, where its rate docs actually live; `kenanga.com.my` was kept
  too). All four live-classify as tier 2 established.

Future additions: confirm each on the SC/BNM register, clear the SC Investor
Alert list, use only the canonical apex domain, then add to
`_OFFICIAL_INSTITUTIONS` with a `classify_tier` test.

## Deferred (separate PR, not this work)

Mobile: extend `CoachSource` (`src/lib/types.ts`) with url/source_type/tier/
confidence; tappable source chip (`Linking.openURL`) for web sources; color-coded
tier badge + confidence label. Corpus chips unchanged.
