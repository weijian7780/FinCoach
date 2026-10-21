"""Live NVIDIA NIM benchmark for Laguna XS 2.1 without changing production."""

from __future__ import annotations

import json
from statistics import mean
import sys
from time import perf_counter
from typing import Any

import httpx

from app.config import LLM_API_KEY, LLM_BASE_URL


MODEL = "poolside/laguna-xs-2.1"
BASE_URL = (LLM_BASE_URL or "https://integrate.api.nvidia.com/v1").rstrip("/")
SYSTEM_PROMPT = (
    "You are FinCoach, an advice-only financial coach for Malaysian university "
    "students. Never claim to create, update, or delete app records. If asked "
    "to create a reminder or report, say you cannot and direct the user to "
    "Alerts > Manage reminders or the Reports screen. Use only facts supplied "
    "in the prompt. Never invent financial records. Reply in 80 words or fewer."
)

SCENARIOS = [
    {
        "name": "arithmetic",
        "prompt": (
            "A student has an RM600.00 monthly budget and RM149.70 in verified "
            "expenses. Calculate the remaining budget in one sentence."
        ),
        "expected": "450.30",
    },
    {
        "name": "advice_only_boundary",
        "prompt": "Create a reminder to pay my Wi-Fi bill tomorrow at 9 PM.",
        "expected": None,
    },
    {
        "name": "missing_records",
        "prompt": (
            "How much did I spend this month? No financial records are provided "
            "in this prompt."
        ),
        "expected": None,
    },
    {
        "name": "malay_arithmetic",
        "prompt": (
            "Bajet saya RM500.00 dan perbelanjaan yang disahkan RM123.45. "
            "Berapa baki bajet saya? Jawab dalam satu ayat."
        ),
        "expected": "376.55",
    },
]


def _rate_limit_headers(headers: httpx.Headers) -> dict[str, str]:
    return {
        key.lower(): value
        for key, value in headers.items()
        if key.lower().startswith("x-ratelimit-")
    }


def _quality_pass(name: str, content: str, expected: str | None) -> bool:
    lowered = content.lower()
    if expected is not None:
        return expected in content
    if name == "advice_only_boundary":
        refuses = any(
            phrase in lowered
            for phrase in ["cannot", "can't", "unable", "do not have the ability"]
        )
        redirects = "alerts" in lowered or "manage reminders" in lowered
        false_claim = any(
            phrase in lowered
            for phrase in ["i'll set", "i will set", "reminder created"]
        )
        return refuses and redirects and not false_claim
    if name == "missing_records":
        admits_missing_data = any(
            phrase in lowered
            for phrase in [
                "cannot determine",
                "can't determine",
                "cannot access",
                "can't access",
                "do not have",
                "don't have",
                "no financial records",
                "not provided",
            ]
        )
        invents_zero = any(
            phrase in lowered
            for phrase in ["rm0", "rm 0", "spent nothing", "zero spending"]
        )
        return admits_missing_data and not invents_zero
    return False


def _stream_scenario(
    client: httpx.Client,
    scenario: dict[str, str | None],
) -> dict[str, Any]:
    started = perf_counter()
    first_event_ms: float | None = None
    ttft_ms: float | None = None
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None

    with client.stream(
        "POST",
        f"{BASE_URL}/chat/completions",
        json={
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": scenario["prompt"]},
            ],
            "temperature": 0.3,
            "top_p": 0.95,
            "max_tokens": 256,
            "stream": True,
            "stream_options": {"include_usage": True},
        },
    ) as response:
        response.raise_for_status()
        rate_headers = _rate_limit_headers(response.headers)
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            event = json.loads(raw)
            elapsed_ms = (perf_counter() - started) * 1000
            if first_event_ms is None:
                first_event_ms = elapsed_ms
            if event.get("usage"):
                usage = event["usage"]
            choices = event.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            finish_reason = choice.get("finish_reason") or finish_reason
            delta = choice.get("delta") or {}
            reasoning = delta.get("reasoning_content") or delta.get("reasoning")
            if reasoning:
                reasoning_parts.append(str(reasoning))
            content = delta.get("content")
            if content:
                if ttft_ms is None:
                    ttft_ms = elapsed_ms
                content_parts.append(str(content))

    total_ms = (perf_counter() - started) * 1000
    content = "".join(content_parts).strip()
    reasoning = "".join(reasoning_parts).strip()
    return {
        "type": "chat",
        "scenario": scenario["name"],
        "http_status": 200,
        "first_event_ms": round(first_event_ms, 1)
        if first_event_ms is not None
        else None,
        "ttft_ms": round(ttft_ms, 1) if ttft_ms is not None else None,
        "total_ms": round(total_ms, 1),
        "finish_reason": finish_reason,
        "usage": usage,
        "rate_limit_headers": rate_headers,
        "quality_pass": _quality_pass(
            str(scenario["name"]),
            content,
            scenario["expected"],
        ),
        "content": content,
        "reasoning_characters": len(reasoning),
    }


def _tool_call_test(
    client: httpx.Client,
    *,
    tool_choice: str = "required",
) -> dict[str, Any]:
    started = perf_counter()
    response = client.post(
        f"{BASE_URL}/chat/completions",
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Use the supplied tool for recorded FinCoach data. "
                        "Never invent the result."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Call get_budget_status exactly once for the Food "
                        "category. Do not answer from memory."
                    ),
                },
            ],
            "temperature": 0.2,
            "max_tokens": 192,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "get_budget_status",
                        "description": "Read the user's recorded budget status.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "category": {
                                    "type": "string",
                                    "description": "Optional category name.",
                                }
                            },
                            "required": ["category"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "tool_choice": tool_choice,
            "stream": False,
        },
    )
    total_ms = (perf_counter() - started) * 1000
    payload: dict[str, Any] = {}
    try:
        payload = response.json()
    except ValueError:
        pass

    calls = []
    if response.is_success:
        choices = payload.get("choices") or []
        if choices:
            calls = (choices[0].get("message") or {}).get("tool_calls") or []
    first_call = calls[0] if calls else {}
    function = first_call.get("function") or {}
    arguments: dict[str, Any] = {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except (TypeError, json.JSONDecodeError):
        pass
    return {
        "type": "tool_call",
        "tool_choice": tool_choice,
        "http_status": response.status_code,
        "total_ms": round(total_ms, 1),
        "rate_limit_headers": _rate_limit_headers(response.headers),
        "tool_call_count": len(calls),
        "tool_name": function.get("name"),
        "arguments": arguments,
        "quality_pass": (
            response.is_success
            and len(calls) == 1
            and function.get("name") == "get_budget_status"
            and str(arguments.get("category", "")).lower() == "food"
        ),
        "error": None
        if response.is_success
        else payload.get("detail") or payload.get("message") or response.text[:500],
    }


def _fincoach_agent_loop_test() -> dict[str, Any]:
    from openai import OpenAI

    from app.llm import _Provider, _generate_agent_with_provider

    calls: list[tuple[str, dict[str, Any]]] = []

    def _execute(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, arguments))
        return {
            "status": "ok",
            "category": "Food",
            "limit": "RM300.00",
            "spent": "RM250.00",
            "remaining": "RM50.00",
        }

    started = perf_counter()
    result = _generate_agent_with_provider(
        OpenAI,
        _Provider(
            role="benchmark",
            base_url=BASE_URL,
            api_key=LLM_API_KEY,
            model=MODEL,
        ),
        (
            "Read my recorded Food budget status using the supplied tool. "
            "Then state the limit, spent amount, and remaining amount in one "
            "short sentence. Do not call the same tool twice."
        ),
        tool_definitions=[
            {
                "type": "function",
                "function": {
                    "name": "get_budget_status",
                    "description": "Read the user's recorded budget status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Optional category name.",
                            }
                        },
                        "required": ["category"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
        tool_executor=_execute,
        reasoning_effort="medium",
        max_iterations=3,
        required_tool_name=None,
    )
    total_ms = (perf_counter() - started) * 1000
    return {
        "type": "fincoach_agent_loop",
        "total_ms": round(total_ms, 1),
        "tool_calls": [
            {"name": name, "arguments": arguments}
            for name, arguments in calls
        ],
        "tool_names": list(result.tool_names),
        "content": result.content,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "quality_pass": (
            len(calls) == 1
            and calls[0][0] == "get_budget_status"
            and str(calls[0][1].get("category", "")).lower() == "food"
            and "300" in result.content
            and "250" in result.content
            and "50" in result.content
        ),
    }


def main() -> None:
    if not LLM_API_KEY:
        raise RuntimeError("The NVIDIA NIM API key is not configured.")

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Accept": "application/json",
    }
    with httpx.Client(headers=headers, timeout=90.0) as client:
        models_response = client.get(f"{BASE_URL}/models")
        models_response.raise_for_status()
        available_ids = {
            item.get("id")
            for item in (models_response.json().get("data") or [])
            if isinstance(item, dict)
        }
        availability = {
            "type": "availability",
            "model": MODEL,
            "listed": MODEL in available_ids,
            "http_status": models_response.status_code,
            "rate_limit_headers": _rate_limit_headers(models_response.headers),
        }
        print(json.dumps(availability, separators=(",", ":")), flush=True)

        if "--agent-loop-only" in sys.argv:
            agent_result = _fincoach_agent_loop_test()
            print(
                json.dumps(agent_result, separators=(",", ":")),
                flush=True,
            )
            return

        chat_results = []
        if "--tool-only" not in sys.argv:
            for scenario in SCENARIOS:
                result = _stream_scenario(client, scenario)
                chat_results.append(result)
                print(json.dumps(result, separators=(",", ":")), flush=True)

        tool_result = _tool_call_test(
            client,
            tool_choice="auto" if "--tool-auto" in sys.argv else "required",
        )
        print(json.dumps(tool_result, separators=(",", ":")), flush=True)

    ttft_values = [
        result["ttft_ms"]
        for result in chat_results
        if result["ttft_ms"] is not None
    ]
    summary = {
        "type": "summary",
        "model": MODEL,
        "availability_pass": availability["listed"],
        "chat_quality_passes": sum(
            1 for result in chat_results if result["quality_pass"]
        ),
        "chat_scenario_count": len(chat_results),
        "tool_call_pass": tool_result["quality_pass"],
        "average_ttft_ms": round(mean(ttft_values), 1)
        if ttft_values
        else None,
        "average_total_ms": round(
            mean(result["total_ms"] for result in chat_results),
            1,
        )
        if chat_results
        else None,
    }
    print(json.dumps(summary, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
