"""Installed extension checks for native sidebar and document/project isolation."""

import copy
import json
import time
import traceback

import test_libreoffice as test
import uno

from libreharp.scopes import ProjectStore, empty_scope, read_document, write_document
from libreharp.sidebar import FACTORY, RESOURCE
from libreharp.store import DEFAULTS, Store

docs = []


def wait_for(fn, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(0.1)
    return False


def main():
    ctx = test.start()
    store = Store(test.PROFILE / "user/LibreHarp")
    store.update(lambda d: (d.clear(), d.update(copy.deepcopy(DEFAULTS))))
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    iterator = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.ProofreadingIterator", ctx
    )
    root = test.ZONE / "scope-project"
    root.mkdir(exist_ok=True)
    project = root / ".libreharp.json"
    ProjectStore(project).update(lambda d: (d.clear(), d.update(empty_scope())))

    def create(path):
        doc = test.desktop.loadComponentFromURL(
            "private:factory/swriter", "_blank", 0, (test.prop("Hidden", True),)
        )
        docs.append(doc)
        doc.Text.String = "This is a example."
        doc.CharLocale = locale
        doc.storeAsURL(path.as_uri(), (test.prop("FilterName", "writer8"), test.prop("Overwrite", True)))
        return doc

    a = create(root / "a.odt")
    b = create(root / "b.odt")
    c = create(test.ZONE / "outside.odt")

    def result(doc):
        flat = doc.getFlatParagraphIterator(2, False).getFirstPara()
        return iterator.checkSentenceAtPosition(doc, flat, flat.getText(), locale, 0, 100, 8)

    def has_rule(doc):
        return any(e.aRuleIdentifier == "AnA" for e in result(doc).aErrors)

    test.record(
        "Initial documents all use baseline grammar", wait_for(lambda: all(has_rule(d) for d in (a, b, c)))
    )
    test.record(
        "Writer assigns distinct identities to identical text",
        len({result(d).aDocumentIdentifier for d in (a, b, c)}) == 3,
    )
    write_document(a, {**empty_scope(), "rules": {"AnA": False}})
    a.store()
    test.record("Installed inline checker uses embedded document override", wait_for(lambda: not has_rule(a)))
    test.record("Document override does not leak to identical sibling", has_rule(b) and has_rule(c))
    ProjectStore(project).update(lambda d: d["rules"].update(AnA=False))
    test.record("Project settings affect a second document in that folder", wait_for(lambda: not has_rule(b)))
    test.record("Project settings do not affect files outside the project", has_rule(c))
    write_document(a, {**empty_scope(), "rules": {"AnA": True}})
    a.store()
    test.record("Document rule overrides project rule", wait_for(lambda: has_rule(a)))
    test.record("Sibling retains project suppression", not has_rule(b))
    factory = ctx.ServiceManager.createInstanceWithContext(FACTORY, ctx)
    test.record("Installed sidebar factory is registered", factory is not None)
    panel = factory.createUIElement(
        RESOURCE,
        (
            test.prop("Frame", a.CurrentController.Frame),
            test.prop("ParentWindow", a.CurrentController.Frame.ContainerWindow),
        ),
    )
    window = panel.getRealInterface().Window
    accessible = panel.getRealInterface().createAccessible(None)
    test.record(
        "Installed panel exposes its accessible control container",
        accessible.getAccessibleContext().getAccessibleChildCount() > 0,
    )
    window.setPosSize(0, 0, 360, 672, 15)
    test.record(
        "Installed sidebar completes scoped review",
        wait_for(lambda: len(window.getControl("issues").getModel().StringItemList) > 0),
    )
    test.record(
        "Sidebar contains native scope and editing controls",
        window.getControl("scope") is not None and window.getControl("apply") is not None,
    )
    test.record("Sidebar reports its actual document frame", panel.Frame == a.CurrentController.Frame)
    test.record(
        "Sidebar explanation includes context and a verified rule example",
        "This is [a] example." in window.getControl("message").getModel().Text
        and "Before: This is a example." in window.getControl("message").getModel().Text,
    )
    minimum_height = panel.getRealInterface().getHeightForWidth(300).Preferred
    window.setPosSize(0, 0, 300, minimum_height, 15)
    test.record(
        "Sidebar controls fit its preferred height",
        wait_for(lambda: window.getControl("status").getPosSize().Y < minimum_height)
        and window.getControl("status").getPosSize().Y + window.getControl("status").getPosSize().Height
        <= minimum_height,
    )
    short_height = window.getControl("message").getPosSize().Height
    window.setPosSize(0, 0, 420, 800, 15)
    test.record(
        "Additional sidebar height goes to the explanation",
        wait_for(
            lambda: window.getControl("message").getPosSize().Height >= short_height + 800 - minimum_height
        )
        and window.getControl("more").getPosSize().Height
        >= window.getControl("more").getMinimumSize().Height,
    )
    window.getControl("apply").getAccessibleContext().doAccessibleAction(0)
    test.record(
        "Installed sidebar Apply button edits its own document",
        wait_for(lambda: a.Text.String == "This is an example."),
    )
    test.record(
        "Sidebar Apply leaves other documents untouched",
        b.Text.String == "This is a example." and c.Text.String == "This is a example.",
    )
    a.getUndoManager().undo()
    test.record("Installed sidebar edit is undoable", a.Text.String == "This is a example.")
    window.getControl("check").getAccessibleContext().doAccessibleAction(0)
    assert wait_for(lambda: bool(window.getControl("issues").getModel().StringItemList))
    window.getControl("more").selectItemPos(2, True)
    window.getControl("run").getAccessibleContext().doAccessibleAction(0)
    test.record(
        "Compact action menu disables the rule in the selected document scope",
        wait_for(lambda: read_document(a)["rules"].get("AnA") is False) and has_rule(c),
    )
    test.record(
        "Empty sidebar disables Apply and explains its state",
        wait_for(lambda: not window.getControl("apply").getModel().Enabled)
        and "No findings" in window.getControl("message").getModel().Text,
    )
    write_document(a, {**empty_scope(), "rules": {"AnA": True}})
    a.store()
    window.getControl("auto").getModel().State = 0
    a.Text.String = "This is a example. That is a example. Here is a example."
    window.getControl("check").getAccessibleContext().doAccessibleAction(0)
    assert wait_for(lambda: len(window.getControl("issues").getModel().StringItemList) == 3)
    window.getControl("next").getAccessibleContext().doAccessibleAction(0)
    assert wait_for(lambda: "Finding 2 of 3" in window.getControl("message").getModel().Text)
    window.getControl("next").getAccessibleContext().doAccessibleAction(0)
    test.record(
        "Navigation shows the selected finding and disables Next at the end",
        wait_for(
            lambda: (
                "Finding 3 of 3" in window.getControl("message").getModel().Text
                and not window.getControl("next").getModel().Enabled
            )
        ),
    )
    window.getControl("ignore").getAccessibleContext().doAccessibleAction(0)
    test.record(
        "Ignoring the last finding retains the nearest remaining selection",
        wait_for(
            lambda: (
                window.getControl("issues").getSelectedItemPos() == 1
                and "Finding 2 of 2" in window.getControl("message").getModel().Text
            )
        ),
    )
    a.Text.String = "This is a example."
    a.store()
    panel.dispose()
    a.close(True)
    docs.remove(a)
    reopened = test.desktop.loadComponentFromURL(
        (root / "a.odt").as_uri(), "_blank", 0, (test.prop("Hidden", True),)
    )
    docs.append(reopened)
    test.record(
        "Document settings survive ODT close and reopen", read_document(reopened)["rules"]["AnA"] is True
    )
    test.record("Reopened document rebinds to inline checker", wait_for(lambda: has_rule(reopened)))
    b.storeAsURL(
        (test.ZONE / "moved-outside.odt").as_uri(),
        (test.prop("FilterName", "writer8"), test.prop("Overwrite", True)),
    )
    test.record("Save As outside project drops old project settings", wait_for(lambda: has_rule(b)))
    for doc in list(docs):
        doc.close(True)
    docs.clear()
    test.stop()
    ctx = test.start()
    iterator = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.ProofreadingIterator", ctx
    )
    reopened_a = test.desktop.loadComponentFromURL(
        (root / "a.odt").as_uri(), "_blank", 0, (test.prop("Hidden", True),)
    )
    reopened_b = test.desktop.loadComponentFromURL(
        (root / "b.odt").as_uri(), "_blank", 0, (test.prop("Hidden", True),)
    )
    docs.extend((reopened_a, reopened_b))

    def ready(doc):
        return any(p.Name == "LibreHarp.ScopeReady" and p.Value for p in result(doc).aProperties)

    test.record(
        "Document and project scopes survive LibreOffice restart",
        wait_for(
            lambda: (
                ready(reopened_a) and ready(reopened_b) and has_rule(reopened_a) and not has_rule(reopened_b)
            )
        ),
    )


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Exception:
        code = 1
        test.REPORT["errors"].append(traceback.format_exc())
        traceback.print_exc()
    finally:
        for doc in docs:
            try:
                doc.close(True)
            except Exception:
                pass
        test.stop()
        test.REPORT["passed"] = code == 0
        (test.ZONE / "scopes-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
