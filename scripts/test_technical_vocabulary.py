"""Technical-word exceptions through installed sidebar actions and native vocabulary dialogs."""

import copy
import json
import subprocess
import traceback

import test_libreoffice as test
import uno
from test_context_menu import Menu, group_item
from test_scopes_libreoffice import wait_for

from libreharp.context_menu import GRAMMAR_MENU, Finding
from libreharp.scope_ui import BulkWords, Vocabulary
from libreharp.scopes import ProjectStore, read_document
from libreharp.sidebar import FACTORY, RESOURCE
from libreharp.store import DEFAULTS, Store
from libreharp.uno_app import PROOFREADER, Runtime, paragraphs

TEXT = "We used homonuclear decoupling and radiofrequency pulses inthe experiment. This is a example."
windows, panels, documents = [], [], []


def main():
    ctx = test.start(visible=True)
    app = Runtime(ctx)
    # The installed runtime owns Writer's shared dictionary. This extra runtime
    # exercises source-level scope actions over the UNO bridge; mirroring from
    # both runtimes can deadlock a remote dictionary.clear() notification.
    app.context_menus.sync_words = lambda: None
    app.store.update(lambda data: (data.clear(), data.update(copy.deepcopy(DEFAULTS))))
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    factory = ctx.ServiceManager.createInstanceWithContext(FACTORY, ctx)
    proofreader = ctx.ServiceManager.createInstanceWithContext(PROOFREADER, ctx)

    def create(text=TEXT):
        doc, identity = test.bound_document(ctx, locale, text)
        documents.append(doc)
        panel = factory.createUIElement(
            RESOURCE,
            (
                test.prop("Frame", doc.CurrentController.Frame),
                test.prop("ParentWindow", doc.CurrentController.Frame.ContainerWindow),
            ),
        )
        panels.append(panel)
        ui = panel.getRealInterface().Window
        ui.getControl("auto").getModel().State = 0
        assert wait_for(lambda: "suggestions" in ui.getControl("status").getModel().Text)
        return doc, identity, ui

    def errors(identity):
        return proofreader.doProofreading(identity, TEXT, locale, 0, len(TEXT), ()).aErrors

    a, aid, panel = create()
    b, bid, sibling = create()
    test.record(
        "Split-word finding exposes the installed global dictionary shortcut",
        panel.getControl("run").getModel().Label == "Add ~globally"
        and "homonuclear" in panel.getControl("message").getModel().Text,
    )
    panel.getControl("run").getAccessibleContext().doAccessibleAction(0)
    test.record(
        "Installed shortcut saves the exact compound without disabling its rule",
        wait_for(lambda: "homonuclear" in app.store.read()["words"]) and app.store.read()["rules"] == {},
    )
    test.record(
        "Global compound acceptance refreshes both installed sidebars",
        wait_for(
            lambda: all(
                not any("homonuclear" in label for label in ui.getControl("issues").getModel().StringItemList)
                for ui in (panel, sibling)
            )
        ),
    )
    test.record(
        "Other split words and grammar errors remain flagged",
        any(e.aRuleIdentifier == "AnA" for e in errors(aid))
        and any(
            e.aRuleIdentifier == "SplitWords"
            and TEXT[e.nErrorStart : e.nErrorStart + e.nErrorLength] == "inthe"
            for e in errors(aid)
        ),
    )

    # Exercise menu actions against real Writer ranges with a controlled container.
    controller = a.CurrentController
    uid = str(a.RuntimeUID)
    app.bindings.refresh()
    interceptor = next(i for i in app.context_menus.interceptors if i.uid == uid)
    paragraph = next(paragraphs(a))
    finding = next(
        i
        for i in app.checker.check(TEXT, "US", app.bindings.for_document(a))
        if i["text"] == "radiofrequency"
    )
    cursor = a.Text.createTextCursorByRange(paragraph.Start)
    cursor.goRight(finding["start"], False)
    cursor.goRight(finding["end"] - finding["start"], True)
    controller.select(cursor)
    menu = Menu()
    menu.setName(GRAMMAR_MENU)
    interceptor.populate(menu)
    test.record(
        "Split-word popup offers direct grouped global and document acceptance",
        group_item(menu, "Remember word", "Globally").CommandURL
        and group_item(menu, "Remember word", "In this document").CommandURL,
    )
    command = group_item(menu, "Remember word", "In this document").CommandURL.split(":", 1)[1]
    app.context_menus.execute(command, controller.Frame)
    assert wait_for(lambda: "radiofrequency" in read_document(a)["words"])
    test.record(
        "Popup scoped acceptance saves only to its document",
        "radiofrequency" in read_document(a)["words"]
        and "radiofrequency" not in read_document(b)["words"]
        and "radiofrequency" not in app.store.read()["words"],
    )
    test.record(
        "Inline scoped compound acceptance leaves the sibling flagged",
        wait_for(
            lambda: (
                not any(
                    TEXT[e.nErrorStart : e.nErrorStart + e.nErrorLength] == "radiofrequency"
                    for e in errors(aid)
                )
            )
        )
        and any(
            TEXT[e.nErrorStart : e.nErrorStart + e.nErrorLength] == "radiofrequency" for e in errors(bid)
        ),
    )
    stale = Finding(interceptor, paragraph, TEXT, finding, GRAMMAR_MENU)
    a.Text.String = "This paragraph changed."
    before = app.store.read()
    try:
        stale.word("global")
        raise AssertionError("Stale split-word action was accepted")
    except ValueError:
        test.record(
            "Stale split-word actions cannot change the global vocabulary", app.store.read() == before
        )

    def editor(document, kind):
        parent = Vocabulary(app, document, kind)
        parent.show()
        windows.append(parent)
        parent.dialog.getControl("word_list").getAccessibleContext().doAccessibleAction(0)
        assert wait_for(lambda: any(isinstance(w, BulkWords) and w.parent is parent for w in app.windows)), (
            parent.model.getByName("status").Text
        )
        bulk = next(w for w in app.windows if isinstance(w, BulkWords) and w.parent is parent)
        windows.append(bulk)
        return parent, bulk

    parent, bulk = editor(b, "global")
    test.record(
        "Bulk entry exposes an accessible multiline field",
        bulk.dialog.getControl("word_list").getAccessibleContext().getAccessibleName()
        == "Words to add, one per line"
        and bulk.model.getByName("word_list").MultiLine,
    )
    bulk.model.getByName("word_list").Text = "radiofrequency\nradiofrequency\nHomonuclear\n"
    # Closing the vocabulary editor also releases its list dialog.
    parent.close()
    test.record("Closing the vocabulary editor closes its bulk-entry dialog", bulk.closed)
    parent, bulk = editor(b, "global")
    bulk.model.getByName("word_list").Text = "radiofrequency\nradiofrequency\nHomonuclear\n"
    bulk.dialog.getControl("add_words").getAccessibleContext().doAccessibleAction(0)
    assert wait_for(lambda: "unique words" in bulk.model.getByName("status").Text)
    test.record(
        "Bulk global acceptance merges unique words and preserves other preferences",
        set(app.store.read()["words"]) == {"homonuclear", "radiofrequency", "Homonuclear"}
        and app.store.read()["rules"] == {},
    )
    test.record(
        "Successful bulk entry clears the field and reports the unique count",
        bulk.model.getByName("word_list").Text == ""
        and "2 unique words" in bulk.model.getByName("status").Text,
    )
    bulk.model.getByName("word_list").Text = "newterm\nradio frequency"
    before = app.store.read()
    bulk.dialog.getControl("add_words").getAccessibleContext().doAccessibleAction(0)
    assert wait_for(lambda: "one word" in bulk.model.getByName("status").Text)
    test.record(
        "Invalid pasted list does not partially save or discard input",
        app.store.read() == before
        and "radio frequency" in bulk.model.getByName("word_list").Text
        and "one word" in bulk.model.getByName("status").Text,
    )
    bulk.model.getByName("word_list").Text = "homonuclear\nradiofrequency\nHomonuclear"
    bulk.status("Ready to add words. Existing words are kept.")
    # Keep a visual record of the actual native dialog.
    bulk.dialog.getPeer().toFront()
    subprocess.run(["import", "-window", "root", str(test.ZONE / "bulk-words.png")], check=True, timeout=15)
    bulk.close()

    parent, bulk = editor(b, "document")
    bulk.model.getByName("word_list").Text = "Qzxdocumentword\nQzxdocumentword"
    bulk.save()
    test.record(
        "Bulk document vocabulary remains scoped and prompts saving",
        "Qzxdocumentword" in read_document(b)["words"]
        and "Qzxdocumentword" not in app.store.read()["words"]
        and "Save the document" in bulk.model.getByName("status").Text,
    )
    bulk.close()
    parent.close()
    project = test.ZONE / "technical-vocabulary-project"
    project.mkdir(exist_ok=True)
    b.storeAsURL((project / "sample.odt").as_uri(), (test.prop("Overwrite", True),))
    parent, bulk = editor(b, "project")
    bulk.model.getByName("word_list").Text = "Qzxprojectword\nQzxprojectsecond"
    bulk.save()
    saved = ProjectStore(project / ".libreharp.json").read()
    test.record(
        "Bulk project vocabulary persists separately from global and document lists",
        {"Qzxprojectword", "Qzxprojectsecond"} <= set(saved["words"])
        and "Qzxprojectword" not in app.store.read()["words"]
        and "Qzxprojectword" not in read_document(b)["words"],
    )
    for window in list(windows):
        window.close()
    for item in panels:
        item.dispose()
    panels.clear()
    for doc in documents:
        doc.close(True)
    documents.clear()
    app.engine.close()
    test.stop()
    ctx = test.start()
    doc, identity = test.bound_document(ctx, locale, TEXT)
    documents.append(doc)
    checker = ctx.ServiceManager.createInstanceWithContext(PROOFREADER, ctx)
    result = checker.doProofreading(identity, TEXT, locale, 0, len(TEXT), ())
    terms = {TEXT[e.nErrorStart : e.nErrorStart + e.nErrorLength] for e in result.aErrors}
    test.record(
        "Accepted compounds persist after restarting the installed extension",
        not {"homonuclear", "radiofrequency"} & terms
        and "inthe" in terms
        and any(e.aRuleIdentifier == "AnA" for e in result.aErrors),
    )
    test.record(
        "A fresh preference store retains all bulk global words",
        set(Store(test.PROFILE / "user/LibreHarp").read()["words"])
        == {"homonuclear", "radiofrequency", "Homonuclear"},
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
        for window in windows:
            window.close()
        for panel in panels:
            panel.dispose()
        for doc in documents:
            doc.close(True)
        test.stop()
        test.REPORT["passed"] = code == 0
        (test.ZONE / "technical-vocabulary-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
