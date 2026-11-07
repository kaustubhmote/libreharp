from pathlib import Path

import pytest

from libreharp.bundled import VENDOR
from libreharp.catalog import filter_rules, load_catalog
from libreharp.checker import Checker
from libreharp.ignores import ignore_key
from libreharp.store import Store
from libreharp.weir import EXAMPLE, RULE_PREFIX, WeirEngine, WeirError


def test_catalog_marks_exact_release_additions():
    old = {rule["name"] for rule in load_catalog(VENDOR / "releases" / "3.0.0")}
    catalog = load_catalog(VENDOR / "releases" / "3.1.0")
    new = filter_rules(catalog, {}, subset="New in bundled Harper")
    assert {rule["name"] for rule in new} == {rule["name"] for rule in catalog} - old
    rule = new[0]
    assert filter_rules(
        catalog, {rule["name"]: False}, category=rule["category"], enabled=False, subset="Overrides"
    ) == [rule]


def test_advanced_options_and_document_ignores_do_not_leak_through_cache(tmp_path):
    class Engine:
        version = "test"

        def check(self, text, settings):
            assert settings["maxFileLength"] == 16
            assert settings["isolateEnglish"] is True
            assert settings["diagnosticSeverity"] == "warning"
            return [{"rule": "SpellCheck", "start": 0, "end": 3, "text": text[:3], "suggestions": []}]

    store = Store(tmp_path)
    store.update(
        lambda data: data.update(
            advanced=dict(max_bytes=16, isolate_english=True, severity="Warning", exclude=["*.draft.odt"])
        )
    )
    checker = Checker(store, Engine())
    text = "bad sentence"
    issue = checker.check(text)[0]
    assert issue["severity"] == "Warning"
    assert checker.check(text, overrides={"document_url": "file:///docs/check.draft.odt"}) == []
    assert checker.check("é" * 9) == []
    ignored = {"ignored": {ignore_key(text, issue): "SpellCheck"}}
    assert checker.check(text, overrides=ignored) == []
    assert checker.cached(text, overrides=ignored) == []
    assert checker.check(text) == [issue]


def test_real_weir_parser_suggestions_and_scoped_disable(tmp_path):
    binary = Path(__file__).resolve().parents[1] / "build" / "libreharp-weir"
    if not binary.is_file():
        pytest.skip("Build the Weir helper to exercise Harper's parser.")
    weir = WeirEngine(binary)
    try:
        result = weir.validate("Unique", EXAMPLE)
        assert result["tests"] == 2 and not result["failures"]
        with pytest.raises(WeirError):
            weir.validate("Unique", "expr main [")
        store = Store(tmp_path)
        store.update(
            lambda data: data.update(
                weir={"Unique": {"source": EXAMPLE, "description": result["description"]}}
            )
        )

        class EmptyEngine:
            version = "test"

            def check(self, text, settings):
                return []

        rule = RULE_PREFIX + "Unique"
        text = "😀 This is very unique."
        checker = Checker(store, EmptyEngine(), weir)
        issue = checker.check(text)[0]
        assert issue["rule"] == rule and issue["suggestions"] == ["unique"]
        assert text[issue["start"] : issue["end"]] == "very unique"
        assert checker.check(text, overrides={"rules": {rule: False}}) == []
        assert checker.check(text) == [issue]
        rollback = Checker(store, EmptyEngine())
        warnings = set()
        assert rollback.check(text, warnings=warnings) == [] and warnings
        assert rollback.cached(text) == []
    finally:
        weir.close()
