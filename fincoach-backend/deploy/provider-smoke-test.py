"""Synthetic production smoke tests; never prints credentials or user data."""

import os
from time import perf_counter

from openai import OpenAI

from app.llm import (
    _Provider,
    _generate_agent_with_provider,
    generate_result,
)


KNOWN_COMPATIBILITY_ERRORS = (
    "name 'budget' is not defined",
    "thinking mode does not support this tool_choice",
    "reasoning_content in the thinking mode must be passed back",
)


def assert_compatible(error: Exception) -> None:
    message = str(error).casefold()
    if any(marker.casefold() in message for marker in KNOWN_COMPATIBILITY_ERRORS):
        raise RuntimeError(f"Known provider compatibility regression: {type(error).__name__}") from error


def synthetic_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_budget_status",
                "description": "Return the verified synthetic budget status.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }
    ]


def synthetic_tool_executor(_name: str, _arguments: dict) -> dict:
    return {"status": "ok", "remaining_amount": "450.30", "currency": "MYR"}


def deepseek_provider() -> _Provider:
    return _Provider(
        role="fallback",
        base_url=os.environ["LLM_BASE_URL"],
        api_key=os.environ["LLM_API_KEY"],
        model=os.environ["LLM_MODEL"],
    )


try:
    started = perf_counter()
    analysis = generate_result(
        "A student has an RM600.00 monthly budget and RM149.70 in verified "
        "recorded expenses. Calculate the remaining budget and answer in one sentence.",
        reasoning_effort="high",
    )
    print("plain", analysis.model, round((perf_counter() - started) * 1000, 1))
    if "450.30" not in analysis.content:
        raise RuntimeError("High-reasoning arithmetic smoke test failed.")
except Exception as error:
    assert_compatible(error)
    raise

provider = deepseek_provider()
tools = synthetic_tool_definitions()

try:
    started = perf_counter()
    required = _generate_agent_with_provider(
        OpenAI,
        provider,
        "Use get_budget_status before answering the synthetic budget question.",
        tool_definitions=tools,
        tool_executor=synthetic_tool_executor,
        reasoning_effort="high",
        max_iterations=3,
        required_tool_name="get_budget_status",
    )
    print("required_tool", required.model, round((perf_counter() - started) * 1000, 1))
    if required.tool_names != ("get_budget_status",) or "450.30" not in required.content:
        raise RuntimeError("DeepSeek required-tool smoke test failed.")
except Exception as error:
    assert_compatible(error)
    raise

try:
    started = perf_counter()
    optional = _generate_agent_with_provider(
        OpenAI,
        provider,
        "Use the available tool to verify the synthetic remaining budget, then answer.",
        tool_definitions=tools,
        tool_executor=synthetic_tool_executor,
        reasoning_effort="high",
        max_iterations=3,
    )
    print("optional_thinking_tool", optional.model, round((perf_counter() - started) * 1000, 1))
    if optional.tool_names != ("get_budget_status",) or "450.30" not in optional.content:
        raise RuntimeError("DeepSeek optional thinking-tool smoke test failed.")
except Exception as error:
    assert_compatible(error)
    raise
