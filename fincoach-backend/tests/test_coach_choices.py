"""Pure parsing/validation/resolution for LLM-offered choice cards."""

import unittest

from app.rag.coach_choices import (
    MAX_CHOICES,
    PAYLOAD_TYPE,
    STATE_VERSION,
    build_choices_payload,
    extract_choice_block,
    parse_choices,
    resolve_choice_query,
)

_OPEN = "<<<FINCOACH_CHOICES>>>"
_CLOSE = "<<<END_FINCOACH_CHOICES>>>"


def _wrap(json_text: str) -> str:
    return f"Here is your answer.\n\n{_OPEN}\n{json_text}\n{_CLOSE}"


class ExtractBlockTests(unittest.TestCase):
    def test_no_block_returns_text_unchanged(self):
        visible, raw = extract_choice_block("Just prose, no metadata.")
        self.assertEqual(visible, "Just prose, no metadata.")
        self.assertIsNone(raw)

    def test_extracts_and_strips_the_tagged_block(self):
        body = '{"choices": [{"label": "A", "query": "show A"}]}'
        visible, raw = extract_choice_block(_wrap(body))
        self.assertEqual(visible, "Here is your answer.")
        self.assertIn('"label": "A"', raw)
        # Raw metadata and markers must never remain in the visible answer.
        self.assertNotIn(_OPEN, visible)
        self.assertNotIn(_CLOSE, visible)
        self.assertNotIn("query", visible)

    def test_truncated_block_is_scrubbed_and_unparseable(self):
        truncated = f"Answer text.\n{_OPEN}\n{{\"choices\": [{{\"label\": \"A\""
        visible, raw = extract_choice_block(truncated)
        self.assertEqual(visible, "Answer text.")
        self.assertNotIn(_OPEN, visible)
        self.assertIsNone(raw)

    def test_second_stray_block_does_not_leak(self):
        body = '{"choices": [{"label": "A", "query": "show A"}]}'
        text = _wrap(body) + f"\n{_OPEN}\nleftover\n{_CLOSE}"
        visible, _raw = extract_choice_block(text)
        self.assertNotIn(_OPEN, visible)
        self.assertNotIn("leftover", visible)


class ParseChoicesTests(unittest.TestCase):
    def test_valid_choices_get_backend_ids(self):
        options = parse_choices(
            '{"choices": [{"label": "Food", "query": "spend on Food"},'
            ' {"label": "Budget", "query": "show my budget"}]}'
        )
        self.assertEqual([o["id"] for o in options], ["c1", "c2"])
        self.assertEqual(options[0]["query"], "spend on Food")

    def test_bare_list_is_accepted(self):
        options = parse_choices('[{"label": "A", "query": "q"}]')
        self.assertEqual(options[0]["id"], "c1")

    def test_none_and_empty_yield_no_cards(self):
        for raw in (None, "", "   ", "not json", "{}", '{"choices": []}', "[]"):
            self.assertIsNone(parse_choices(raw), raw)

    def test_malformed_option_invalidates_whole_block(self):
        for raw in (
            '{"choices": [{"label": "A"}]}',            # missing query
            '{"choices": [{"query": "q"}]}',            # missing label
            '{"choices": [{"label": "", "query": "q"}]}',  # empty label
            '{"choices": [{"label": "A", "query": 3}]}',   # non-string query
            '{"choices": ["A"]}',                        # not an object
        ):
            self.assertIsNone(parse_choices(raw), raw)

    def test_over_length_and_over_count_rejected(self):
        long_query = "x" * 500
        self.assertIsNone(parse_choices(f'{{"choices": [{{"label": "A", "query": "{long_query}"}}]}}'))
        too_many = ",".join('{"label": "A", "query": "q"}' for _ in range(MAX_CHOICES + 1))
        self.assertIsNone(parse_choices(f'{{"choices": [{too_many}]}}'))

    def test_whitespace_is_collapsed(self):
        options = parse_choices('[{"label": "  A  b ", "query": " q\\n q "}]')
        self.assertEqual(options[0]["label"], "A b")
        self.assertEqual(options[0]["query"], "q q")


class PayloadAndResolveTests(unittest.TestCase):
    def _payload(self):
        options = parse_choices(
            '{"choices": [{"label": "Food", "query": "spend on Food"},'
            ' {"label": "Budget", "query": "show my budget"}]}'
        )
        return build_choices_payload(options, origin_message_id="msg-1")

    def test_payload_shape_is_distinct_from_read_clarification(self):
        payload = self._payload()
        self.assertEqual(payload["type"], PAYLOAD_TYPE)
        self.assertNotEqual(payload["type"], "read_clarification")
        self.assertEqual(payload["state"]["version"], STATE_VERSION)
        self.assertEqual(payload["state"]["origin_message_id"], "msg-1")

    def test_resolves_selected_query_from_saved_payload(self):
        self.assertEqual(resolve_choice_query(self._payload(), "c2"), "show my budget")

    def test_invalid_option_id_resolves_to_none(self):
        for bad in ("c9", "", "C1", "nonsense", None):
            self.assertIsNone(resolve_choice_query(self._payload(), bad), bad)

    def test_wrong_type_or_version_resolves_to_none(self):
        self.assertIsNone(resolve_choice_query({"type": "read_clarification"}, "c1"))
        bad = self._payload()
        bad["state"]["version"] = 999
        self.assertIsNone(resolve_choice_query(bad, "c1"))


if __name__ == "__main__":
    unittest.main()
