# NVIDIA GPT-OSS Primary and Grounding Validation Design

Date: 2026-08-11

## Objective

Release two bounded Coach fixes together, with deployment performed only after local verification:

1. Use NVIDIA NIM `openai/gpt-oss-120b` as the primary Coach provider and direct DeepSeek `deepseek-v4-flash` as fallback.
2. Stop rejecting supported EPF and similar paraphrases while preserving deterministic grounding safeguards.

No mobile, retrieval, database, OCR, ERD, action-tool, or unrelated backend behavior is in scope.

## Provider Design

The provider order remains the existing two-provider loop:

```text
NVIDIA NIM primary
  base URL: https://integrate.api.nvidia.com/v1
  model: openai/gpt-oss-120b
  reasoning effort: high
  completion ceiling: 32,768
        |
        | failure, empty response, rate limit outside retry budget, or timeout
        v
Direct DeepSeek fallback
  base URL: https://api.deepseek.com
  model: deepseek-v4-flash
  reasoning effort: high
  completion ceiling: 32,768
```

The ceiling is not the expected response length. Existing prompts still limit visible Coach output to 60 or 120 words, so providers can stop early. The 32,768 ceiling gives hidden reasoning enough room without incorrectly treating the 131K NVIDIA context window as output-only capacity. It is also below DeepSeek V4 Flash's documented maximum output.

Provider credentials remain environment-only. The NVIDIA key is recovered on the Oracle host from the existing protected backup; no secret is copied into source-controlled files or logs.

## Grounding Design

The validator remains deterministic and adds no model or embedding call.

For each answer line:

1. Collect citations from the individual sentence. If a sentence has no marker, inherit markers from the same answer line.
2. Select only cited source passages with the same negation polarity as the claim.
3. Union the support tokens from those eligible passages across all cited sources.
4. Require the existing 80% claim-token coverage against that evidence union.
5. Normalize possessives and exclude conversational filler tokens so grammar differences do not masquerade as unsupported facts.

This changes the current requirement that one passage independently contain approximately 80% of every word. It permits a supported compound paraphrase to draw evidence from multiple passages while continuing to reject contradictions.

The following safeguards remain unchanged:

- citation indices must exist;
- cited claims must have supporting evidence;
- positive evidence cannot support a negative claim, or vice versa;
- numeric values must exactly match a cited source or verified user context;
- uncited external financial facts remain invalid;
- specific product recommendations remain blocked;
- required headings and disclaimer remain mandatory.

## Failure Handling

- Empty NVIDIA output, including `finish_reason="length"`, enters the existing provider-failover path.
- Short primary HTTP 429 retries remain bounded by the existing request deadline.
- DeepSeek remains the only fallback.
- If both providers fail, the existing request error behavior remains unchanged.
- If grounding still fails after the existing correction attempt, FinCoach returns the safe official-source fallback.

## Test Strategy

Test-first changes will cover:

1. NVIDIA is attempted before DeepSeek and DeepSeek is used when NVIDIA fails.
2. Coach completion calls receive the 32,768 ceiling with high reasoning.
3. The real EPF paraphrase is accepted from the retrieved EPF evidence.
4. A multi-passage supported claim is accepted.
5. A contradiction remains rejected even when other passages share keywords.
6. Unsupported and incorrect numeric claims remain rejected.
7. A line-level citation can support each evidenced sentence on that same line, while an unrelated sentence still fails.

Targeted provider and grounding tests run before the complete backend test suite.

## Deployment and Verification

After local tests pass:

1. Audit the diff against the approved allowlist.
2. Back up the live `.env` if the deployment script has not already done so.
3. Configure NVIDIA NIM as primary, DeepSeek as fallback, and `LLM_MAX_TOKENS=32768`.
4. Recreate only the FinCoach backend container.
5. Verify the public health endpoint.
6. Send a harmless Coach query and inspect provider, finish reason, validation result, latency, and failover logs without exposing financial data or API keys.
7. Confirm unrelated hosted services and containers remain untouched.

## Approved File Boundary

Expected implementation files are limited to:

- `app/config.py`
- `app/llm.py`
- `app/rag/grounding.py`
- `tests/test_rag_pipeline.py`
- `tests/test_response_grounding.py`
- `.env.example`
- local `.env` provider/token values
- `deploy/apply-nvidia120b-primary.sh`
- this design and the subsequent implementation-plan document

Existing unrelated dirty-worktree changes are preserved.
