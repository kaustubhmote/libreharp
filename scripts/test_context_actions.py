"""Exercise context-sensitive dictionary actions through the installed sidebar."""

import copy
import json
import traceback

import test_libreoffice as test
import uno
from test_scopes_libreoffice import wait_for

from libreharp.scopes import read_document
from libreharp.sidebar import FACTORY, RESOURCE
from libreharp.store import DEFAULTS, Store

WORD = "Qzxnmrspectroprobe"
docs = []
panels = []


def main():
    ctx = test.start()
    store = Store(test.PROFILE / "user/LibreHarp")
    store.update(lambda d: (d.clear(), d.update(copy.deepcopy(DEFAULTS))))
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    factory = ctx.ServiceManager.createInstanceWithContext(FACTORY, ctx)

    def create():
        doc = test.desktop.loadComponentFromURL(
            "private:factory/swriter", "_blank", 0, (test.prop("Hidden", True),)
        )
        docs.append(doc)
        doc.Text.String = f"The {WORD} works."
        doc.CharLocale = locale
        panel = factory.createUIElement(
            RESOURCE,
            (
                test.prop("Frame", doc.CurrentController.Frame),
                test.prop("ParentWindow", doc.CurrentController.Frame.ContainerWindow),
            ),
        )
        panels.append(panel)
        window = panel.getRealInterface().Window
        window.getControl("auto").getModel().State = 0
        assert wait_for(lambda: window.getControl("run").getModel().Label == "Add ~globally")
        return doc, window

    a, window = create()
    b, sibling = create()

    def model(name):
        return window.getControl(name).getModel()

    def click(name):
        window.getControl(name).getAccessibleContext().doAccessibleAction(0)

    def check(text, marker=None):
        a.Text.String = text
        click("check")
        marker = marker or (f"[{WORD}]" if WORD in text else "[a]")
        assert wait_for(lambda: marker in model("message").Text and "suggestions" in model("status").Text)

    test.record(
        "Spelling finding preselects the global dictionary action",
        window.getControl("more").getSelectedItem() == "Add word globally"
        and window.getControl("scope").getSelectedItemPos() == 0,
    )
    test.record(
        "Dictionary button exposes the exact word and global scope",
        WORD in window.getControl("run").getAccessibleContext().getAccessibleName()
        and "all documents and profiles" in model("run").HelpText,
    )
    before = read_document(a)
    click("run")
    test.record(
        "One native button action saves the global word", wait_for(lambda: WORD in store.read()["words"])
    )
    test.record(
        "Global shortcut leaves selected scope and document settings unchanged",
        window.getControl("scope").getSelectedItemPos() == 0 and read_document(a) == before,
    )
    test.record(
        "Both open sidebars recheck after a global dictionary addition",
        wait_for(lambda: not model("issues").StringItemList)
        and wait_for(lambda: not sibling.getControl("issues").getModel().StringItemList),
    )
    test.record(
        "Empty sidebar retains management actions without finding actions",
        model("more").StringItemList
        == ("More actions...", "Grammar rules", "Document / project settings", "Words and terminology")
        and not model("run").Enabled,
    )
    store.update(lambda d: d["profiles"].update(Scientific=copy.deepcopy(d["profiles"][d["profile"]])))
    test.record(
        "Global dictionary word applies to another profile",
        WORD in store.effective({"profile": "Scientific"})["words"],
    )
    check("This is a example.")
    test.record(
        "Grammar findings omit dictionary actions and do not preselect disabling",
        model("more").StringItemList
        == (
            "More actions...",
            "Show in document",
            "Disable rule",
            "Grammar rules",
            "Document / project settings",
            "Words and terminology",
        )
        and window.getControl("more").getSelectedItemPos() == 0
        and not model("run").Enabled,
    )
    check("The ZqxVocabularyProbe works. This is a example.", "[ZqxVocabularyProbe]")
    click("next")
    test.record(
        "Changing selection to grammar removes the spelling shortcut",
        wait_for(lambda: "[a]" in model("message").Text)
        and "Add word globally" not in model("more").StringItemList,
    )
    click("previous")
    test.record(
        "Returning to a spelling finding restores its one-click shortcut",
        wait_for(lambda: model("run").Label == "Add ~globally")
        and "ZqxVocabularyProbe" in model("run").HelpText,
    )
    # Removing from global vocabulary should restore the spelling finding.
    store.update(lambda d: d.update(words=[]))
    check(f"The {WORD} works.")
    test.record("Spelling shortcut returns when a word is removed", model("run").Label == "Add ~globally")
    a.Text.String = "The instrument works."
    click("run")
    test.record(
        "A stale spelling finding cannot add an old word",
        WORD not in store.read()["words"] and wait_for(lambda: not model("issues").StringItemList),
    )
    check(f"The {WORD} works.")
    window.getControl("more").selectItem("Remember word in selected scope", True)
    click("run")
    test.record(
        "Explicit scoped word action still saves only to the document",
        wait_for(lambda: WORD in read_document(a)["words"]) and WORD not in store.read()["words"],
    )
    sibling.getControl("check").getAccessibleContext().doAccessibleAction(0)
    test.record(
        "Document word does not silence another document",
        wait_for(lambda: bool(sibling.getControl("issues").getModel().StringItemList)),
    )
    sibling.getControl("scope").selectItemPos(1, True)
    sibling.getControl("run").getAccessibleContext().doAccessibleAction(0)
    test.record(
        "Global shortcut works even when project scope is selected on an unsaved document",
        wait_for(lambda: WORD in store.read()["words"]),
    )
    for panel in panels:
        panel.dispose()
    panels.clear()
    for doc in docs:
        doc.close(True)
    docs.clear()
    test.stop()
    ctx = test.start()
    doc, identity = test.bound_document(ctx, locale, f"The {WORD} works.")
    docs.append(doc)
    checker = ctx.ServiceManager.createInstanceWithContext("org.libreharp.Proofreader", ctx)
    result = checker.doProofreading(identity, doc.Text.String, locale, 0, len(doc.Text.String), ())
    test.record(
        "One-click global dictionary addition survives a LibreOffice restart",
        WORD in store.read()["words"] and not any(e.aRuleIdentifier == "SpellCheck" for e in result.aErrors),
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
        for panel in panels:
            panel.dispose()
        for doc in docs:
            doc.close(True)
        test.stop()
        test.REPORT["passed"] = code == 0
        (test.ZONE / "context-actions-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
