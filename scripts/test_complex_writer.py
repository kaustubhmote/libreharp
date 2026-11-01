"""Regression tests for fields, nested tables, existing redlines, and DOCX metadata."""

import copy
import json
import time
import traceback

import test_libreoffice as test
import uno

from libreharp.scopes import empty_scope, read_document, write_document
from libreharp.store import DEFAULTS
from libreharp.uno_app import Review, Runtime, apply_replacement, language_runs, paragraphs

documents = []


def new_document(text):
    doc = test.desktop.loadComponentFromURL(
        "private:factory/swriter", "_blank", 0, (test.prop("Hidden", True),)
    )
    documents.append(doc)
    doc.Text.String = text
    doc.CharLocale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    return doc


def review_rows(app, document, timeout=30):
    review = Review(app, document)
    review.show()
    review.check()
    deadline = time.monotonic() + timeout
    while review.pending and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not review.pending, "Review timed out"
    assert not review.model.getByName("status").Text.startswith("Check failed"), review.model.getByName(
        "status"
    ).Text
    result = review.rows
    review.close()
    return result


def main():
    ctx = test.start()
    app = Runtime(ctx)
    app.store.update(lambda d: (d.clear(), d.update(copy.deepcopy(DEFAULTS))))
    try:
        test_fields(app)
        test_tables(app)
        test_docx(app)
        test_redlines(app)
        test_large_document(app)
    finally:
        app.engine.close()


def test_fields(app):
    doc = new_document("This is a example before the field: ")
    field = doc.createInstance("com.sun.star.text.TextField.Input")
    field.Content = "a example"
    doc.Text.insertTextContent(doc.Text.End, field, False)
    doc.Text.insertString(doc.Text.End, " and this is a example after the field.", False)
    paragraph = next(paragraphs(doc))
    original = paragraph.String
    field_begin = len("This is a example before the field: ")
    field_end = field_begin + len(field.Content)
    runs = language_runs(paragraph)
    test.record(
        "Field contents are excluded from English review runs",
        len(runs) == 2 and runs[0][1] == field_begin and runs[1][0] == field_end,
    )
    rows = review_rows(app, doc)
    articles = [row for row in rows if row[2]["rule"] == "AnA"]
    test.record("Review finds prose errors on both sides of a field", len(articles) == 2)
    after = next(row for row in articles if row[2]["start"] > field_end)
    apply_replacement(doc, *after, "an")
    test.record(
        "Replacement after a field uses the correct native range",
        doc.Text.String.endswith("and this is an example after the field.") and field.Content == "a example",
    )
    doc.getUndoManager().undo()
    field = doc.TextFields.createEnumeration().nextElement()
    paragraph = next(paragraphs(doc))
    test.record(
        "Undo preserves field content and paragraph text",
        doc.Text.String == original and field.Content == "a example",
    )
    issue = dict(start=field_begin, end=field_begin + 1, text="a")
    try:
        apply_replacement(doc, paragraph, original, issue, "an")
        raise AssertionError("Field replacement was accepted")
    except ValueError:
        test.record("Direct replacement cannot overwrite a field", doc.Text.String == original)


def test_tables(app):
    doc = new_document("A table follows.\n")
    outer = doc.createInstance("com.sun.star.text.TextTable")
    outer.initialize(2, 2)
    doc.Text.insertTextContent(doc.Text.End, outer, False)
    cursor = outer.createCursorByCellName("A1")
    cursor.gotoCellByName("B1", True)
    assert cursor.mergeRange()
    outer.getCellByName("A1").String = "The merged cell is a example."
    cell = outer.getCellByName("A2")
    inner = doc.createInstance("com.sun.star.text.TextTable")
    inner.initialize(1, 1)
    cell.insertTextContent(cell.End, inner, False)
    inner.getCellByName("A1").String = "The nested cell is a example."
    rows = review_rows(app, doc)
    for name in ("merged", "nested"):
        matches = [r for r in rows if r[1] == f"The {name} cell is a example." and r[2]["rule"] == "AnA"]
        test.record(f"Review checks the {name} table cell once", len(matches) == 1)
        apply_replacement(doc, *matches[0], "an")
        target = outer if name == "merged" else inner
        test.record(
            f"Replacement in the {name} cell preserves table structure",
            target.getCellByName("A1").String == f"The {name} cell is an example."
            and len(outer.getCellNames()) == 3
            and len(inner.getCellNames()) == 1,
        )
        doc.getUndoManager().undo()
        test.record(
            f"Undo restores the {name} cell",
            target.getCellByName("A1").String == f"The {name} cell is a example.",
        )


def test_docx(app):
    doc = new_document("This is a example.")
    settings = {
        **empty_scope(),
        "rules": {"AnA": False, "LongSentences": False},
        "words": ["Qzxprobe", "Échantillon"],
        "terms": [{"find": "utilize", "replace": "use"}],
        "dialect": "British",
        "sentence_limit": 40,
    }
    write_document(doc, settings)
    path = test.ZONE / "scoped-roundtrip.docx"
    doc.storeAsURL(
        path.as_uri(), (test.prop("FilterName", "Office Open XML Text"), test.prop("Overwrite", True))
    )
    doc.close(True)
    documents.remove(doc)
    reopened = test.desktop.loadComponentFromURL(path.as_uri(), "_blank", 0, (test.prop("Hidden", True),))
    documents.append(reopened)
    test.record("DOCX round trip preserves all embedded scope settings", read_document(reopened) == settings)
    test.record(
        "Reopened DOCX applies its saved rule suppression",
        not any(r[2]["rule"] == "AnA" for r in review_rows(app, reopened)),
    )


def test_redlines(app):
    doc = new_document("The old sample is ready.\nThis is a example.")
    doc.RecordChanges = True
    cursor = doc.Text.createTextCursor()
    cursor.goRight(4, False)
    cursor.goRight(3, True)
    cursor.String = "new"
    count = doc.Redlines.Count
    assert count > 0
    rows = review_rows(app, doc)
    target = next(r for r in rows if "This is a example." in r[1] and r[2]["rule"] == "AnA")
    apply_replacement(doc, *target, "an")
    test.record("Replacement adds tracking without accepting existing redlines", doc.Redlines.Count > count)
    doc.getUndoManager().undo()
    test.record("Undo retains the pre-existing tracked changes", doc.Redlines.Count == count)


def test_large_document(app):
    doc = new_document("")
    doc.lockControllers()
    try:
        cursor = doc.Text.createTextCursor()
        for index in range(1000):
            if index:
                doc.Text.insertControlCharacter(cursor, 0, False)  # PARAGRAPH_BREAK
            doc.Text.insertString(cursor, f"Sample {index} is a example.", False)
        doc.CharLocale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    finally:
        doc.unlockControllers()
    test.record(
        "Large-document fixture contains 1000 actual Writer paragraphs", len(list(paragraphs(doc))) == 1000
    )
    start = time.monotonic()
    rows = review_rows(app, doc, timeout=90)
    elapsed = time.monotonic() - start
    test.REPORT["measurements"] = {"paragraphs": 1000, "review_seconds": round(elapsed, 3)}
    test.record("Review completes 1000 distinct paragraphs", sum(r[2]["rule"] == "AnA" for r in rows) == 1000)


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
        (test.ZONE / "complex-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
