"""Public reliability probe for multi-part research acceptance.

Supports explicit --live, --queries-file, --runs, --cache-mode cold|warm, and --output.
Rejects overwrites.
Each cold run gets an ephemeral source store and history; warm runs share the store.
Records per-operation trace events, trial timings, and build identity.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any
from unittest.mock import patch

if str(Path(__file__).parent) != "/tmp":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    # Read-only reference to existing .env outside candidate root
    for _parent in Path(__file__).resolve().parents:
        _backend_env = _parent / "fincoach-backend" / ".env"
        if _backend_env.exists():
            from dotenv import load_dotenv
            load_dotenv(_backend_env)
            break


class PublicHistory:
    user_id = "public-reliability-probe"

    def __init__(self, session_id: str = "public-probe"):
        self.session_id = session_id
        self.messages = []

    def require_session(self, *_):
        return {"id": self.session_id, "title": "Public Reliability Probe"}

    def find_user_message(self, *_):
        return None

    def enforce_usage_limits(self, *_):
        pass

    def insert_user_message(self, session_id, message_id, content):
        item = dict(id=message_id, session_id=session_id, content=content, role="user", status="completed")
        self.messages.append(item)
        return item

    def list_messages(self, *_):
        return list(self.messages)

    def complete_turn(self, **kwargs):
        self.messages.append(kwargs["assistant_payload"])
        return kwargs["assistant_payload"]

    def mark_user_message_failed(self, *_):
        pass


class PublicCorpus:
    def __init__(self, client):
        self.client = client

    def rpc(self, name, args):
        if name not in {"match_knowledge_documents", "match_knowledge_documents_hybrid"}:
            raise AssertionError(f"Non-public RPC forbidden: {name}")
        return self.client.rpc(name, args)

    def table(self, *_):
        raise AssertionError("Database tables forbidden in public probe")


class EventRecorder(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        try:
            data = json.loads(record.getMessage())
        except (TypeError, ValueError):
            return
        if data.get("event") in {
            "coach_provider_attempt",
            "research_stage",
            "coach_answer_recovery",
            "coach_pipeline",
            "coach_verifier_failure",
            "coach_operation_trace",
            "research_assessment_repair",
        }:
            self.events.append(data)


def run_single_conversation(
    questions: list[str],
    *,
    source_store: Any,
    client: Any,
    session_id: str = "probe-turn",
) -> dict[str, Any]:
    from app.rag import service, research_policy, web_research, research_answer

    repo = PublicHistory(session_id=session_id)
    recorder = EventRecorder()
    logger = logging.getLogger("uvicorn.error")
    old_level = logger.level
    logger.addHandler(recorder)
    logger.setLevel(logging.INFO)

    results: list[dict[str, Any]] = []
    decisions: list[Any] = []
    plans: list[Any] = []
    research_inputs: list[dict[str, Any]] = []
    search_results: list[dict[str, Any]] = []
    generated_drafts: list[dict[str, Any]] = []

    original_research = service.run_research_policy
    original_interpret = service.interpret_question
    original_assess = research_policy.assess_evidence
    original_search = web_research._search_pass
    original_generate = service.generate_result
    original_rewrite = research_answer.generate_fallback_result

    def generate(*args, **kwargs):
        from app.llm_observability import result_metadata
        res = original_generate(*args, **kwargs)
        generated_drafts.append(dict(stage="generation", content=res.content, model=res.model,
                                     **result_metadata(res)))
        return res

    def rewrite(*args, **kwargs):
        res = original_rewrite(*args, **kwargs)
        generated_drafts.append(dict(stage="recovery", content=res.content, model=res.model))
        return res

    def assess(plan, chunks, **kwargs):
        res = original_assess(plan, chunks, **kwargs)
        research_inputs.append(dict(plan=asdict(plan), candidates=[asdict(c) for c in chunks], assessment=asdict(res)))
        return res

    def search(c, query, **kwargs):
        res = original_search(c, query, **kwargs)
        search_results.append(dict(query=query, results=[asdict(item) for item in res]))
        return res

    def research(*args, **kwargs):
        dec = original_research(*args, source_store=source_store, **kwargs)
        decisions.append(dec)
        return dec

    def interpret(*args, **kwargs):
        p = original_interpret(*args, **kwargs)
        plans.append(p)
        return p

    def forbid(*args, **kwargs):
        raise AssertionError("Private tools forbidden in public probe")

    try:
        with patch("app.rag.retrieval.get_supabase", return_value=client), \
             patch.object(service, "run_research_policy", side_effect=research), \
             patch.object(service, "interpret_question", side_effect=interpret), \
             patch.object(research_policy, "assess_evidence", side_effect=assess), \
             patch.object(web_research, "_search_pass", side_effect=search), \
             patch.object(service, "generate_result", side_effect=generate), \
             patch.object(research_answer, "generate_fallback_result", side_effect=rewrite), \
             patch.object(service.AgentToolExecutor, "execute", side_effect=forbid):
            coach = service.CoachingService(repo, client)
            for index, question in enumerate(questions):
                before = len(decisions)
                started = perf_counter()
                reply = coach.send_message(session_id, f"msg-{index}", question)
                assistant = reply.get("assistant_message", {})
                decision = decisions[-1] if len(decisions) > before else None
                outcome = assistant.get("ui_payload", {}).get("research_outcome", {})
                explanation = outcome.get("recovery", {}).get("explanation", {})
                category = (
                    "answer_with_clarification"
                    if explanation.get("clarification_part_ids") and explanation.get("used_source_indices")
                    else "complete_answer"
                    if explanation.get("complete")
                    else "verified_partial"
                    if explanation.get("used_source_indices")
                    else "clarification"
                    if assistant.get("model") == "fincoach-research-clarification"
                    else "technical_failure"
                )
                results.append(
                    dict(
                        question=question,
                        answer=assistant.get("content", ""),
                        model=assistant.get("model"),
                        elapsed_ms=round((perf_counter() - started) * 1000, 1),
                        category=category,
                        plan=asdict(plans[-1]) if plans else None,
                        sources=reply.get("sources", []),
                        outcome=outcome,
                        evidence=[asdict(c) for c in decision.chunks] if decision else [],
                    )
                )
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(old_level)

    return {
        "turns": results,
        "events": recorder.events,
        "research_inputs": research_inputs,
        "search_results": search_results,
        "generated_drafts": generated_drafts,
    }


def parse_queries_file(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        cases = []
        for idx, item in enumerate(raw):
            if isinstance(item, str):
                cases.append({"id": f"q{idx+1}", "questions": [item]})
            elif isinstance(item, list):
                cases.append({"id": f"conv{idx+1}", "questions": [str(q) for q in item]})
            elif isinstance(item, dict) and "questions" in item:
                cases.append(item)
            elif isinstance(item, dict) and "question" in item:
                cases.append({"id": item.get("id", f"q{idx+1}"), "questions": [item["question"]]})
        return cases
    raise ValueError(f"Unrecognized format in queries file {path}")


def main():
    parser = argparse.ArgumentParser(description="FinCoach Public Research Reliability Probe")
    parser.add_argument("--live", action="store_true", help="Execute real live public API calls")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON artifact path")
    parser.add_argument("--queries-file", type=Path, help="JSON file containing test queries")
    parser.add_argument("--query", action="append", help="Individual query strings")
    parser.add_argument("--runs", type=int, default=1, help="Number of repetitions per query case")
    parser.add_argument("--cache-mode", choices=["cold", "warm"], default="cold", help="Cache mode for trials")
    parser.add_argument("--warmup", action="store_true", default=True, help="Warmup embeddings once before running")
    args = parser.parse_args()

    if not args.live:
        parser.error("Real public provider execution requires --live")
    if args.output.exists():
        parser.error(f"Output file {args.output} already exists; overwriting is strictly rejected.")

    # Determine cases
    if args.queries_file:
        if not args.queries_file.exists():
            parser.error(f"Queries file {args.queries_file} does not exist.")
        cases = parse_queries_file(args.queries_file)
    elif args.query:
        cases = [{"id": f"cli_case_{i+1}", "questions": [q]} for i, q in enumerate(args.query)]
    else:
        # Default canonical test cases
        cases = [
            {"id": "icu_definition", "questions": ["what is ICU JPM"]},
            {"id": "str_application_docs", "questions": ["how do i apply STR, what document do i need"]},
        ]

    from app import config
    from app.build_info import capture_build_info, get_public_config
    from app.embeddings import embed_query
    from app.rag.public_source_store import PublicSourceStore
    from app.supabase_client import get_supabase

    root = Path(__file__).resolve().parents[1]
    build_info = capture_build_info(root, get_public_config())

    if args.warmup:
        embed_query("public financial education")

    supabase_client = PublicCorpus(get_supabase())

    trials: list[dict[str, Any]] = []

    # Run trials
    if args.cache_mode == "warm":
        with TemporaryDirectory(prefix="fincoach-warm-store-") as warm_dir:
            shared_store = PublicSourceStore(Path(warm_dir))
            for case in cases:
                for run_idx in range(1, args.runs + 1):
                    trial_id = f"{case['id']}-run{run_idx}-warm"
                    try:
                        conv = run_single_conversation(
                            case["questions"],
                            source_store=shared_store,
                            client=supabase_client,
                            session_id=trial_id,
                        )
                        trials.append({
                            "trial_id": trial_id,
                            "case_id": case["id"],
                            "run_index": run_idx,
                            "cache_mode": "warm",
                            "status": "completed",
                            "error": None,
                            **conv,
                        })
                    except Exception as exc:
                        trials.append({
                            "trial_id": trial_id,
                            "case_id": case["id"],
                            "run_index": run_idx,
                            "cache_mode": "warm",
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {str(exc)}",
                            "turns": [],
                            "events": [],
                            "research_inputs": [],
                            "search_results": [],
                            "generated_drafts": [],
                        })
    else:
        # Cold cache mode: each run gets a completely fresh store and session
        for case in cases:
            for run_idx in range(1, args.runs + 1):
                trial_id = f"{case['id']}-run{run_idx}-cold"
                with TemporaryDirectory(prefix="fincoach-cold-store-") as cold_dir:
                    ephemeral_store = PublicSourceStore(Path(cold_dir))
                    try:
                        conv = run_single_conversation(
                            case["questions"],
                            source_store=ephemeral_store,
                            client=supabase_client,
                            session_id=trial_id,
                        )
                        trials.append({
                            "trial_id": trial_id,
                            "case_id": case["id"],
                            "run_index": run_idx,
                            "cache_mode": "cold",
                            "status": "completed",
                            "error": None,
                            **conv,
                        })
                    except Exception as exc:
                        trials.append({
                            "trial_id": trial_id,
                            "case_id": case["id"],
                            "run_index": run_idx,
                            "cache_mode": "cold",
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {str(exc)}",
                            "turns": [],
                            "events": [],
                            "research_inputs": [],
                            "search_results": [],
                            "generated_drafts": [],
                        })

    result_payload = {
        "build_id": build_info["build_id"],
        "source_fingerprint": build_info["source_fingerprint"],
        "config_fingerprint": build_info["config_fingerprint"],
        "primary_model": config.LLM_PRIMARY_MODEL,
        "deadline_seconds": config.COACH_REQUEST_DEADLINE_SECONDS,
        "runtime_limits": {
            "primary_max_tokens": config.LLM_PRIMARY_MAX_TOKENS,
            "structured_timeout_seconds": config.COACH_STRUCTURED_TIMEOUT_SECONDS,
            "primary_timeout_seconds": config.LLM_PRIMARY_TIMEOUT_SECONDS,
            "fallback_timeout_seconds": config.LLM_FALLBACK_TIMEOUT_SECONDS,
        },
        "cache_mode": args.cache_mode,
        "runs": args.runs,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_cases": len(cases),
        "total_trials": len(trials),
        "trials": trials,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "output": str(args.output),
        "build_id": build_info["build_id"],
        "total_trials": len(trials),
        "trials_summary": [
            {
                "trial_id": t["trial_id"],
                "status": t["status"],
                "turns": [
                    {"category": turn.get("category"), "elapsed_ms": turn.get("elapsed_ms")}
                    for turn in t.get("turns", [])
                ],
            }
            for t in trials
        ],
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
