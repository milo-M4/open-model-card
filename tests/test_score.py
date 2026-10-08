import unittest

from open_model_card.report import build_report, to_markdown
from open_model_card.score import score_task
from open_model_card.tasks import TASKS


class ScoreTests(unittest.TestCase):
    def test_exact(self):
        row = score_task(TASKS[0], "BENCHOK\n")
        self.assertTrue(row["pass"])
        row = score_task(TASKS[0], "benchok")
        self.assertFalse(row["pass"])

    def test_json(self):
        row = score_task(TASKS[1], 'Sure: {"action":"read","path":"notes.md"}')
        self.assertTrue(row["pass"])
        row = score_task(TASKS[1], '{"action":"write","path":"notes.md"}')
        self.assertFalse(row["pass"])

    def test_digits(self):
        row = score_task(TASKS[2], "The answer is 391.")
        self.assertTrue(row["pass"])
        row = score_task(TASKS[2], "390")
        self.assertFalse(row["pass"])

    def test_facts(self):
        row = score_task(TASKS[3], "On March 3 the invoice was $240.")
        self.assertTrue(row["pass"])
        row = score_task(TASKS[3], "On April 3 the invoice was $240.")
        self.assertFalse(row["pass"])

    def test_lines(self):
        row = score_task(TASKS[4], "- a\n- b\n- c\n")
        self.assertTrue(row["pass"])
        row = score_task(TASKS[4], "- a\n- b\n")
        self.assertFalse(row["pass"])

    def test_report_names_strength(self):
        rows = [score_task(task, "BENCHOK") for task in TASKS]
        rows[0]["pass"] = True
        rows[0]["area"] = "instruction following"
        report = build_report({"model": "demo", "base_url": "http://127.0.0.1:9/v1"}, None, [rows[0]], {"available": False})
        text = to_markdown(report)
        self.assertIn("instruction following", text)
        self.assertIn("demo", text)


if __name__ == "__main__":
    unittest.main()
