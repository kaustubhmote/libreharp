import unittest

from libreharp.bundled import engine_directory
from libreharp.catalog import load_catalog
from libreharp.engine import Engine
from libreharp.rule_help import HELP, finding_text


class HelpTests(unittest.TestCase):
    def test_examples_match_pinned_engine(self):
        engine = Engine(engine_directory() / "harper-ls")
        self.addCleanup(engine.close)
        catalog = {rule["name"]: rule for rule in load_catalog()}
        for name, (_, before, after) in HELP.items():
            with self.subTest(rule=name):
                self.assertIn(name, catalog)
                rules = {alternative: False for alternative in catalog[name]["alternatives"]}
                rules[name] = True
                self.assertTrue(any(i["rule"] == name for i in engine.check(before, {"linters": rules})))
                self.assertFalse(any(i["rule"] == name for i in engine.check(after, {"linters": rules})))

    def test_context_keeps_unicode_and_entire_finding(self):
        text = "😀 This is a example."
        issue = dict(start=10, end=11, text="a", rule="AnA", message="Incorrect article.", suggestions=["an"])
        rendered, (begin, end), (fix_begin, fix_end) = finding_text(text, issue, 2, 3, "an")
        self.assertIn("In your text\n😀 This is a example.", rendered)
        self.assertEqual(rendered[begin:end], "a")
        self.assertTrue(rendered[:begin].endswith("😀 This is "))
        self.assertEqual(rendered[fix_begin:fix_end], "an")
        self.assertTrue(rendered[:fix_begin].endswith("Suggested replacement\n"))
        self.assertIn("Finding 2 of 3", rendered)
        self.assertIn("Before: This is a example.", rendered)

    def test_unknown_rule_keeps_engine_explanation_and_no_fix_message(self):
        text = "a" * 1000
        issue = dict(
            start=0, end=1000, text=text, rule="FutureRule", message="Engine explanation.", suggestions=[]
        )
        rendered, (begin, end), replacement = finding_text(text, issue, 1, 1, None)
        self.assertEqual(rendered[begin:end], text)
        self.assertIsNone(replacement)
        self.assertIn("Engine explanation.", rendered)
        self.assertIn("No automatic replacement", rendered)

    def test_insertion_point_and_removal_preview(self):
        issue = dict(start=4, end=4, text="", rule="Comma", message="Insert a comma.", suggestions=[","])
        rendered, (begin, end), (fix_begin, fix_end) = finding_text("Well then.", issue, 1, 1, ",")
        self.assertIn("Well▏ then.", rendered)
        self.assertEqual(rendered[begin:end], "▏")
        self.assertEqual(rendered[fix_begin:fix_end], ",")
        issue.update(start=5, end=9, text="then", suggestions=[""])
        rendered, _, (begin, end) = finding_text("Well then.", issue, 1, 1, "")
        self.assertEqual(rendered[begin:end], "Remove flagged text")
