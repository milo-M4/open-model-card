import unittest

from open_model_card.brief import agent_brief
from open_model_card.client import EndpointError
from open_model_card.compare import (
    comparison_markdown,
    load_reports,
    plain_choice,
    recommend,
)
from open_model_card.guard import block_reason
from open_model_card.hostmem import rss_mb_for_port
from open_model_card.report import build_report, plain_summary, to_markdown, write_report
from open_model_card.score import (
    extract_json_object,
    score_contains,
    score_exact,
    score_hyphen_lines,
    score_json,
    score_numbered_lines,
    score_task,
    strip_thinking,
)
from open_model_card.tasks import TASKS


def task(name):
    matches = [item for item in TASKS if item["id"] == name]
    if not matches:
        raise KeyError(f"no task named {name!r}")
    return matches[0]


class ScoreTests(unittest.TestCase):
    def test_exact_strict(self):
        row = score_task(task("exact-reply-benchok"), "BENCHOK\n")
        self.assertTrue(row["pass"])
        row = score_task(task("exact-reply-benchok"), "benchok")
        self.assertFalse(row["pass"])

    def test_exact_thinking_aware(self):
        # The model writes its answer first, then its reasoning.
        text = "BENCHOK\nHere's a thinking process:\n1. Analyze\n"
        row = score_task(task("exact-reply-benchok"), text, thinking_aware=True)
        self.assertTrue(row["pass"], row["detail"])
        # The non-thinking-aware path stays strict.
        row = score_task(task("exact-reply-benchok"), text, thinking_aware=False)
        self.assertFalse(row["pass"])

    def test_exact_second_token(self):
        row = score_task(task("exact-reply-single-token"), "HELIX42")
        self.assertTrue(row["pass"])

    def test_json_strict(self):
        row = score_task(task("json-action-path"), '{"action":"read","path":"notes.md"}')
        self.assertTrue(row["pass"])
        row = score_task(task("json-action-path"), '{"action":"write","path":"notes.md"}')
        self.assertFalse(row["pass"])

    def test_json_in_code_block(self):
        # A thinking model wraps the JSON in a code block. The strict scorer
        # still finds it because extract_json_object looks inside fences.
        text = "Let me think...\n```json\n{\"action\":\"read\",\"path\":\"notes.md\"}\n```\nDone."
        row = score_task(task("json-action-path"), text)
        self.assertTrue(row["pass"], row["detail"])

    def test_json_second_pair(self):
        row = score_task(task("json-customer-tier"), '{"tier":"gold","renews":"2027-01-15"}')
        self.assertTrue(row["pass"])
        row = score_task(task("json-customer-tier"), '{"tier":"silver","renews":"2027-01-15"}')
        self.assertFalse(row["pass"])

    def test_digits_strict(self):
        row = score_task(task("arithmetic-17x23"), "The answer is 391.")
        self.assertTrue(row["pass"])

    def test_digits_thinking_aware(self):
        # The reasoning trace has lots of small numbers; the model
        # prints 391 on its own line near the end.
        text = (
            "Here's a thinking process:\n"
            "1. 17 * 23 = 391\n"
            "2. Confirm: 391\n"
        )
        row = score_task(task("arithmetic-17x23"), text, thinking_aware=True)
        self.assertTrue(row["pass"], row["detail"])

    def test_facts(self):
        row = score_task(task("faithful-summary"), "On March 3 the invoice was $240.")
        self.assertTrue(row["pass"])
        row = score_task(task("faithful-summary"), "On April 3 the invoice was $240.")
        self.assertFalse(row["pass"])

    def test_meeting(self):
        row = score_task(task("meeting-facts"), "Ship Friday. Hold the newsletter. Budget 50.")
        self.assertTrue(row["pass"])
        row = score_task(task("meeting-facts"), "Ship Monday. Hold the newsletter. Budget 50.")
        self.assertFalse(row["pass"])

    def test_contains(self):
        # Reasoning tests already work in thinking mode because the answer
        # word is somewhere in the trace.
        row = score_task(task("reason-bigger"), "0.67 is larger than 0.6.")
        self.assertTrue(row["pass"])
        row = score_task(task("reason-bigger"), "0.6 is larger than 2/3.")
        self.assertFalse(row["pass"])

    def test_hyphen_lines_strict(self):
        row = score_task(task("three-hyphen-lines"), "- a\n- b\n- c\n")
        self.assertTrue(row["pass"])
        row = score_task(task("three-hyphen-lines"), "- a\n- b\n")
        self.assertFalse(row["pass"])

    def test_hyphen_lines_thinking_aware(self):
        # The thinking trace has explanatory lines that start with '- ' too,
        # but only 3 lines in the whole text match the format. The
        # thinking-aware scorer looks for the answer block of three '- '
        # lines that match the requested count.
        text = (
            "Thinking process:\n"
            "Constraint 1: exactly 3 lines\n"
            "Constraint 2: each line starts with - \n"
            "Here is the answer:\n"
            "- alpha\n"
            "- beta\n"
            "- gamma\n"
        )
        row = score_task(task("three-hyphen-lines"), text, thinking_aware=True)
        self.assertTrue(row["pass"], row["detail"])

    def test_numbered_lines(self):
        row = score_task(task("five-numbered-lines"), "1\n2\n3\n4\n5")
        self.assertTrue(row["pass"])
        row = score_task(task("five-numbered-lines"), "1\n2\n3\n4")
        self.assertFalse(row["pass"])

    def test_strip_thinking_final_marker(self):
        text = "analysis... Final Answer: 0.67\nmore analysis"
        self.assertEqual(strip_thinking(text), "0.67\nmore analysis".strip())

    def test_strip_thinking_fence(self):
        text = "analysis\n```\n0.67\n```\nend"
        self.assertEqual(strip_thinking(text), "0.67")

    def test_strip_thinking_fallback(self):
        text = "no marker, no fence, just text"
        self.assertEqual(strip_thinking(text), text)

    def test_report_names_strength(self):
        row = score_task(task("exact-reply-benchok"), "BENCHOK")
        report = build_report({"model": "demo", "base_url": "http://127.0.0.1:9/v1"}, None, [row], {"available": False})
        text = to_markdown(report)
        self.assertIn("demo", text)

    def test_plain_summary_is_sentences(self):
        row = score_task(task("exact-reply-benchok"), "BENCHOK")
        report = build_report(
            {"model": "demo", "base_url": "http://127.0.0.1:9/v1"},
            {"ttft_s": 2.5, "tok_per_s": 40},
            [row],
            {"available": True, "rss_mb": 28000},
        )
        text = plain_summary(report)
        self.assertIn("started answering in 2.5 seconds", text)
        self.assertIn("large model", text)
        self.assertNotIn("tok/s", text)

    def test_plain_summary_thinking_aware_note(self):
        row = score_task(task("exact-reply-benchok"), "BENCHOK")
        report = build_report(
            {"model": "demo", "base_url": "http://127.0.0.1:9/v1"},
            None,
            [row],
            {"available": False},
        )
        report["thinking_aware"] = True
        text = plain_summary(report)
        self.assertIn("thinking", text.lower())

    def test_to_markdown_thinking_section(self):
        row = score_task(task("exact-reply-benchok"), "BENCHOK")
        report = build_report(
            {"model": "demo", "base_url": "http://127.0.0.1:9/v1"},
            None,
            [row],
            {"available": False},
        )
        report["thinking_aware"] = True
        text = to_markdown(report)
        self.assertIn("## Thinking model", text)

    def test_write_report_creates_two_files(self):
        import json
        import tempfile
        from pathlib import Path
        row = score_task(task("exact-reply-benchok"), "BENCHOK")
        report = build_report(
            {"model": "demo", "base_url": "http://127.0.0.1:9/v1", "family": "llamacpp", "engine_name": "llama.cpp"},
            None,
            [row],
            {"available": False},
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            json_path, md_path = write_report(report, out)
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())
            self.assertTrue(json_path.suffix == ".json")
            self.assertTrue(md_path.suffix == ".md")
            # Filename includes the engine family.
            self.assertIn("llamacpp", json_path.name)
            self.assertIn("demo", json.loads(json_path.read_text())["model"]["id"])


def _card(name, replies, tok_s, rss):
    rows = []
    for item in TASKS:
        rows.append(score_task(item, replies.get(item["id"], "BENCHOK")))
    return build_report(
        {"model": name, "base_url": "http://127.0.0.1:9/v1", "family": "llamacpp", "engine_name": "llama.cpp"},
        {"tok_per_s": tok_s, "ttft_s": 1},
        rows,
        {"available": True, "rss_mb": rss, "pids": ["1"]},
    )


def _all_pass_replies():
    """Replies that pass every task. Used to test that compare picks a clean card."""
    return {
        "exact-reply-benchok": "BENCHOK",
        "exact-reply-single-token": "HELIX42",
        "json-action-path": '{"action":"read","path":"notes.md"}',
        "json-customer-tier": '{"tier":"gold","renews":"2027-01-15"}',
        "arithmetic-17x23": "391",
        "faithful-summary": "March 3 invoice 240",
        "meeting-facts": "Friday, hold the newsletter, budget 50",
        "reason-bigger": "0.67",
        "reason-deduction": "yes",
        "reason-sequence": "32",
        "three-hyphen-lines": "- a\n- b\n- c",
        "five-numbered-lines": "1\n2\n3\n4\n5",
    }


def _small_fast_replies():
    """A small fast model: passes instruction following, fails the rest.

    The compare rules look for instruction following as a minimum for
    cron work, and a small RSS to mark the model as a light repeating
    job. So a model that obeys exact instructions but botches
    structured output and facts is exactly the cron candidate the rules
    are meant to find.
    """
    return {
        "exact-reply-benchok": "BENCHOK",
        "exact-reply-single-token": "HELIX42",
        "json-action-path": "no json here",
        "json-customer-tier": "no json here",
        "arithmetic-17x23": "1",
        "faithful-summary": "April and 500",
        "meeting-facts": "Monday and 100",
        "reason-bigger": "0.6",
        "reason-deduction": "no",
        "reason-sequence": "16",
        "three-hyphen-lines": "no lines",
        "five-numbered-lines": "1 2 3 4 5",
    }


class CompareTests(unittest.TestCase):
    def test_jobs_do_not_share_one_winner(self):
        accurate = _card("large", _all_pass_replies(), tok_s=60, rss=28000)
        small = _card("small", _small_fast_replies(), tok_s=200, rss=3000)
        advice = recommend([accurate, small])
        self.assertEqual(advice["transcripts"]["model"], "large")
        self.assertEqual(advice["operator"]["model"], "large")
        self.assertEqual(advice["cron"]["model"], "small")
        self.assertIn("large", advice["do_not_pair"])

    def test_no_cards_returns_no_winner(self):
        advice = recommend([])
        self.assertIsNone(advice["transcripts"]["model"])
        self.assertIsNone(advice["operator"]["model"])
        self.assertIsNone(advice["cron"]["model"])

    def test_plain_choice_mentions_three_jobs(self):
        text = plain_choice({"transcripts": {"model": "a", "reason": "r"}, "operator": {"model": "b", "reason": "r"}, "cron": {"model": "c", "reason": "r"}, "do_not_pair": []})
        self.assertIn("meeting transcripts", text.lower())
        self.assertIn("day-to-day", text.lower())
        self.assertIn("light repeating", text.lower())

    def test_comparison_markdown_includes_table(self):
        card = _card("model-x", _all_pass_replies(), tok_s=80, rss=10000)
        text = comparison_markdown([card], recommend([card]))
        self.assertIn("| Model (engine)", text)
        self.assertIn("model-x", text)

    def test_load_reports_reads_json_files(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "a.json").write_text(json.dumps({"endpoint": {"model": "a"}}))
            (out / "b.json").write_text(json.dumps({"endpoint": {"model": "b"}}))
            (out / "notes.md").write_text("not a report")
            reports = load_reports(out)
            self.assertEqual(len(reports), 2)
            self.assertEqual([r["endpoint"]["model"] for r in reports], ["a", "b"])


class GuardTests(unittest.TestCase):
    def test_same_model_on_same_server_can_run_again(self):
        reason = block_reason(
            [{"where": "http://127.0.0.1:18434/v1", "model": "Qwen"}],
            "http://127.0.0.1:18434/v1",
            "Qwen",
        )
        self.assertIsNone(reason)

    def test_other_loaded_model_blocks(self):
        reason = block_reason(
            [{"where": "http://127.0.0.1:8000/v1", "model": "MLX-35B"}],
            "http://127.0.0.1:18434/v1",
            "Qwen",
        )
        self.assertIn("was not started", reason)
        self.assertIn("MLX-35B", reason)


class ClientErrorTests(unittest.TestCase):
    def test_endpoint_error_carries_message(self):
        err = EndpointError("HTTP 401 from x: bad key")
        self.assertIn("401", str(err))
        self.assertIn("bad key", str(err))


class HostmemTests(unittest.TestCase):
    def test_returns_unavailable_for_nothing_listening(self):
        # Port 1 is reserved and almost never has a process listening.
        result = rss_mb_for_port(1)
        self.assertFalse(result.get("available", True))


class BriefTests(unittest.TestCase):
    def test_blank_notes_are_marked(self):
        text = agent_brief("# Model choice\n\n| Model |", "Machine:", False)
        self.assertIn("Do not invent a benchmark number", text)
        self.assertIn("blank template", text)
        self.assertIn("Machine:", text)
        self.assertNotIn("openai", text.lower())


if __name__ == "__main__":
    unittest.main()
