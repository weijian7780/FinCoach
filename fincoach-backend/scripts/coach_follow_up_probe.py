"""Public multi-turn acceptance using the ACTIVE Coach and ephemeral history.

Opt in with --live. Only public corpus RPCs, providers and web sources are used.
The real repository and private financial tables are never available to the Coach.
Each conversation uses an empty public-page store. Artifacts are public-only.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

if str(Path(__file__).parent) != '/tmp':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    for _parent in Path(__file__).resolve().parents:
        _backend_env = _parent / 'fincoach-backend' / '.env'
        if _backend_env.exists():
            from dotenv import load_dotenv
            load_dotenv(_backend_env)
            break


class PublicHistory:
    user_id = 'public-follow-up-probe'

    def __init__(self):
        self.messages = []

    def require_session(self, *_):
        return {'id': 'public-probe', 'title': 'Public follow-up'}

    def find_user_message(self, *_):
        return None

    def enforce_usage_limits(self, *_):
        pass

    def insert_user_message(self, session_id, message_id, content):
        item = dict(id=message_id, session_id=session_id, content=content, role='user', status='completed')
        self.messages.append(item)
        return item

    def list_messages(self, *_):
        return list(self.messages)

    def complete_turn(self, **kwargs):
        self.messages.append(kwargs['assistant_payload'])
        return kwargs['assistant_payload']

    def mark_user_message_failed(self, *_):
        pass


class PublicCorpus:
    def __init__(self, client):
        self.client = client

    def rpc(self, name, args):
        if name not in {'match_knowledge_documents', 'match_knowledge_documents_hybrid'}:
            raise AssertionError('Non-public RPC forbidden')
        return self.client.rpc(name, args)

    def table(self, *_):
        raise AssertionError('Database tables forbidden in public probe')


class EventRecorder(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        try:
            data = json.loads(record.getMessage())
        except (TypeError, ValueError):
            return
        if data.get('event') in {'coach_provider_attempt', 'research_stage', 'coach_answer_recovery',
                                 'coach_pipeline', 'coach_verifier_failure'}:
            self.events.append(data)


def run_public_conversation(questions: list[str], *, warmup: bool = True, source_store=None) -> dict:
    from app import config
    from app.embeddings import embed_query
    from app.rag import service
    from app.rag import research_policy, web_research, research_answer
    from app.rag.public_source_store import PublicSourceStore
    from app.supabase_client import get_supabase
    client = PublicCorpus(get_supabase())
    repo = PublicHistory()
    recorder = EventRecorder()
    logger = logging.getLogger()
    old_level = logger.level
    logger.addHandler(recorder)
    logger.setLevel(logging.INFO)
    results, decisions, plans = [], [], []
    research_inputs, search_results, generated_drafts = [], [], []
    original_research, original_interpret = service.run_research_policy, service.interpret_question
    original_assess, original_search = research_policy.assess_evidence, web_research._search_pass
    original_generate, original_rewrite = service.generate_result, research_answer.generate_fallback_result

    def generate(*args, **kwargs):
        result = original_generate(*args, **kwargs)
        generated_drafts.append(dict(stage='generation', content=result.content, model=result.model))
        return result

    def rewrite(*args, **kwargs):
        result = original_rewrite(*args, **kwargs)
        generated_drafts.append(dict(stage='recovery', content=result.content, model=result.model))
        return result

    def assess(plan, chunks, **kwargs):
        result=original_assess(plan, chunks, **kwargs)
        research_inputs.append(dict(plan=asdict(plan), candidates=[asdict(c) for c in chunks], assessment=asdict(result)))
        return result

    def search(client, query, **kwargs):
        result=original_search(client, query, **kwargs)
        search_results.append(dict(query=query, results=[asdict(item) for item in result]))
        return result

    def research(*args, **kwargs):
        decision = original_research(*args, source_store=source_store, **kwargs)
        decisions.append(decision)
        return decision

    def interpret(*args, **kwargs):
        plan = original_interpret(*args, **kwargs)
        plans.append(plan)
        return plan

    def forbid(*args, **kwargs):
        raise AssertionError('Private tools forbidden in public-only probe')

    try:
        if warmup:
            embed_query('public financial education')
        with TemporaryDirectory(prefix='fincoach-follow-up-') as tmp:
            source_store = source_store or PublicSourceStore(Path(tmp))
            with patch('app.rag.retrieval.get_supabase', return_value=client), \
                 patch.object(service, 'run_research_policy', side_effect=research), \
                 patch.object(service, 'interpret_question', side_effect=interpret), \
                 patch.object(research_policy, 'assess_evidence', side_effect=assess), \
                 patch.object(web_research, '_search_pass', side_effect=search), \
                 patch.object(service, 'generate_result', side_effect=generate), \
                 patch.object(research_answer, 'generate_fallback_result', side_effect=rewrite), \
                 patch.object(service.AgentToolExecutor, 'execute', side_effect=forbid):
                coach = service.CoachingService(repo, client)
                for index, question in enumerate(questions):
                    before = len(decisions)
                    started = perf_counter()
                    reply = coach.send_message('public-probe', f'public-message-{index}', question)
                    assistant = reply['assistant_message']
                    decision = decisions[-1] if len(decisions) > before else None
                    outcome = assistant.get('ui_payload', {}).get('research_outcome', {})
                    explanation = outcome.get('recovery', {}).get('explanation', {})
                    category = ('answer_with_clarification' if explanation.get('clarification_part_ids') and
                        explanation.get('used_source_indices') else 'complete_answer' if explanation.get('complete')
                        else 'verified_partial' if explanation.get('used_source_indices')
                        else 'clarification' if assistant.get('model') == 'fincoach-research-clarification'
                        else 'technical_failure')
                    results.append(dict(question=question, answer=assistant['content'], model=assistant.get('model'),
                        elapsed_ms=round((perf_counter()-started)*1000, 1), category=category,
                        plan=asdict(plans[-1]) if plans else None, sources=reply.get('sources', []),
                        outcome=outcome, evidence=[asdict(c) for c in decision.chunks] if decision else []))
    finally:
        logger.removeHandler(recorder)
        logger.setLevel(old_level)
    from app.build_info import capture_build_info, get_public_config
    root = Path(__file__).resolve().parents[1]
    build_info = capture_build_info(root, get_public_config())
    return dict(build_id=build_info.get("build_id"),
                source_fingerprint=build_info.get("source_fingerprint"),
                config_fingerprint=build_info.get("config_fingerprint"),
                primary_model=config.LLM_PRIMARY_MODEL, deadline_seconds=config.COACH_REQUEST_DEADLINE_SECONDS,
                turns=results, events=recorder.events, research_inputs=research_inputs,
                search_results=search_results, generated_drafts=generated_drafts, private_reads=0, persisted_messages=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--query', action='append')
    args = parser.parse_args()
    if not args.live:
        parser.error('Real public-provider calls require --live')
    if args.output.exists():
        parser.error('Refusing to overwrite an earlier paid acceptance result')
    questions = args.query or ['what is ICU, JPM do for?', 'confirm the duties or application now for ICU, JPM']
    result = run_public_conversation(questions)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'turns': [{'category': t['category'],
        'elapsed_ms': t['elapsed_ms'], 'model': t['model']} for t in result['turns']]}))


if __name__ == '__main__':
    main()
