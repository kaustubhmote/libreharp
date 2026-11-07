import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from libreharp.catalog import load_catalog
from libreharp.checker import Checker, replacement_is_current
from libreharp.engine import Engine, EngineError, offset
from libreharp.store import Store


class FakeEngine:
    version = "test"

    def __init__(self):
        self.calls = 0

    def check(self, text, settings):
        self.calls += 1
        return [
            {
                "start": 0,
                "end": len(text),
                "text": text,
                "rule": "SpellCheck",
                "message": "Unknown",
                "suggestions": [],
            }
        ]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)

    def test_rule_survives_new_store_and_profile(self):
        self.store.set_rule("LongSentences", False)
        other = Store(self.tmp.name)
        other.update(lambda d: d.update(profile="Scientific"))
        self.assertFalse(other.effective()["rules"]["LongSentences"])

    def test_document_override_isolation(self):
        self.store.set_rule("LongSentences", False)
        self.assertTrue(self.store.effective({"rules": {"LongSentences": True}})["rules"]["LongSentences"])
        self.assertFalse(self.store.effective()["rules"]["LongSentences"])

    def test_dictionary_invalidates_cache(self):
        engine = FakeEngine()
        checker = Checker(self.store, engine)
        self.assertEqual(len(checker.check("Nmrprobe")), 1)
        checker.check("Nmrprobe")
        self.assertEqual(engine.calls, 1)
        self.store.add_word("Nmrprobe")
        self.assertEqual(checker.check("Nmrprobe"), [])
        self.assertEqual(engine.calls, 2)
        self.assertEqual(Store(self.tmp.name).read()["words"], ["Nmrprobe"])

    def test_menu_cache_does_not_start_or_wait_for_engine(self):
        engine = FakeEngine()
        checker = Checker(self.store, engine)
        self.assertIsNone(checker.cached("Nmrprobe"))
        self.assertEqual(engine.calls, 0)
        checker.check("Nmrprobe")
        cached = checker.cached("Nmrprobe")
        cached[0]["text"] = "changed"
        self.assertEqual(checker.cached("Nmrprobe")[0]["text"], "Nmrprobe")
        acquired, release = threading.Event(), threading.Event()

        def hold():
            with checker.lock:
                acquired.set()
                release.wait(2)

        worker = threading.Thread(target=hold)
        worker.start()
        acquired.wait(2)
        try:
            self.assertIsNone(checker.cached("Nmrprobe"))
        finally:
            release.set()
            worker.join()
        self.store.add_word("Nmrprobe")
        self.assertIsNone(checker.cached("Nmrprobe"))

    def test_first_result_is_cached_under_resolved_engine_version(self):
        class StartingEngine(FakeEngine):
            def check(self, text, settings):
                self.version = "resolved"
                return super().check(text, settings)

        checker = Checker(self.store, StartingEngine())
        issues = checker.check("Nmrprobe")
        self.assertEqual(checker.cached("Nmrprobe"), issues)

    def test_atomic_concurrent_updates(self):
        threads = [
            threading.Thread(target=Store(self.tmp.name).add_word, args=(f"word{i}",)) for i in range(12)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(self.store.read()["words"]), 12)

    def test_corrupt_preferences_preserved(self):
        self.store.path.write_text("not json")
        with self.assertRaises(ValueError):
            self.store.add_word("word")
        self.assertEqual(self.store.path.read_text(), "not json")

    def test_import_validation_and_backup(self):
        self.store.add_word("first")
        export = Path(self.tmp.name) / "export.json"
        self.store.export_to(export)
        self.store.add_word("second")
        self.store.import_from(export)
        self.assertEqual(self.store.read()["words"], ["first"])
        backup = json.loads((Path(self.tmp.name) / "preferences.before-import.json").read_text())
        self.assertIn("second", backup["words"])
        data = json.loads(export.read_text())
        data["rules"] = {"Rule": "false"}
        export.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.store.import_from(export)
        self.assertEqual(self.store.read()["words"], ["first"])

    def test_custom_terms_literal_boundaries_and_profile_limit(self):
        def change(d):
            d["terms"] = [{"find": "a+b", "replace": "sum"}]
            d["profiles"]["General"]["sentence_limit"] = 3

        self.store.update(change)
        issues = Checker(self.store, FakeEngine()).check("a+b and xa+b are different.")
        terms = [i for i in issues if i["rule"].startswith("LibreHarp.Term.")]
        self.assertEqual(len(terms), 1)
        self.assertEqual(terms[0]["suggestions"], ["sum"])
        self.assertTrue(any(i["rule"] == "LibreHarp.SentenceLength" for i in issues))

    def test_cache_results_cannot_be_mutated_by_ui(self):
        checker = Checker(self.store, FakeEngine())
        checker.check("word")[0]["suggestions"].append("bad")
        self.assertEqual(checker.check("word")[0]["suggestions"], [])

    def test_stale_replacement(self):
        issue = {"start": 0, "end": 4, "text": "This"}
        self.assertTrue(replacement_is_current("This is.", "This is.", issue))
        self.assertFalse(replacement_is_current("This is.", "This was.", issue))
        self.assertFalse(replacement_is_current("That is.", "That is.", issue))

    def test_utf16_offset(self):
        self.assertEqual(offset("😀 This\nword", {"line": 0, "character": 3}), 2)
        self.assertEqual(offset("😀 This\nword", {"line": 1, "character": 2}), 9)

    def test_missing_engine_is_error(self):
        engine = Engine(Path(self.tmp.name) / "absent", timeout=0.1)
        with self.assertRaises(EngineError):
            engine.check("This is a example.", {})

    def test_rule_catalog_unique_and_known_defaults(self):
        catalog = load_catalog()
        rules = {r["name"]: r for r in catalog}
        self.assertEqual(len(rules), len(catalog))
        self.assertGreater(len(rules), 300)
        self.assertTrue(rules["LongSentences"]["default"])
        self.assertIn("NoOxfordComma", rules["OxfordComma"]["alternatives"])

    def test_oversize_paragraph_is_not_reported_clean(self):
        engine = Engine(Path(self.tmp.name) / "absent")
        with self.assertRaisesRegex(EngineError, "120 KB"):
            engine.check("a" * 120001, {})

    def test_stalled_engine_times_out_and_is_terminated(self):
        binary = Path(self.tmp.name) / "stalled-engine"
        binary.write_text(
            f"#!{sys.executable}\nimport sys\nif '--version' in sys.argv:\n print('stalled 1.0')\nelse:\n sys.stdin.read()\n"
        )
        binary.chmod(0o755)
        engine = Engine(binary, timeout=0.2)
        with self.assertRaisesRegex(EngineError, "timed out"):
            engine.check("This is a example.", {})
        self.assertIsNone(engine.process)

    def test_malformed_profile_rejected_without_write(self):
        before = self.store.read()
        with self.assertRaises(ValueError):
            self.store.update(lambda d: d["profiles"].update(Invalid=None))
        self.assertEqual(self.store.read(), before)
        with self.assertRaises(ValueError):
            self.store.update(lambda d: d["profiles"]["General"].pop("sentence_limit"))
        with self.assertRaises(ValueError):
            self.store.update(lambda d: d.update(terms=[{"find": "foo", "replace": "bar", "message": 12}]))
        self.assertEqual(self.store.read(), before)


class RealEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from libreharp.bundled import engine_directory

        cls.engine = Engine(engine_directory() / "harper-ls")

    @classmethod
    def tearDownClass(cls):
        cls.engine.close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.checker = Checker(self.store, self.engine)

    def test_real_diagnostics_and_replacements(self):
        text = "This is a example. This is is incorrect."
        issues = self.checker.check(text)
        self.assertTrue(issues, "Harper returned no findings")
        self.assertTrue(any("an" in i["suggestions"] for i in issues), issues)
        for issue in issues:
            self.assertEqual(text[issue["start"] : issue["end"]], issue["text"])

    def test_real_rule_disable_and_reenable(self):
        text = "This is a example."
        issues = self.checker.check(text)
        rule = next(i["rule"] for i in issues if "an" in i["suggestions"])
        self.store.set_rule(rule, False)
        self.assertFalse(any(i["rule"] == rule for i in self.checker.check(text)))
        self.store.set_rule(rule, True)
        self.assertTrue(any(i["rule"] == rule for i in self.checker.check(text)))

    def test_non_bmp_code_actions_match_diagnostic(self):
        text = "😀 This is a example."
        issues = self.checker.check(text)
        issue = next(i for i in issues if i["rule"] == "AnA")
        self.assertEqual(issue["text"], "a")
        self.assertIn("an", issue["suggestions"])

    def test_real_personal_dictionary(self):
        text = "Qzxnmrspectroprobe is unusual."
        self.assertTrue(
            any(
                i["rule"] == "SpellCheck" and i["text"] == "Qzxnmrspectroprobe"
                for i in self.checker.check(text)
            )
        )
        self.store.add_word("Qzxnmrspectroprobe")
        self.assertFalse(
            any(
                i["rule"] == "SpellCheck" and i["text"] == "Qzxnmrspectroprobe"
                for i in self.checker.check(text)
            )
        )

    def test_accepted_compounds_keep_other_splitting_and_grammar_checks(self):
        text = "We used homonuclear decoupling and radiofrequency pulses inthe experiment. This is a example."
        before = self.checker.check(text)
        self.assertEqual(
            {i["text"] for i in before if i["rule"] == "SplitWords"},
            {"homonuclear", "radiofrequency", "inthe"},
        )
        self.store.add_word("homonuclear")
        self.store.add_word("radiofrequency")
        after = self.checker.check(text)
        self.assertEqual({i["text"] for i in after if i["rule"] == "SplitWords"}, {"inthe"})
        self.assertTrue(any(i["rule"] == "AnA" for i in after))
        self.assertEqual(self.store.read()["rules"], {})
        other = Checker(Store(self.tmp.name), self.engine)
        self.assertEqual(other.check(text), after)
        self.store.update(lambda data: data.update(words=["radiofrequency"]))
        self.assertTrue(any(i["text"] == "homonuclear" for i in self.checker.check(text)))

    def test_scoped_compound_acceptance_is_exact_and_isolated(self):
        text = "We used homonuclear decoupling and radiofrequency pulses."
        scoped = {"schema": 1, "rules": {}, "words": ["homonuclear"], "terms": []}
        result = self.checker.check(text, overrides=scoped)
        self.assertFalse(any(i["text"] == "homonuclear" for i in result))
        self.assertTrue(any(i["text"] == "radiofrequency" for i in result))
        self.assertTrue(any(i["text"] == "homonuclear" for i in self.checker.check(text)))
        result = self.checker.check("Homonuclear coupling is strong.", overrides=scoped)
        self.assertTrue(any(i["text"] == "Homonuclear" for i in result))
        scoped["words"].append("Homonuclear")
        self.assertFalse(
            any(
                i["text"] == "Homonuclear"
                for i in self.checker.check("Homonuclear coupling is strong.", overrides=scoped)
            )
        )

    def test_restart_and_revision_isolation(self):
        self.engine.close()
        first = self.engine.check("This is a example.", {"linters": {}})
        second = self.engine.check("This is an example.", {"linters": {}})
        self.assertTrue(first)
        self.assertFalse(any("an" in i["suggestions"] for i in second))

    def test_long_sentence_suppression_survives_new_checker(self):
        text = (
            "The researchers collected samples from several different locations across the region and "
            "carefully recorded the temperature and pressure at each site before returning to the "
            "laboratory where they prepared the materials for analysis and compared the results with "
            "previous experiments that had been conducted under similar conditions during the previous year."
        )
        self.assertTrue(any(i["rule"] == "LongSentences" for i in self.checker.check(text)))
        self.store.set_rule("LongSentences", False)
        self.engine.close()
        restarted = Checker(Store(self.tmp.name), self.engine)
        self.assertFalse(any(i["rule"] == "LongSentences" for i in restarted.check(text)))


if __name__ == "__main__":
    unittest.main()
