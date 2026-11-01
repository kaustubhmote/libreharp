import unittest
from pathlib import Path

from libreharp.catalog import load_catalog
from libreharp.engine import Engine
from libreharp.rule_help import HELP, finding_text


class HelpTests(unittest.TestCase):
    def test_examples_match_pinned_engine(self):
        engine = Engine(Path(__file__).resolve().parents[1] / "vendor/harper/harper-ls")
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
        rendered = finding_text(text, issue, 2, 3)
        self.assertIn("😀 This is [a] example.", rendered)
        self.assertIn("Finding 2 of 3", rendered)
        self.assertIn("Before: This is a example.", rendered)

    def test_unknown_rule_keeps_engine_explanation_and_no_fix_message(self):
        text = "a" * 1000
        issue = dict(
            start=0, end=1000, text=text, rule="FutureRule", message="Engine explanation.", suggestions=[]
        )
        rendered = finding_text(text, issue, 1, 1)
        self.assertIn("[" + text + "]", rendered)
        self.assertIn("Engine explanation.", rendered)
        self.assertIn("No automatic replacement", rendered)
