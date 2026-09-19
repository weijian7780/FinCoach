# Web-Research Fallback for the AI Coach — Design Plan

Status: **DRAFT — requirements locked, integration design pending code exploration.**
Last updated: 2026-09-19

## 1. Purpose

Give the AI coach a controlled way to answer questions the internal corpus (RAG)
cannot answer, by falling back to web research — without weakening any of the
existing anti-fabrication and grounding guards. This is a *fallback*, not a
replacement: the corpus is always tried first.

## 2. Non-negotiable invariants (from spec)

These are hard requirements. The design fails review if any is violated.

1. **Corpus first.** Web research runs only when internal RAG cannot answer.
   Retrieval-then-web, never web-first.
2. **Source priority tiers** (highest → lowest trust):
   1. Government / regulatory (e.g. central bank, tax authority, statute)
   2. Official institutions (the actual provider/issuer's own site/docs)
   3. Reputable publications (established press, well-known outlets)
   4. Academic (peer-reviewed / scholarly)
   5. Community / forums (Reddit, forums, blogs, Q&A)
3. **Never fabricate** numbers, product names, policies, citations, or evidence.
   If it is not in a real retrieved source, it does not appear in the answer.
4. **Label every claim by trust tier.** Community/forum content is presented as
   *anecdotal*, never dressed up as established fact.
5. **Cite links.** Every web-sourced claim carries the link it came from.
6. **Explain disagreements.** When sources conflict, surface the disagreement and
   which tier each side sits in — do not silently pick a winner.
7. **Say "insufficient evidence"** when the web cannot establish the answer either.
   Do not paper over a gap with a confident-sounding guess.

## 3. Confidence / trust classes

Every answer (and ideally every claim) is tagged with one of four classes:

| Class | Meaning | Source basis |
|-------|---------|--------------|
| `established` | Verifiable, high-trust | gov/regulatory or official institution |
| `reported` | Credible but secondary | reputable publication / academic |
| `anecdotal` | Individual experience, not authoritative | community / forum |
| `insufficient` | Web could not establish it | no adequate source found |

## 4. Guards that must survive the change

Carried over from prior work on the answer/validation layer — the web path must
respect these, not bypass them:

- No fabricated product names or named financial providers presented as
  recommendations. (Backstop gap already known: a bare named provider can slip
  the verb+noun guard regex — the web path must not widen that hole.)
- Numeric claims must trace to a real source; no invented figures/rates.
- The existing verifier/rescue behavior on the RAG path stays intact; the web
  path plugs into the same validation, it does not get a private exemption.
- Malay-language handling and the compound-corpus behavior are preserved.

## 5. Flow (target)

```
user question
  → RAG retrieval over corpus
     → adequate grounding?  ── yes ──> answer via existing RAG path (unchanged)
                            └─ no  ──> WEB RESEARCH FALLBACK
                                         → query web
                                         → rank hits into tiers 1–5
                                         → synthesize with per-claim tier labels
                                         → run through answer validation/guards
                                         → if still ungrounded → "insufficient evidence"
```

## 6. Integration design (finalized against real code)

Grounded in the actual schema and guard layer:
- Response contract: `CoachTurnResponse` → `MessageResponse` + `sources: list[SourceResponse]`;
  `SourceResponse = {title, source, similarity, rank}`; `StrictModel` `extra="forbid"`.
- Flow: `CoachingService.send_message` (`app/rag/service.py:1131-1665`) → route →
  `retrieve()` (only FINANCIAL_EDUCATION/COMBINED) → `build_coach_prompt` → LLM →
  grounding/verifier → persist.
- Guards: `validate_coach_answer` (`grounding.py:377-503`) + fail-closed entailment
  `verify_grounding_claims` (`verifier.py`); the verifier prompt says *"Use only the
  supplied sources; do not use world knowledge."*
- Mobile: sections not raw markdown, **no `Linking`/clickable links**, source chips
  non-tappable, label = filename + "% match"; `CoachSource` has no url/tier/confidence.

### D1. Web hits reuse the existing chunk → citation → verifier machinery
Each web result becomes a `RetrievedChunk`-compatible object (`content` = extracted
page text, `source` = domain/title). It gets an `[Sn]` marker in the same
`build_coach_prompt` references block, so the **entailment verifier and numeric guard
apply identically** — no exemption. Because the verifier only accepts claims entailed
by supplied source text, invariant #3 (never fabricate) is enforced *by construction*:
a web claim with no supporting fetched text fails closed exactly like a corpus claim.

### D2. Trigger = corpus-inadequate on a knowledge route ("corpus first")
After `retrieve()` (`service.py:1247-1256`): if route ∈ {FINANCIAL_EDUCATION, COMBINED}
**and** (`chunks` empty **or** max `similarity` < `WEB_FALLBACK_SIM_THRESHOLD`), run web
research to populate `chunks`, then continue down the unchanged prompt/validation path.
CASUAL (no retrieval) and PERSONAL_FINANCE (user's own data) never trigger web.

### D3. Tier assignment is deterministic by domain
A domain→tier classifier (allowlist-driven): 1 gov/regulatory (`*.gov.my`, BNM, LHDN),
2 official institution (issuer's own domain), 3 reputable publication, 4 academic
(`.edu`, DOI), 5 community/forum. **Unknown domains default to tier 5 and are never
upgraded** — this is what stops community content being dressed as fact (invariant #4).
Testable in isolation.

### D4. Schema extension (explicit — `extra="forbid"`)
Extend `SourceResponse` (backend) and `CoachSource` (mobile) with, all optional and
backward-compatible (corpus sources keep defaults):
- `url: str | None = None`
- `source_type: Literal["corpus","web"] = "corpus"`
- `tier: int | None = None`  (1–5, web only)
- `confidence: Literal["established","reported","anecdotal","insufficient"] | None = None`

### D5. Answer format stays locked; tiers ride the source objects, not prose
The 3-heading / ≤120-word / fixed-disclaimer format is **unchanged** (changing it breaks
`validate_coach_answer`). Per-claim trust is expressed by (a) the existing `[Sn]` markers
in prose and (b) each `[Sn]` source carrying `tier`/`confidence`, rendered as a colored
tier badge on a now-tappable source chip. Labels every cited claim without touching the
validated format.

### D6. Disagreement handling
New prompt rule: *"If sources disagree, state the disagreement in Insight and cite each
side; do not silently choose."* The differing tier badges on the cited chips make the
trust asymmetry visible (invariant #6).

### D7. Insufficient evidence
If web research yields no tier-1..4 source (only tier-5 or nothing) for a question that
needs an authoritative answer, answer `confidence = "insufficient"` and route through the
existing `safe_grounding_fallback(has_sources=False)` wording. Anecdotal-only info may be
shared but is explicitly labeled anecdotal, never presented as the answer (invariants #4, #7).

### Mobile work
- Extend `CoachSource`; make the source chip tappable → `Linking.openURL(url)` when `url`
  present; add color-coded tier badge + confidence label on `source_type === "web"` chips.
  Corpus chips unchanged.

### Tests
Domain→tier classifier; trigger threshold (empty / below-threshold / above-threshold);
verifier gates a fabricated web claim; schema backward-compat (corpus response unchanged);
mobile chip opens link + renders correct badge.

## 7. Decisions (locked 2026-09-19)

1. **Product-name ban → loosened.** Web path MAY name a specific provider/product when
   the naming claim is cited to a **tier-1 (gov/regulatory) or tier-2 (institution's own
   official) source**. Still no imperative "you should open/switch to X" recommendation
   phrasing — factual naming only ("BNM's authorised list includes …", "per KWSP, the
   dividend was …"). Unknown/tier-3–5 sources cannot lift the ban. If you meant a broader
   loosening than tier-1/2, flag it and I'll widen.
2. **Provider = Tavily.** `TAVILY_API_KEY` read from config; user configures it later. With
   no key set the fallback yields no web sources → answer degrades to "insufficient evidence"
   rather than erroring.
3. **Scope = backend first**, mobile link/badge UI as a second PR.

## 9. Implementation status — backend (2026-09-19)

**Done and tested (27 web-research tests + 117 in the affected suites green; the one
failing test is a pre-existing `ModuleNotFoundError: supabase` at import time in this
env, unrelated to this change).**

- `app/rag/web_research.py` (new): Tavily search wrapper (lazy import, degrades to no
  results with no key), deterministic domain→tier classifier (unknown → tier 5, never
  upgraded), tier→confidence mapping, and `RetrievedChunk` adapter (tier-ranked, negative
  synthetic ids).
- `app/config.py`: `TAVILY_API_KEY`, `WEB_FALLBACK_ENABLED`, `WEB_FALLBACK_SIM_THRESHOLD`,
  `WEB_FALLBACK_MAX_RESULTS`, `WEB_FALLBACK_TIMEOUT_SECONDS`.
- `app/models.py` `SourceResponse` + `app/rag/retrieval.py` `RetrievedChunk`: added
  `url` / `source_type` / `tier` / `confidence` (optional, backward-compatible).
- `app/rag/service.py`: corpus-first web fallback trigger after `retrieve()`; `source_rows`
  now carries web provenance; `coaching_retrievals` persistence filtered to corpus chunks;
  `web_fallback` added to the pipeline log.
- `app/rag/prompts.py`: web references injected with `web; tier=N (label); confidence=…; url=…`;
  added disagreement, tier-labeling, and insufficient-evidence rules.
- `requirements.txt`: `tavily-python` (optional at runtime).

**Product-name ban loosening (per §7.1) is prompt-only — the deterministic guard was NOT
weakened.** The `_SPECIFIC_PRODUCT_RECOMMENDATION` regex only ever matched *imperative*
recommendations ("open/choose/buy … account/app/fund"), so it already permitted factual
naming and still hard-blocks "you should open X" on every route. Only the coach prompt rule
was relaxed to allow factual naming when cited to a tier-1/2 source.

### Known limitations / residual risk (backend)
- **Web sources are not persisted.** They render on the live turn but `coaching_retrievals`
  has no web columns, so a reloaded past answer loses its web chips. Closing this needs a
  `coaching_retrievals` migration (url/source_type/tier/confidence, nullable
  knowledge_document_id) + RPC + `list_retrievals*` select changes — a separate DB change,
  deliberately deferred given the migration-hazard history.
- **No hard guard binds a *named provider* to a tier-1/2 citation.** A model could name a
  provider citing a tier-5 source against the prompt rule; mitigated by the prompt + the
  entailment verifier (the name must at least be supported by a cited source's text), but
  the same bare-named-provider backstop gap noted previously still applies.
- **Tavily key not yet set** — until it is, the fallback yields no web sources and answers
  degrade to "insufficient evidence" (by design).

## 10. Next: mobile (deferred second PR)
Extend `CoachSource` (`src/lib/types.ts`) with url/source_type/tier/confidence; make the
source chip tappable (`Linking.openURL`) for web sources; add a color-coded tier badge +
confidence label. Corpus chips unchanged.

## 11. Superseded open-decisions (see §7)

1. **Product-name ban (safety guard).** Today the guard blocks naming *any* specific
   provider/product as a recommendation and redirects to BNM authorised lists
   (`grounding.py`, `safe_product_redirect`). My default: **web fallback keeps this ban.**
   So "which bank has the best FD rate now?" still redirects rather than naming a bank,
   even when web research could find it — the web path explains policies/definitions/cited
   rate *ranges* with tiers, but won't recommend a named product. Loosening this to let a
   tier-1/2 citation name a provider is a deliberate weakening of a safety guard and I want
   explicit sign-off before doing it. **Keep the ban, or loosen it for tier-1/2 sources?**

2. **Web search provider under RM0/no-card.** A hosted search API (Tavily/Brave) is easiest
   but the free tiers can require a card. Alternatives: self-host SearXNG, or a curated
   **allowlist + direct fetch** of known MY gov/official finance domains (BNM, LHDN, KWSP,
   PIDM, SC) — most robust for free but weak on tier 3–5 coverage. **Which provider?**

3. **Scope of first cut.** Backend-only (schema + tiers + citations returned, chips still
   non-tappable) as a first PR, then mobile link/badge UI as a second — or both together?
```
