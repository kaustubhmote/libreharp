import json
import tempfile
import unittest
from pathlib import Path

from libreharp.migration import legacy_rules, word_list
from libreharp.scopes import ProjectStore, empty_scope, merge_scopes, project_path, resolve, validate_scope
from libreharp.store import Store


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root / "personal")

    def test_precedence_and_inherited_vocabulary(self):
        self.store.set_rule("AnA", True)
        self.store.add_word("Personal")
        project = {
            **empty_scope(),
            "rules": {"AnA": False},
            "words": ["Project"],
            "terms": [{"find": "utilize", "replace": "use"}],
        }
        document = {
            **empty_scope(),
            "rules": {"AnA": True},
            "words": ["Document"],
            "terms": [{"find": "utilize", "replace": "employ"}],
        }
        result = self.store.effective(merge_scopes(project, document))
        self.assertTrue(result["rules"]["AnA"])
        self.assertEqual(result["words"], ["Document", "Personal", "Project"])
        self.assertEqual(result["terms"], [{"find": "utilize", "replace": "employ"}])
        self.assertTrue(self.store.effective()["rules"]["AnA"])

    def test_nearest_project_and_sibling_isolation(self):
        outer = self.root / "project/.libreharp.json"
        inner = self.root / "project/sub/.libreharp.json"
        ProjectStore(outer).update(lambda d: d["rules"].update(AnA=False))
        ProjectStore(inner).update(lambda d: d["rules"].update(AnA=True))
        self.assertEqual(project_path((inner.parent / "a.odt").as_uri()), inner)
        self.assertFalse(resolve((outer.parent / "b.odt").as_uri(), empty_scope())[0]["rules"]["AnA"])
        self.assertEqual(resolve((self.root / "outside/c.odt").as_uri(), empty_scope())[0]["rules"], {})

    def test_unsaved_and_remote_documents_have_no_project(self):
        self.assertIsNone(project_path(""))
        self.assertIsNone(project_path("https://example.com/test.odt"))

    def test_project_persistence_and_invalid_file_preserved(self):
        path = self.root / "project/.libreharp.json"
        ProjectStore(path).update(lambda d: d["rules"].update(LongSentences=False))
        self.assertFalse(ProjectStore(path).read()["rules"]["LongSentences"])
        path.write_text("bad json")
        with self.assertRaises(ValueError):
            resolve((path.parent / "a.odt").as_uri(), empty_scope())
        self.assertEqual(path.read_text(), "bad json")

    def test_optional_profile_and_dialect(self):
        prefs = self.store.effective(
            merge_scopes({**empty_scope(), "profile": "Scientific", "dialect": "British"})
        )
        self.assertFalse(prefs["rules"]["LongSentences"])
        self.assertEqual(prefs["dialect"], "British")
        with self.assertRaisesRegex(ValueError, "not available"):
            self.store.effective({"profile": "Missing"})

    def test_invalid_scope_fields_are_rejected(self):
        for field, value in (
            ("sentence_limit", -1),
            ("dialect", "unknown"),
            ("rules", {"AnA": "false"}),
            ("execute", "evil"),
        ):
            with self.assertRaises(ValueError):
                validate_scope({**empty_scope(), field: value})

    def test_migration_keeps_only_recognized_harper_rules(self):
        rules, skipped = legacy_rules(
            json.dumps(
                {
                    "model": "harper",
                    "ignored_rules": ["LongSentences", "harper||AnA", "unknown", "languagetool||AnA"],
                }
            )
        )
        self.assertEqual(rules, ["AnA", "LongSentences"])
        self.assertEqual(len(skipped), 2)
        rules, _ = legacy_rules(
            json.dumps({"model": "languagetool", "ignored_rules": ["LongSentences", "harper||AnA"]})
        )
        self.assertEqual(rules, ["AnA"])

    def test_word_list_import_is_bounded_and_deduplicated(self):
        path = self.root / "words.txt"
        path.write_text("Nmrprobe\nNmrprobe\nSecondword\n")
        self.assertEqual(word_list(path), ["Nmrprobe", "Secondword"])
        path.write_text("word/FLAGS")
        with self.assertRaises(ValueError):
            word_list(path)
