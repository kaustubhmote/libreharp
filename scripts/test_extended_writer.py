"""Real Writer coverage for text containers, languages and native editors."""

import json
import time
import traceback

import test_libreoffice as test
import uno

from libreharp.migration import LEGACY_PROPERTY
from libreharp.migration_ui import Migration
from libreharp.scope_ui import ScopedSettings, Vocabulary
from libreharp.scopes import read_document, write_document
from libreharp.uno_app import Review, RuleBrowser, Runtime, apply_replacement, language_runs, paragraphs

documents = []


def wait_review(review):
    review.show()
    review.check()
    deadline = time.monotonic() + 20
    while review.pending and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not review.pending, "Review timed out"


def main():
    ctx = test.start()
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    doc, _ = test.bound_document(ctx, locale, "The body is a example.")
    documents.append(doc)
    app = Runtime(ctx)
    frame = doc.createInstance("com.sun.star.text.TextFrame")
    frame.AnchorType = uno.Enum("com.sun.star.text.TextContentAnchorType", "AT_PARAGRAPH")
    frame.Width, frame.Height = 6000, 1500
    doc.Text.insertTextContent(doc.Text.End, frame, False)
    frame.Text.String = "The frame is a example."
    note = doc.createInstance("com.sun.star.text.Footnote")
    doc.Text.insertTextContent(doc.Text.End, note, False)
    note.String = "The footnote is a example."
    endnote = doc.createInstance("com.sun.star.text.Endnote")
    doc.Text.insertTextContent(doc.Text.End, endnote, False)
    endnote.String = "The endnote is a example."
    style = doc.StyleFamilies.getByName("PageStyles").getByName("Standard")
    style.HeaderIsOn = True
    style.FooterIsOn = True
    style.HeaderText.String = "The header is a example."
    style.FooterText.String = "The footer is a example."
    strings = [p.String for p in paragraphs(doc)]
    for name in ("frame", "footnote", "endnote", "header", "footer"):
        test.record(
            f"Traversal includes {name} exactly once", strings.count(f"The {name} is a example.") == 1
        )
    review = Review(app, doc)
    wait_review(review)
    for name in ("frame", "footnote", "endnote", "header", "footer"):
        test.record(
            f"Harper review finds grammar in {name}",
            any(
                original == f"The {name} is a example." and issue["rule"] == "AnA"
                for _, original, issue in review.rows
            ),
        )
    paragraph, original, issue = next(
        row for row in review.rows if row[1] == "The footnote is a example." and row[2]["rule"] == "AnA"
    )
    apply_replacement(doc, paragraph, original, issue, "an")
    test.record(
        "Footnote replacement edits only its own text",
        note.String == "The footnote is an example." and frame.Text.String == "The frame is a example.",
    )
    doc.getUndoManager().undo()
    test.record("Footnote replacement supports Undo", note.String == "The footnote is a example.")
    review.close()
    test_editors(ctx, app, locale, doc)
    app.engine.close()


def test_editors(ctx, app, locale, other):
    mixed, _ = test.bound_document(ctx, locale, "This is a example. Bonjour le monde.")
    documents.append(mixed)
    french = mixed.Text.createTextCursor()
    french.goRight(len("This is a example. "), False)
    french.gotoEnd(True)
    french.CharLocale = uno.createUnoStruct("com.sun.star.lang.Locale", "fr", "FR", "")
    runs = language_runs(next(paragraphs(mixed)))
    test.record(
        "Mixed-language review isolates the English portion", runs == [(0, len("This is a example. "), "US")]
    )
    review = Review(app, mixed)
    wait_review(review)
    test.record(
        "Mixed-language review keeps correct offsets",
        any(i["rule"] == "AnA" and i["start"] == 8 for _, _, i in review.rows)
        and all(i["end"] <= len("This is a example. ") for _, _, i in review.rows),
    )
    review.close()
    scoped = ScopedSettings(app, mixed)
    scoped.show()
    stale = ScopedSettings(app, mixed)
    stale.show()
    scoped.model.getByName("rules").Text = "LongSentences=false"
    scoped.save()
    test.record(
        "Native scope editor writes embedded rules", read_document(mixed)["rules"]["LongSentences"] is False
    )
    scoped.dialog.getControl("scope").selectItemPos(1, True)
    try:
        scoped.save()
        raise AssertionError("Unloaded scope wrote to the old target")
    except ValueError:
        test.record("Changing scope requires loading its settings before saving")
    scoped.dialog.getControl("scope").selectItemPos(0, True)
    rules = RuleBrowser(app, mixed)
    rules.show()
    rules.model.getByName("search").Text = "LongSentences"
    rules.refresh()
    test.record(
        "Document rule browser defaults to document scope",
        rules.dialog.getControl("scope").getSelectedItemPos() == 2,
    )
    test.record(
        "Rule browser identifies the winning scope",
        "document override" in rules.model.getByName("detail").Text,
    )
    rules.close()
    try:
        stale.save()
        raise AssertionError("Stale editor overwrote settings")
    except ValueError:
        test.record("Stale scoped editor preserves newer changes")
    scoped.close()
    stale.close()
    words = Vocabulary(app, mixed, "document")
    words.show()
    words.model.getByName("word").Text = "Qzxscopeprobe"
    words.add_word()
    words.model.getByName("find").Text = "utilize"
    words.model.getByName("replacement").Text = "use"
    words.add_term()
    data = read_document(mixed)
    test.record(
        "Dedicated editor saves words and terminology",
        "Qzxscopeprobe" in data["words"] and {"find": "utilize", "replace": "use"} in data["terms"],
    )
    test.record("Document vocabulary stays isolated", "Qzxscopeprobe" not in read_document(other)["words"])
    words.close()
    data = read_document(mixed)
    data["rules"]["AnA"] = True
    write_document(mixed, data)
    legacy = json.dumps({"model": "harper", "ignored_rules": ["LongSentences", "AnA", "harper||SpellCheck"]})
    mixed.DocumentProperties.UserDefinedProperties.addProperty(LEGACY_PROPERTY, 128, legacy)
    dictionary = test.ZONE / "legacy-words.txt"
    dictionary.write_text("Qzxlegacyword\nNmrlegacyprobe\n")
    migration = Migration(app, mixed)
    migration.show()
    migration.model.getByName("path").Text = str(dictionary)
    migration.preview()
    test.record(
        "Migration previews recognized legacy rules and words",
        len(migration.rules) == 3 and len(migration.words) == 2,
    )
    dictionary.write_text("Qzxlegacyword\nNmrlegacyprobe\nChangedsource\n")
    try:
        migration.import_words()
        raise AssertionError("Changed import source was accepted")
    except ValueError:
        test.record("Migration requires a fresh preview after source changes")
    migration.preview()
    migration.import_words()
    migration.import_rules()
    test.record(
        "Migration merges words and backs up personal settings",
        "Qzxlegacyword" in app.store.read()["words"]
        and bool(list(app.store.directory.glob("preferences.before-migration-*.json"))),
    )
    migrated = read_document(mixed)
    test.record(
        "Migration preserves newer document choices",
        migrated["rules"]["AnA"] is True and migrated["rules"]["SpellCheck"] is False,
    )
    test.record(
        "Migration preserves legacy metadata",
        mixed.DocumentProperties.UserDefinedProperties.getPropertyValue(LEGACY_PROPERTY) == legacy,
    )
    migration.close()
    tracked, _ = test.bound_document(ctx, locale, "This is a example.")
    documents.append(tracked)
    tracked.RecordChanges = True
    apply_replacement(
        tracked, next(paragraphs(tracked)), tracked.Text.String, {"start": 8, "end": 9, "text": "a"}, "an"
    )
    test.record("Replacement honors Writer track-changes mode", tracked.Redlines.Count > 0)
    tracked.getUndoManager().undo()
    test.record("Tracked replacement supports Undo", tracked.Text.String == "This is a example.")
    large, _ = test.bound_document(ctx, locale, "This is a example.")
    documents.append(large)
    large.Text.String = "\n".join(f"Sample {i} is a example." for i in range(100))
    large.CharLocale = locale
    review = Review(app, large)
    wait_review(review)
    test.record(
        "Review completes a 100-line document", sum(i["rule"] == "AnA" for _, _, i in review.rows) == 100
    )
    large.Text.String = "The latest version is a example."
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if (
            review.rows
            and not review.pending
            and all(original == large.Text.String for _, original, _ in review.rows)
        ):
            break
        time.sleep(0.1)
    test.record(
        "Long-document results refresh after replacement",
        bool(review.rows) and all(original == large.Text.String for _, original, _ in review.rows),
    )
    review.close()


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Exception:
        code = 1
        test.REPORT["errors"].append(traceback.format_exc())
        traceback.print_exc()
    finally:
        for doc in documents:
            try:
                doc.close(True)
            except Exception:
                pass
        test.stop()
        test.REPORT["passed"] = code == 0
        (test.ZONE / "extended-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
