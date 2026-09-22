# FinCoach read routing and clarification design

Status: proposed implementation scope; no application changes made by this document.

## Objective

Keep a recognised financial intent stable while resolving its parameters. Execute a personal read only when its parameters are valid; otherwise ask a targeted question that can be answered on the next turn.

## Evidence and boundaries

The local application already separates `required_read_agent_tool_name` from `required_read_agent_tool_arguments`, defaults spending periods inside `AgentToolExecutor`, and replays user history in `resolve_read_request`. It has no general persisted pending-read contract. `CoachingService` currently handles casual routing before some clarification results. Existing structured clarification resumes only reminder/report preparation and is gated by `COACH_WRITE_ACTIONS_ENABLED`.

Initial resolver probes on 2026-09-22 reproduced the cases below. A recheck while planning found concurrent workspace changes: `get_period_comparison` now correctly resolves June/August. The other listed failures remain. Rebase implementation on the current files and preserve that comparison work.

| Input | Current failure |
|---|---|
| Food spending, then “What about my savings?” | Inherits spending tool and Food category |
| “Compare my spending in June and August” | Initially wrong; now resolves `get_period_comparison` with June/August. Validate and preserve this fix. |
| “Show my September food budget” | Loses Food category |
| “Show me that transaction” | Executes broad transaction search without resolving “that” |
| “Only food” without history | Resolver asks a question, but casual service branch can bypass it |
| Invalid budget period, then “July” | No durable pending budget request to resume |

The existing routing/tool test selection passed 12 tests plus 12 subtests before planning. Those tests do not establish correctness of these uncovered cases. No deployed-backend or device result is claimed.

## Product rules

1. “Show my spending” means current Malaysia calendar month, all categories. State the chosen period in the answer.
2. “Compare my spending” means current calendar month versus previous calendar month. Preserve this existing default and identify both periods in the answer.
3. Explicit calendar-month comparisons use the existing `get_period_comparison` tool and its 2–12 month capability. June versus August means those two months; never silently substitute May. Ambiguous/incomplete periods require clarification. Requests beyond the limit must not be silently truncated. Unsupported custom paired date ranges ask for calendar months; extending the comparison engine to arbitrary paired ranges is outside this plan.
4. “Last month” is relative to the current Malaysia date. “The month before that” is relative to the active period when recognised; otherwise ask. Do not conflate them.
5. Explicit parameters override context. Context overrides defaults only for recognised continuations of the same read intent.
6. Explicit topic changes clear incompatible filters. Bare “my savings” asks whether the user wants saved-goal progress or estimated saving capacity; it must not inherit spending or automatically choose either meaning.
7. “That transaction” without an unambiguous supported reference asks for a date, merchant, or description. A subsequent search is presented as matching transactions, not falsely as an identified exact record. Transaction IDs are never inherited implicitly.
8. Invalid supplied values stay invalid until corrected. Defaults must never replace an explicit invalid date, unknown category, or unresolved reference.
9. A pending read survives a compatible short answer such as “July”. An explicit new topic or cancellation ends that pending read. A bare greeting/thanks ends implicit carryover; it does not execute pending work.
10. `NEEDS_CLARIFICATION` and `UNSUPPORTED` stop personal-data execution and answer generation for that request. Deterministic questions/explanations require no additional provider call.
11. Read clarifications work with AI write actions disabled. Reminder/report confirmation rules remain enforced.
12. Old mobile versions can read the assistant's textual question and reply through normal chat. Chips are an enhancement, not the only continuation mechanism.

## Architecture

```text
Message + bounded owner-scoped history
  -> intent/tool selection
  -> explicit parameter extraction
  -> compatible context resolution
  -> explicit defaults + validation
  -> READY | NEEDS_CLARIFICATION | UNSUPPORTED
       READY -> existing owner-scoped tool -> existing verified answer path
       NEEDS_CLARIFICATION -> saved read state + question + optional chips
       UNSUPPORTED -> supported-scope explanation
```

Keep broad `CoachingRoute` values separate from fine-grained read intent and execution readiness. Do not classify clarification as a new financial topic. An ambiguous request may have no selected tool yet; preserve the identified topic and bounded choices rather than inventing a tool or confidence number.

Extend `ResolvedReadRequest` compatibly with readiness, intent, missing/invalid fields, and parameter provenance. Use `explicit`, `context`, and `default` sources. Keep `arguments` as the concrete tool argument dictionary; provenance must not be passed as tool arguments.

Keep the policy registry small: entries for current allowlisted read tools, their supported parameters, required/defaultable/optional classification, and inheritance eligibility. Actual type/date validation remains authoritative in existing typed tool arguments. Write preparation stays in its existing action pipeline.

Persist versioned state through existing `coaching_messages.ui_payload` and `complete_coaching_turn`; no new financial tables are planned. Use `type: read_clarification` for pending reads and a `read_context` metadata member on completed read answers. Saved state contains intent, arguments, provenance, missing/invalid fields, anchor date, and originating message ID. Do not duplicate financial rows, balances, credentials, or tool results in this state.

Validate persisted state before reuse. Only load owner-scoped assistant messages from the same session. A structured reply may resume only the latest eligible pending read; older/superseded cards return a useful stale-state response. Duplicate request IDs keep existing idempotency semantics. Free-text continuation uses the latest eligible state within bounded history; absence of trustworthy state causes clarification, not broad fetching.

## Delivery milestones

- **A — routing correctness:** concrete failures fixed, explicit comparison periods supported, no new mobile dependency.
- **B — complete clarification loop:** shared read readiness, saved pending state, text continuation, reusable mobile clarification chips.

## Global constraints

- Scope is the AI Financial Coaching module.
- Backend remains FastAPI/Python with real Supabase persistence and owner-scoped reads.
- Use Asia/Kuala_Lumpur for user-facing date semantics.
- Preserve spending consent, provider consent, numeric grounding, tool allowlists, and existing write-action policy.
- No additional model call or new provider dependency for parameter resolution.
- No Jev activation, provider migration, ranked-confidence router, or retrieval redesign in this change.
- No new financial-record write tool or automatic financial-record mutation.
- Preserve the existing FinCoach UI direction and use responsive, accessible controls.
- No deployment, schema migration, APK build, or device installation is part of writing this plan.

## Acceptance and follow-on work

All reproduced failures need regression coverage at the responsible layer; clarification branching also needs service tests that assert zero tool/provider calls. Resume tests must cover text, chips, restart/history reload, consent changes, and cross-session rejection. Add English and Malay variants of the supported intent/period/category cases.

Jev can later supply candidate intent/topic decisions to the same resolver. The resolver's validation and readiness rules remain mandatory regardless of classifier. Candidate confidence calibration and model evaluation belong to a separate routing-provider task.
