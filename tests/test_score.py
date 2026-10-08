import unittest

from open_model_card.compare import recommend
from open_model_card.report import build_report, to_markdown
from open_model_card.score import score_task
from open_model_card.tasks import TASKS


def task(name):
    return [item for item in TASKS if item["id"] == name][0]


class ScoreTests(unittest.TestCase):
    def test_exact(self):
        row = score_task(task("exact-reply"), "BENCHOK\n")
        self.assertTrue(row["pass"])
        row = score_task(task("exact-reply"), "benchok")
        self.assertFalse(row["pass"])

    def test_json(self):
        row = score_task(task("json-object"), '{"action":"read","path":"notes.md"}')
        self.assertTrue(row["pass"])
        row = score_task(task("json-object"), '{"action":"write","path":"notes.md"}')
        self.assertFalse(row["pass"])

    def test_digits(self):
        row = score_task(task("arithmetic"), "The answer is 391.")
        self.assertTrue(row["pass"])

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

    def test_lines(self):
        row = score_task(task("three-lines"), "- a\n- b\n- c\n")
        self.assertTrue(row["pass"])
        row = score_task(task("three-lines"), "- a\n- b\n")
        self.assertFalse(row["pass"])

    def test_report_names_strength(self):
        row = score_task(task("exact-reply"), "BENCHOK")
        report = build_report({"model": "demo", "base_url": "http://127.0.0.1:9/v1"}, None, [row], {"available": False})
        text = to_markdown(report)
        self.assertIn("demo", text)


def _card(name, replies, tok_s, rss):
    rows = []
    for item in TASKS:
        rows.append(score_task(item, replies.get(item["id"], "BENCHOK")))
    return build_report(
        {"model": name, "base_url": "http://127.0.0.1:9/v1"},
        {"tok_per_s": tok_s, "ttft_s": 1},
        rows,
        {"available": True, "rss_mb": rss, "pids": ["1"]},
    )


class CompareTests(unittest.TestCase):
    def test_jobs_do_not_share_one_winner(self):
        accurate = _card(
            "large",
            {
                "exact-reply": "BENCHOK",
                "json-object": '{"action":"read","path":"notes.md"}',
                "arithmetic": "391",
                "faithful-summary": "March 3 invoice 240",
                "meeting-facts": "Friday, hold the newsletter, budget 50",
                "three-lines": "- a\n- b\n- c",
            },
            tok_s=60,
            rss=28000,
        )
        small = _card(
            "small",
            {
                "exact-reply": "BENCHOK",
                "json-object": "nope",
                "arithmetic": "1",
                "faithful-summary": "April and 500",
                "meeting-facts": "Monday and 100",
                "three-lines": "- a\n- b\n- c",
            },
            tok_s=200,
            rss=3000,
        )
        advice = recommend([accurate, small])
        self.assertEqual(advice["transcripts"]["model"], "large")
        self.assertEqual(advice["operator"]["model"], "large")
        self.assertEqual(advice["cron"]["model"], "small")
        self.assertIn("large", advice["do_not_pair"])


if __name__ == "__main__":
    unittest.main()
