"""Check 0.8 features with Writer and the installed engine in the disposable profile."""

import copy
import faulthandler
import json
import traceback
from unittest.mock import patch

import test_libreoffice as test
import uno
from test_accessibility import wait_for

from libreharp.advanced_ui import AdvancedSettings, StatisticsWindow
from libreharp.ignores import read_ignores
from libreharp.scope_ui import BulkWords, SavedIgnores, Vocabulary
from libreharp.scopes import read_document
from libreharp.store import DEFAULTS
from libreharp.uno_app import PROOFREADER, Review, RuleBrowser, Runtime, units
from libreharp.weir_ui import WeirRules


def choose(window, control, text):
    items = window.model.getByName(control).StringItemList
    window.dialog.getControl(control).selectItemPos(items.index(text), True)


def main():
    ctx = test.start()
    app = Runtime(ctx)
    # The installed component owns the shared native dictionary.
    app.context_menus.sync_words = lambda: None
    app.store.update(lambda data: (data.clear(), data.update(copy.deepcopy(DEFAULTS))))
    app.statistics.clear()
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    proofreader = ctx.ServiceManager.createInstanceWithContext(PROOFREADER, ctx)
    text = "This is a example. This is a example."
    doc, identity = test.bound_document(ctx, locale, text)
    sibling, sibling_id = test.bound_document(ctx, locale, text)
    path = test.ZONE / "features.draft.odt"
    doc.storeAsURL(path.as_uri(), (test.prop("FilterName", "writer8"), test.prop("Overwrite", True)))

    def errors(content, document_id=identity, rule="AnA"):
        result = proofreader.doProofreading(document_id, content, locale, 0, units(content), ())
        return [error for error in result.aErrors if rule is None or error.aRuleIdentifier == rule]

    assert wait_for(lambda: len(errors(text)) == 2)
    browser = RuleBrowser(app, doc)
    browser.show()
    choose(browser, "subset", "New in bundled Harper")
    browser.refresh()
    test.record("Rule browser shows only new Harper rules", len(browser.visible_rules) == 25)
    category = next(rule["category"] for rule in browser.visible_rules if rule["default"])
    choose(browser, "category", category)
    choose(browser, "enabled", "Enabled")
    browser.refresh()
    test.record(
        "Rule filters combine with effective state",
        bool(browser.visible_rules)
        and all(
            rule["category"] == category and rule["default"] and rule["new"] for rule in browser.visible_rules
        ),
    )
    choose(browser, "category", "All categories")
    choose(browser, "enabled", "Any state")
    choose(browser, "subset", "Overrides")
    app.store.set_rule("AnA", True)
    browser.refresh()
    test.record(
        "Overrides filter identifies a saved choice", [r["name"] for r in browser.visible_rules] == ["AnA"]
    )
    choose(browser, "subset", "All rules")

    options = AdvancedSettings(app)
    options.show()
    options.model.getByName("delay_ms").Text = "10"
    options.model.getByName("max_bytes").Text = "1024"
    options.model.getByName("exclude").Text = "*.draft.odt"
    choose(options, "severity", "Warning")
    options.save()
    test.record(
        "Saved filename exclusion only affects the matching document",
        wait_for(lambda: not errors(text)) and len(errors(text, sibling_id)) == 2,
    )
    options.model.getByName("exclude").Text = ""
    options.model.getByName("max_bytes").Text = "12"
    options.save()
    test.record("Maximum size suppresses oversized inline runs", not errors(text, sibling_id))
    options.model.getByName("max_bytes").Text = "120000"
    options.save()
    test.record(
        "An eligible document resumes checking after advanced settings change", len(errors(text)) == 2
    )
    mixed = text + " Il semble important de vérifier toutes les données avant de publier nos résultats."
    before = len(errors(mixed, rule=None))
    options.model.getByName("isolate_english").State = 1
    options.save()
    test.record(
        "Harper isolates English while retaining English grammar findings",
        before > len(errors(mixed, rule=None)) and len(errors(mixed)) == 2,
    )
    options.model.getByName("isolate_english").State = 0
    options.save()

    review = Review(app, doc)
    review.show()
    review.check()
    assert wait_for(lambda: not review.pending and len(review.rows) == 2)
    test.record("Review receives configured Harper severity", review.rows[0][2]["severity"] == "Warning")
    review.dialog.getControl("issues").selectItemPos(1, True)
    review.remember_ignore()
    test.record(
        "Saved ignore suppresses only the matching range and document",
        wait_for(lambda: len(errors(text)) == 1)
        and errors(text)[0].nErrorStart == text.index("a example")
        and len(errors(text, sibling_id)) == 2,
    )
    test.record("Statistics are opt-in", app.statistics.read() == {})
    doc.store()
    review.close()
    browser.close()
    options.close()
    doc.close(True)

    doc = test.desktop.loadComponentFromURL(path.as_uri(), "_blank", 0, (test.prop("Hidden", True),))
    test.record(
        "Saved ignore survives document reopen in separate metadata",
        bool(read_ignores(doc)) and "ignored" not in read_document(doc),
    )
    iterator = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.ProofreadingIterator", ctx
    )

    def writer_result():
        flat = doc.getFlatParagraphIterator(2, False).getFirstPara()
        return iterator.checkSentenceAtPosition(doc, flat, flat.getText(), locale, 0, units(text), 0)

    def writer_errors():
        return [error for error in writer_result().aErrors if error.aRuleIdentifier == "AnA"]

    test.record(
        "Reopened Writer document still suppresses the saved finding",
        wait_for(lambda: len(writer_errors()) == 1),
    )
    manager = SavedIgnores(app, doc)
    manager.show()
    manager.dialog.getControl("ignored").selectItemPos(0, True)
    manager.restore()
    test.record(
        "Restoring an ignore makes both findings available", wait_for(lambda: len(writer_errors()) == 2)
    )
    manager.close()

    incoming = test.ZONE / "incoming-harper-dictionary.txt"
    outgoing = test.ZONE / "outgoing-harper-dictionary.txt"
    incoming.write_text("Homonuclear\nQzxharperprobe\nHomonuclear\n", encoding="utf-8")
    outgoing.unlink(missing_ok=True)
    editor = Vocabulary(app, doc, "document")
    editor.show()
    with patch("libreharp.scope_ui.pick_file", return_value=str(incoming)):
        editor.import_words()
    bulk = next(window for window in app.windows if isinstance(window, BulkWords) and window.parent is editor)
    test.record("Dictionary import previews words before changing scope", not read_document(doc)["words"])
    bulk.save()
    with patch("libreharp.scope_ui.pick_file", return_value=str(outgoing)):
        editor.export_words()
    test.record(
        "Dictionary round trip is deduplicated and scoped",
        outgoing.read_text(encoding="utf-8") == "Homonuclear\nQzxharperprobe\n"
        and not read_document(sibling)["words"]
        and not app.store.read()["words"],
    )
    editor.close()

    options = AdvancedSettings(app)
    options.show()
    options.model.getByName("record_statistics").State = 1
    options.save()
    review = Review(app, doc)
    review.show()
    review.check()
    assert wait_for(lambda: not review.pending and len(review.rows) == 2)
    review.ignore()
    review.apply()
    assert wait_for(lambda: not review.pending)
    review.close()
    counts = StatisticsWindow(app)
    counts.show()
    test.record(
        "Local statistics count explicit actions by rule",
        app.statistics.read() == {"Applied": {"AnA": 1}, "Ignored": {"AnA": 1}}
        and "AnA" in counts.model.getByName("counts").Text,
    )
    counts.close()

    browser = RuleBrowser(app, sibling)
    browser.show()
    weir = WeirRules(browser)
    weir.show()
    weir.example()
    test.record("Weir editor validates and runs both embedded example tests", weir.test()["tests"] == 2)
    original = weir.model.getByName("source").Text
    weir.model.getByName("source").Text = original.replace('let becomes "unique"', 'let becomes "special"')
    try:
        weir.save()
    except ValueError as error:
        test.record(
            "A failing Weir test prevents saving",
            "tests failed" in str(error) and not app.store.read().get("weir"),
        )
    else:
        raise AssertionError("A Weir rule with failing tests was saved")
    weir.model.getByName("source").Text = original
    weir.save()
    rule = "LibreHarp.Weir.UniqueWithoutIntensifier"
    sample = "😀 This is very unique."
    result = errors(sample, sibling_id, rule)
    test.record(
        "Installed Weir bridge emits the exact Writer range and replacement",
        len(result) == 1
        and result[0].nErrorStart == units("😀 This is ")
        and result[0].aSuggestions == ("unique",),
    )
    browser.model.getByName("search").Text = "UniqueWithoutIntensifier"
    browser.refresh()
    assert browser.selected()["name"] == rule
    browser.set(False)
    test.record(
        "Weir rules support document overrides",
        wait_for(lambda: not errors(sample, sibling_id, rule))
        and bool(errors(sample, writer_result().aDocumentIdentifier, rule)),
    )
    weir.close()
    browser.close()
    options.close()
    doc.setModified(False)
    doc.close(True)
    sibling.setModified(False)
    sibling.close(True)


if __name__ == "__main__":
    exit_code = 0
    faulthandler.dump_traceback_later(45)
    try:
        main()
    except Exception:
        traceback.print_exc()
        test.REPORT["errors"].append(traceback.format_exc())
        exit_code = 1
    finally:
        test.stop()
        faulthandler.cancel_dump_traceback_later()
        test.REPORT["passed"] = exit_code == 0
        (test.ZONE / "harper-features-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(exit_code)
