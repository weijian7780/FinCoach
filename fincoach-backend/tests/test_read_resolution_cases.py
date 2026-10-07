"""Deterministic fixture runner for the read-resolution contract.

Each case fixes ``now`` and history, so the resolver's tool, readiness,
arguments, and missing/invalid fields are pinned without any live records.
Service/persistence behaviours are proven in test_read_clarification and the
service tests, not here.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.rag.routing import resolve_read_request

CASES = json.loads(
    (Path(__file__).parent / "fixtures" / "read_resolution_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_read_resolution_contract(case):
    result = resolve_read_request(
        case["query"], case["history"], now=date.fromisoformat(case["now"])
    )
    expected = case["expected"]
    assert result.tool_name == expected["tool_name"]
    assert result.readiness.value == expected["readiness"]
    assert result.arguments == expected["arguments"]
    assert list(result.missing_required) == expected["missing_required"]
    assert list(result.invalid_fields) == expected["invalid_fields"]
