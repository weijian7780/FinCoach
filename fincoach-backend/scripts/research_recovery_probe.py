"""Opt-in public Coach replay: real corpus/providers/web, zero persisted records.

Run from the backend, in its configured environment:
  python scripts/research_recovery_probe.py --live --warmup --query 'public question'
Warmup matches a ready server; its time is reported separately. This does not
restart/deploy the server, read saved conversations, or query financial tables.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def assessment_snapshot(assessment):
    """Produce JSON-safe nested coverage in the public diagnostic artifact."""
    return asdict(assessment)


class NoPersistenceRepository:
    """Only ephemeral request/response objects; no underlying database client."""

    user_id = "public-research-probe"

    def __init__(self, public_topic: str | None = None):
        # A public-only context reproduces follow-up interpretation without
        # reading stored chat text, financial records or user identifiers.
        self.public_topic = public_topic

    def require_session(self, *_):
        return {"id": "probe-session", "title": "Public research probe"}

    def find_user_message(self, *_):
        return None

    def enforce_usage_limits(self, *_):
        pass

    def insert_user_message(self, session_id, message_id, content):
        return {"id": message_id, "session_id": session_id, "content": content,
                "role": "user", "status": "completed"}

    def list_messages(self, *_):
        if self.public_topic:
            return [{"role": "assistant", "content": "", "ui_payload": {
                "research_context": {"topic": self.public_topic, "time_scope": "stable",
                                     "entities": [], "period": None, "jurisdiction": "Malaysia"},
            }}]
        return []  # Never fetch or forward stored conversation history.

    def complete_turn(self, **kwargs):
        return kwargs["assistant_payload"]

    def mark_user_message_failed(self, *_):
        pass


class PublicCorpusClient:
    """Capability boundary: permit only the two existing public retrieval RPCs."""

    def __init__(self, client):
        self._client = client
        self.rpc_calls = 0
        self.forbidden_attempts = 0

    def rpc(self, name, params):
        if name not in {"match_knowledge_documents", "match_knowledge_documents_hybrid"}:
            self.forbidden_attempts += 1
            raise AssertionError("The public probe forbids non-corpus RPCs.")
        self.rpc_calls += 1
        return self._client.rpc(name, params)

    def table(self, *_):
        self.forbidden_attempts += 1
        raise AssertionError("The public probe forbids table access.")


class StageRecorder(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        try:
            event = json.loads(record.getMessage())
        except (ValueError, TypeError):
            return
        if event.get("event") in {"research_stage", "research_assessment_repair",
                "research_assessment_invalid", "coach_provider_attempt", "coach_pipeline",
                "coach_answer_recovery"}:
            self.events.append(event)


def run_public_probe(question: str, *, warmup: bool = False, public_topic: str | None = None, source_store=None) -> dict:
    from tempfile import TemporaryDirectory
    from app.rag.public_source_store import PublicSourceStore
    isolated_store = TemporaryDirectory(prefix="fincoach-public-probe-") if source_store is None else None
    if isolated_store is not None:
        source_store = PublicSourceStore(Path(isolated_store.name))
    from app import config
    from app.embeddings import embed_query
    from app.rag import service
    from app.rag import research_answer
    from app.rag import verifier
    from app.rag import web_research
    from app.supabase_client import get_supabase

    client = PublicCorpusClient(get_supabase())
    recorder = StageRecorder()
    root_logger = logging.getLogger()
    old_level = root_logger.level
    root_logger.addHandler(recorder)
    root_logger.setLevel(logging.INFO)
    decisions = []
    public_plans = []
    structured_responses = []
    tokens = []
    private_reads = []
    answer_checks = []
    composed_answers = []
    public_pages = {}
    original_extract = web_research.extract_passages
    def capture_extract(*args, **kwargs):
        result = original_extract(*args, **kwargs)
        cache = kwargs.get('cache')
        if cache is not None:
            # Public-only isolated probe: preserve fetched evidence for replay.
            # Production requests never install this diagnostic wrapper.
            public_pages.update({url: text for url, text in cache.full_pages.items()
                if web_research.is_public_guidance_url(url)})
        return result
    original_research = service.run_research_policy
    original_structured = service.generate_structured_result
    original_validate = service.validate_coach_answer
    original_compose = service._compose_research_answer
    original_explanation_check = research_answer.check_research_draft
    original_recovery_generate = research_answer._generate_research_correction
    original_generate = service.generate_result
    generation_attempts = []
    verifier_responses = []
    original_verifier_client = verifier._create_verifier_client

    def verifier_client(**kwargs):
        # Diagnostic-only public replay: keep exact paid checker input/output.
        # This never runs in the server or logs private production prompts.
        client = original_verifier_client(**kwargs)
        original_create = client.chat.completions.create
        def create(**request):
            response = original_create(**request)
            verifier_responses.append({"prompt": request["messages"][-1]["content"],
                "content": str(response.choices[0].message.content or "")})
            return response
        client.chat.completions.create = create
        return client

    def explanation_check(*args, **kwargs):
        result = original_explanation_check(*args, **kwargs)
        answer_checks.append({"draft": args[0], "valid": result.is_valid,
                              "errors": list(result.error_codes), "diagnostics": result.diagnostics})
        return result

    def generated(original, *args, **kwargs):
        result = original(*args, **kwargs)
        from app.llm_observability import result_metadata
        generation_attempts.append({"model": result.model, "prompt_tokens": result.prompt_tokens,
                                    "completion_tokens": result.completion_tokens,
                                    "public_draft": result.content, **result_metadata(result)})
        return result

    def research(*args, **kwargs):
        public_plans.append(vars(args[0]))
        kwargs["source_store"] = source_store
        decision = original_research(*args, **kwargs)
        decisions.append(decision)
        return decision

    def structured(*args, **kwargs):
        result = original_structured(*args, **kwargs)
        from app.llm_observability import result_metadata
        structured_responses.append({"prompt": args[0], "content": result.content, **result_metadata(result)})
        tokens.append({"model": result.model, "prompt_tokens": result.prompt_tokens,
                       "completion_tokens": result.completion_tokens})
        return result

    def forbid_read(*args, **kwargs):
        private_reads.append(True)
        raise AssertionError("The public probe forbids financial tools.")

    def validate(*args, **kwargs):
        result = original_validate(*args, **kwargs)
        # This probe accepts only public questions and forbids private reads.
        # Capture the draft to distinguish generation from later composition.
        answer_checks.append({"draft": args[0], "valid": result.is_valid,
                              "errors": list(result.errors)})
        return result

    def compose(*args, **kwargs):
        result = original_compose(*args, **kwargs)
        composed_answers.append({"failure": kwargs.get("failure"),
                                 "quote_count": len(kwargs.get("quotes", []))})
        return result

    warmup_ms = 0.0
    try:
        if warmup:
            started = perf_counter()
            embed_query("public financial education")
            warmup_ms = round((perf_counter() - started) * 1000, 1)
        with (patch("app.rag.retrieval.get_supabase", return_value=client),
              patch.object(web_research, 'extract_passages', side_effect=capture_extract),
              patch.object(service, "run_research_policy", side_effect=research),
              patch.object(service, "generate_structured_result", side_effect=structured),
              patch.object(service, "validate_coach_answer", side_effect=validate),
              patch.object(service, "_compose_research_answer", side_effect=compose),
              patch.object(research_answer, "check_research_draft", side_effect=explanation_check),
              patch.object(verifier, "_create_verifier_client", side_effect=verifier_client),
              patch.object(service, "generate_result", side_effect=lambda *a, **k: generated(original_generate, *a, **k)),
              patch.object(research_answer, "_generate_research_correction", side_effect=lambda *a, **k: generated(original_recovery_generate, *a, **k)),
              patch.object(service.AgentToolExecutor, "execute", side_effect=forbid_read)):
            started = perf_counter()
            reply = service.CoachingService(NoPersistenceRepository(public_topic), client).send_message(
                "probe-session", "probe-message", question,
            )
            elapsed_ms = round((perf_counter() - started) * 1000, 1)
    finally:
        root_logger.removeHandler(recorder)
        root_logger.setLevel(old_level)
        if isolated_store is not None:
            isolated_store.cleanup()
    assistant = reply["assistant_message"]
    outcome = assistant.get("ui_payload", {}).get("research_outcome", {})
    decision = decisions[-1] if decisions else None
    sources = reply.get("sources", [])
    grounded = bool(decision and decision.source_quotes and sources
                    and outcome.get("status") in {"sufficient", "partial"}
                    and assistant["content"] != research_answer.UNAVAILABLE_MESSAGE
                    and "could not complete the source search" not in assistant["content"]
                    and not private_reads and not client.forbidden_attempts)
    return {
        "query": question, "public_topic": public_topic, "answer": assistant["content"], "model": assistant.get("model"),
        "elapsed_ms": elapsed_ms, "warmup_ms": warmup_ms,
        "store_mode": "isolated_empty" if isolated_store is not None else "explicit_store",
        "source_reuse": decision.diagnostics if decision else {},
        "request_deadline_seconds": config.COACH_REQUEST_DEADLINE_SECONDS,
        "research_policy_enabled": config.COACH_RESEARCH_POLICY_ENABLED,
        "research_outcome": outcome,
        "requested_parts": decision.diagnostics.get("requested_part_labels", []) if decision else [],
        "part_coverage": [vars(part) for part in decision.assessment.parts] if decision else [],
        "answered_part_ids": outcome.get("recovery", {}).get("explanation", {}).get("answered_part_ids", []),
        "evidence_strength_counts": {status: sum(part.status == status for part in decision.assessment.parts)
                                     for status in ("confirmed", "reported", "missing", "conflicting")} if decision else {},
        "source_urls": [source.get("url") for source in sources],
        "validated_quotes": list(decision.source_quotes) if decision else [],
        "public_pages": public_pages,
        "grounded_reply": grounded,
        "complete_answer": grounded and outcome.get("status") == "sufficient" and not outcome.get("missing")
                           and outcome.get("recovery", {}).get("explanation", {}).get("complete", False)
                           and bool(decision and decision.assessment.parts)
                           and all(part.complete for part in decision.assessment.parts)
                           and set(outcome.get("recovery", {}).get("explanation", {}).get("answered_part_ids", []))
                               == {part.part_id for part in decision.assessment.parts},
        "persisted_writes": 0, "private_read_attempts": len(private_reads) + client.forbidden_attempts,
        "public_corpus_rpc_calls": client.rpc_calls,
        "structured_tokens": tokens,
        "structured_responses": structured_responses,
        "public_plans": public_plans,
        "generation_attempts": generation_attempts,
        "explanation_diagnostics": outcome.get("recovery", {}).get("explanation", {}),
        "answer_tokens": {"prompt_tokens": assistant.get("prompt_tokens"),
                          "completion_tokens": assistant.get("completion_tokens")},
        "stages": recorder.events,
        "answer_checks": answer_checks, "composed_answers": composed_answers,
        "verifier_responses": verifier_responses,
        "public_decision": {
            "chunks": [asdict(chunk) for chunk in decision.chunks],
            "assessment": assessment_snapshot(decision.assessment),
        } if decision else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Explicitly enable paid public API calls")
    parser.add_argument("--warmup", action="store_true", help="Warm embeddings as a ready server does")
    parser.add_argument("--require-complete", action="store_true", help="Fail partial/unavailable complete-answer acceptance")
    parser.add_argument("--public-topic", help="Public-only preceding topic for an isolated follow-up replay")
    parser.add_argument("--repeat", type=int, choices=(1, 2), default=1,
                        help="Independent requests with fresh caches and repositories")
    questions = parser.add_mutually_exclusive_group(required=True)
    questions.add_argument("--query")
    questions.add_argument("--case", help="One public case ID from the versioned fixtures")
    args = parser.parse_args()
    if not args.live:
        parser.error("Use --live to authorize public provider/Search/Extract calls.")
    query = args.query
    if args.case:
        fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/research_recovery_cases.json"
        cases = json.loads(fixture.read_text(encoding="utf-8"))["public_questions"]
        query = next((case["question"] for case in cases if case["id"] == args.case), None)
        if query is None:
            parser.error("Unknown public case ID.")
    runs = [run_public_probe(query, warmup=args.warmup and index == 0, public_topic=args.public_topic)
            for index in range(args.repeat)]
    result = runs[0] if args.repeat == 1 else {"runs": runs}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if all(run["complete_answer" if args.require_complete else "grounded_reply"] for run in runs) else 2


if __name__ == "__main__":
    raise SystemExit(main())
