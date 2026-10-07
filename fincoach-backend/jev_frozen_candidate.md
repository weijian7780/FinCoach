# Jev action+topic detection — FROZEN candidate configuration

Frozen 2026-09-21. Do not tune any of the below against the unseen test set
(`tests/fixtures/jev_action_test_cases.json`). Only the development set
(`tests/fixtures/jev_action_dev_cases.json`) was used to reach this config.

## Model / SDK
- provider: TypeSafe System One
- model: `jev-1.13.0`
- sdk: `typesafe-sdk==0.7.0`
- key: `TYPESAFE_API_KEY` in gitignored `.env` (never committed)

## Detection design (candidate C = "independent Noul per action")
- One `system_one` call per message.
- Questions asked in that call:
  - 13 action Nouls (`ACTION_QUESTIONS` in `jev_action_eval.py`)
  - 1 `education` action Noul = **eduB wording** (frozen; eduB2 kept only as
    `jev_action_preds_eduB2.json` for comparison, NOT used).
  - 1 positive-evidence `casual` Noul (`CASUAL_QUESTION`)
  - 1 cadence parameter Noul (`plan_monthly_cadence`, scored separately from intent)
  - 17 topic Nouls (one per `KNOWLEDGE_TOPICS` entry)
- Python combiner: `decide()` in `jev_action_eval.py`
  - NO automatic topic->education promotion
  - NO blanket personal-action suppression
  - casual fires only with its own positive evidence AND nothing financial fired
  - uncertain band (neg < p < pos) with no confident action -> clarification signal

## Frozen operating point
- `pos = 0.70`  (action/topic accept threshold)
- `neg = 0.30`  (confident-NO ceiling; uncertain band = 0.30..0.70)
- `param_pos = 0.70` (cadence Noul)
- `max_actions = 4`

Primary metric is task_set_recall (detect every requested action). 0.70 is chosen
over 0.80 because recall is the release priority (0.931 vs 0.890); 0.80 is recorded
as the precision-leaning alternative (prec 0.903, exact 0.806).

## Development metrics at the frozen point (67 dev cases, eduB)
- pos0.70: task_rec 0.931 / task_prec 0.850 / exact 0.791 / topic_rec 0.909 /
  topic_prec 0.741 / personal_acc 0.970 / unneeded_clarify 4 / missed_clarify 0
- pos0.80: task_rec 0.890 / task_prec 0.903 / exact 0.806 / topic_rec 0.864 /
  topic_prec 0.826 / personal_acc 0.940 / unneeded_clarify 5 / missed_clarify 0

## Finalized labeling rules (applied to the dev set, to be reused on the test set)
1. **budget-allocation** ("how should I split/allocate my budget") = `education`
   only, `requires_personal_records=false`. Matches `routing.py`
   `_BUDGET_ALLOCATION_QUERY`, which routes allocation-method questions to
   FINANCIAL_EDUCATION rather than reading budget status.
2. **ptptn vs student_aid**: PTPTN questions are labelled `["ptptn"]` ONLY.
   `student_aid` is a separate corpus doc (scholarships/biasiswa). Jev additionally
   firing `student_aid` on a PTPTN question is counted as a real topic-precision
   cost, NOT absorbed by relabeling (do not relabel extra predictions as correct).

## Comparison plan (unseen test set)
Three-way on `tests/fixtures/jev_action_test_cases.json`:
- **A** repaired deterministic baseline (`jev_deterministic_baseline.py`) — regex
  routing, multi-read emission repaired (no first-match-wins ceiling).
- **C** this frozen Jev candidate at pos0.70.
- (B, hierarchical Choice, is out of scope for this pass.)
No thresholds or wordings may change after this line based on test-set results.
