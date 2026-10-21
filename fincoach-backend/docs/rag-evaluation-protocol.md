# FinCoach accuracy and RAG evaluation protocol

## Material Passport
- Mode: experiment plan / implementation verification; not a completed performance experiment.
- Scope: local Batch A accuracy fixes and source-document retrieval evaluation.
- Evidence: deterministic regression tests; no real retrieval scores reported yet.
- Labels: existing development labels are legacy/unreviewed; candidate FYP labels require human review.
- No private financial records or manuscripts are uploaded by this benchmark. Hybrid evaluation uses read-only knowledge RPCs with public/synthetic questions. It does not call an answer-generation LLM.

## What has been implemented

Accuracy: paginated transaction reads with stable date/ID ordering; independent overall/category budget totals; calendar-month comparisons; English/Malay date and category filters; chronological bounded-history follow-up resolution; unknown-category clarification; failed reads no longer default to zero; removal of user/history numeric evidence for personal records; conservative field-aware money-claim checks. These checks are not a proof of arbitrary natural-language financial truth.

Out of scope: mobile races/retry-state changes, message leases, action transactions, production deployment (Batches B/C).

## Research question and comparisons

Proposed question: How well does FinCoach retrieve relevant Malaysian-finance source documents, and how does the production topic-aware hybrid path compare with a raw-query dense baseline?

Primary outcomes: final-context macro precision, recall and F1. Secondary: micro precision/recall/F1, P@3, R@3, F1@3, Hit@1, Hit@3, MRR@3, and unanswerable-query abstention accuracy. Record latency separately. Do not describe retrieval F1 as answer accuracy.

Dense mode embeds the raw question and the checked-in corpus. Hybrid mode calls the actual production `retrieve` function, including topic analysis/inheritance, pgvector+lexical candidates, RRF, topic reservation and filtering. The candidate trace is the merged pre-reservation pool, not a globally exhaustive ranking. Missing hybrid RPC/fallback aborts a hybrid benchmark; it cannot silently become a dense result. The benchmark exercises retrieval directly, not the full chat router: a personal/casual negative query tests retrieval abstention even if the app would normally skip retrieval.

## Dataset and review gate

- Development: `tests/fixtures/rag_retrieval_cases.json` (existing labels; now includes previously skipped negative cases).
- Candidate held-out pilot: `tests/fixtures/rag_fyp_candidate_cases.json` (22 questions, NOT a complete FYP test set).
- Candidate pilot covers four read source topics (AKPK/PTPTN/PIDM/compound interest), English/Malay/mixed wording, a typo, multi-topic queries, contextual follow-ups, and five unsupported queries. It is intentionally labelled `candidate_unreviewed`.
- Expand to all corpus topics before drawing general conclusions. Add independently authored questions from a supervisor/domain reviewer or representative students. Do not claim model-authored questions are independently sampled user questions.
- Review every query against the entire frozen corpus. Labels must list ALL documents that materially support an answer, not just the canonical topic document. Overlap in digital banking/PIDM, aid/PTPTN, scam/crypto, etc. makes single-source labels potentially incomplete.
- Two reviewers where feasible: label independently, record disagreements, adjudicate, retain rationale and reviewer/date metadata. Do not set `label_status=human_reviewed` until a person has actually reviewed it.
- Keep paraphrase families together in one split; audit semantic as well as exact overlap. Freeze held-out labels/questions before tuning. Tune thresholds only on development. After examining test failures to improve the system, that test set is no longer untouched final evidence.
- Final command requires `--require-reviewed`. This is a workflow gate, not cryptographic proof of review.

## Metric definitions

The relevance unit is the unique source DOCUMENT, not a chunk. Deduplicate ranked sources by first occurrence before top-k. Duplicate chunks still affect production context cost, but do not inflate document relevance counts.

For answerable query q, let G be the labelled relevant-source set and R the final returned-source set:

- TP = |G intersect R|; FP = |R minus G|; FN = |G minus R|.
- Precision = TP / |R| (0 when R is empty).
- Recall = TP / |G|.
- F1 = 2PR/(P+R) (0 when both are zero).
- Macro means average each per-query metric over answerable cases. Macro F1 is the mean of query F1, NOT F1 of macro P/R.
- Micro values use pooled TP/FP/FN; false positives from negative cases are included.
- P@3 has denominator 3 even if fewer than 3 unique documents exist/return. R@3 uses |G|. F1@3 is per-query harmonic mean, then macro-averaged.
- MRR is explicitly truncated MRR@3 (legacy JSON key `mrr`).
- `source_coverage_at_3` is pooled recall@3; `expected_retained` is the fraction of answerable queries retaining every expected document.
- Negative cases have undefined P/R/F1 (`null` in per-query output), are excluded from answerable macro means, and are scored separately for correct abstention. Never award retrieval F1=1 just because an unanswerable question returned nothing.
- Missing/failed retrieval runs are errors, not empty successful results. Do not hide them from denominators.

Example: expected {A,B}, returned {A,C}: P=0.5, R=0.5, F1=0.5. Returned {A}: P=1, R=0.5, F1=0.667. More sources can raise recall while lowering precision.

## Reproducible execution (from fincoach-backend)

Only run actual experiments after approving the command/data boundary and ensuring the local embedding model is installed. Model downloads, external DB access and benchmark output writes are not necessary for unit tests.

```powershell
# Development baseline, local corpus, no Supabase writes / no generation calls
.\.venv\Scripts\python.exe rag_evaluation.py --mode dense --output evaluation-results/dense-dev

# Production retriever, read-only Supabase knowledge RPCs
.\.venv\Scripts\python.exe rag_evaluation.py --mode hybrid --output evaluation-results/hybrid-dev

# After candidate labels have actually been reviewed and the test set frozen:
.\.venv\Scripts\python.exe rag_evaluation.py --mode hybrid --cases tests/fixtures/rag_fyp_candidate_cases.json --require-reviewed --output evaluation-results/hybrid-heldout
```

Do NOT run ingestion/pruning as part of evaluation. First verify the remote knowledge index matches the frozen local corpus, embedding model, chunking settings and SQL implementation. Current output explicitly records `database_corpus_verified=false` for hybrid runs: its local corpus fingerprint does not prove remote content equality. Record deployment revision and actual index verification separately before comparing modes.

Outputs: `metrics.json`, `per-query.csv`, `report.md`. Use different output directories for every configuration/run so previous runs are not overwritten. JSON records mode, local-corpus/dataset SHA256, parameters, label status, per-query outcomes and latency. Capture git revision/dirty diff, Python/package versions, hardware, model revision and SQL migration revision alongside results. No pre-fix real benchmark was run during this implementation: do not invent before/after scores from unit tests.

Latency is a sequential single pass and may include cold-start model/network effects. Setup is separately timed; dense/hybrid setup differs. Warm both paths and run repeated fixed-order or randomized-order blocks before making speed claims; report cold and warm results separately. Compare paired per-query differences; use paired query/family bootstrap intervals if estimating uncertainty. A 22-case draft pilot does not establish statistical power or generalization.

## Financial answer correctness is a separate test layer

Use synthetic owner-scoped records to score exact amount/date/category correctness, unsupported recorded claims, consent boundaries, and required clarification. Inject adversarial model drafts to test guards; clearly distinguish this from the frequency of errors in live model answers. For live generation studies freeze prompts/model settings, account for stochasticity, use a reviewed rubric and keep private real user data out of prompts.

## Current verification and remaining work

- Backend full suite passed 315 tests / 2,278 subtests (approved temporary-file access was required for three ingestion tests). The final category-without-limit refinement then passed the targeted 154-test / 83-subtest accuracy, tool, pipeline and evaluator selection. CLI help was also verified.
- No measured recall/precision/F1 scores are provided: metric unit tests are not performance experiments.
- Human label review, wider held-out coverage, remote index verification, real dense/hybrid benchmark runs and device/deployment checks remain external validation steps.
