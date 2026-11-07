"""Context-menu targeting and actions against real Writer ranges in an isolated profile."""

import copy
import json
import traceback

import test_libreoffice as test
import uno

from libreharp.context_menu import GRAMMAR_MENU, SPELL_MENU, Finding, selected_paragraph
from libreharp.scopes import ProjectStore, read_document
from libreharp.store import DEFAULTS, Store
from libreharp.uno_app import Runtime, paragraphs


class Menu:
    def __init__(self):
        self.items = []

    @property
    def Count(self):
        return len(self.items)

    def setName(self, name):
        self.name = name

    def getName(self):
        return self.name

    def createInstance(self, name):
        return Menu()

    def setPropertyValue(self, name, value):
        setattr(self, name, value)

    @property
    def PropertySetInfo(self):
        return self

    def hasPropertyByName(self, name):
        return hasattr(self, name)

    def getPropertyValue(self, name):
        return getattr(self, name)

    def getByIndex(self, index):
        return self.items[index]

    def insertByIndex(self, index, item):
        self.items.insert(index, item)

    def removeByIndex(self, index):
        self.items.pop(index)


def group_item(container, heading, label):
    active = False
    for index in range(container.Count):
        item = container.getByIndex(index)
        text = getattr(item, "Text", "")
        if not text.startswith(("  ├─ ", "  └─ ")):
            active = text == heading
        elif active and text[5:] == label:
            return item
    raise AssertionError(f"Missing {heading}: {label}")


def main():
    ctx = test.start()
    app = Runtime(ctx)
    app.store.update(lambda d: (d.clear(), d.update(copy.deepcopy(DEFAULTS))))
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    text = "😀 This is a example. The Qzxcontextprobe works."
    doc, identity = test.bound_document(ctx, locale, text)
    other, _ = test.bound_document(ctx, locale, text)
    controller = doc.CurrentController
    app.bindings.refresh()
    interceptor = next(i for i in app.context_menus.interceptors if i.controller == controller)
    paragraph = next(paragraphs(doc))
    issues = app.checker.check(text, "US", app.bindings.for_document(doc))
    spelling = next(i for i in issues if i["text"] == "Qzxcontextprobe")
    grammar = next(i for i in issues if i["rule"] == "AnA")

    def select(issue):
        cursor = doc.Text.createTextCursorByRange(paragraph.Start)
        cursor.goRight(issue["start"], False)
        cursor.goRight(issue["end"] - issue["start"], True)
        controller.select(cursor)

    def menu(name=SPELL_MENU):
        container = Menu()
        container.setName(name)
        old = Menu()
        old.Text, old.CommandURL = "Original", ".uno:Copy"
        container.insertByIndex(0, old)
        result = interceptor.populate(container)
        return container, result

    def labels(container):
        return [getattr(container.getByIndex(i), "Text", "") for i in range(container.Count)]

    select(spelling)
    snap = selected_paragraph(controller)
    test.record(
        "Popup targets the selected occurrence after a non-BMP character",
        snap[2:] == (spelling["start"], spelling["end"]),
    )
    container, result = menu()
    names = labels(container)
    test.record(
        "Spelling popup replaces native actions",
        result.value == "CONTINUE_MODIFIED" and "Original" not in names,
    )
    test.record(
        "Spelling popup groups one-click word actions under one heading",
        group_item(container, "Remember word", "Globally").CommandURL
        and group_item(container, "Remember word", "In this document").CommandURL,
    )
    test.record(
        "Groups stay flat without submenus or a suggestion card",
        not any(getattr(item, "SubContainer", None) is not None for item in container.items)
        and "Review suggestion…" not in names,
    )
    before = app.store.read()
    for item in container.items:
        if getattr(item, "Text", "") in ("Replace", "Remember word", "Disable rule"):
            app.context_menus.execute(item.CommandURL.split(":", 1)[1], controller.Frame)
    test.record(
        "Group headings leave text and preferences unchanged",
        doc.Text.String == text and app.store.read() == before,
    )
    test.record("Unsaved documents omit project actions", not any("project" in n for n in names))
    entry = Finding(interceptor, paragraph, text, spelling, SPELL_MENU)
    app.context_menus.execute(
        group_item(container, "Remember word", "In this document").CommandURL.split(":", 1)[1],
        controller.Frame,
    )
    test.record(
        "Document word action preserves personal and sibling dictionaries",
        spelling["text"] in read_document(doc)["words"]
        and spelling["text"] not in app.store.read()["words"]
        and spelling["text"] not in read_document(other)["words"],
    )
    entry.word("global")
    test.record("Global word action persists", spelling["text"] in Store(app.store.directory).read()["words"])
    dictionaries = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.DictionaryList", ctx
    )
    test.record(
        "Global words also reach Writer spelling",
        dictionaries.getDictionaryByName("LibreHarp personal words").getEntry(spelling["text"]) is not None,
    )
    select(grammar)
    app.checker.check(text, "US", app.bindings.for_document(doc))
    container, result = menu(GRAMMAR_MENU)
    names = labels(container)
    test.record(
        "Grammar popup omits word actions",
        "Remember word" not in names,
    )
    test.record(
        "Grammar popup offers direct grouped scopes and a short Ignore once label",
        "Ignore once" in names
        and group_item(container, "Disable rule", "Globally").CommandURL
        and group_item(container, "Disable rule", "In this document").CommandURL,
    )
    container, _ = menu("private:resource/popupmenu/text")
    test.record(
        "Ordinary text menus retain their original commands", labels(container) == ["LibreHarp", "Original"]
    )
    # Execute the actual captured action, with frame verification.
    container, _ = menu(GRAMMAR_MENU)
    command = group_item(container, "Replace", '"an"').CommandURL
    app.context_menus.execute(command.split(":", 1)[1], other.CurrentController.Frame)
    test.record(
        "A command cannot act through a different document frame",
        doc.Text.String == text and other.Text.String == text,
    )
    container, _ = menu(GRAMMAR_MENU)
    command = group_item(container, "Replace", '"an"').CommandURL
    app.context_menus.execute(command.split(":", 1)[1], controller.Frame)
    test.record(
        "Popup suggestion edits its captured range",
        doc.Text.String == text.replace("a example", "an example"),
    )
    doc.UndoManager.undo()
    test.record("Popup suggestion supports Undo", doc.Text.String == text)
    paragraph = next(paragraphs(doc))
    entry = Finding(interceptor, paragraph, text, grammar, GRAMMAR_MENU)
    folder = test.ZONE / "menu-project"
    folder.mkdir(exist_ok=True)
    project = ProjectStore(folder / ".libreharp.json")
    project.update(lambda data: data.update(rules={}))
    doc.storeAsURL((folder / "menu.odt").as_uri(), (test.prop("Overwrite", True),))
    app.bindings.refresh()
    select(grammar)
    app.checker.check(text, "US", app.bindings.for_document(doc))
    container, _ = menu(GRAMMAR_MENU)
    app.context_menus.execute(
        group_item(container, "Disable rule", "In this project").CommandURL.split(":", 1)[1],
        controller.Frame,
    )
    test.record(
        "Project branch saves only the project rule choice",
        project.read()["rules"].get("AnA") is False
        and "AnA" not in read_document(doc)["rules"]
        and "AnA" not in app.store.read()["rules"],
    )
    project.update(lambda data: data.update(rules={}))
    app.bindings.refresh()
    select(grammar)
    app.checker.check(text, "US", app.bindings.for_document(doc))
    container, _ = menu(GRAMMAR_MENU)
    app.context_menus.execute(
        group_item(container, "Disable rule", "In this document").CommandURL.split(":", 1)[1],
        controller.Frame,
    )
    test.record(
        "Document rule action preserves sibling and global choices",
        read_document(doc)["rules"].get("AnA") is False
        and "AnA" not in read_document(other)["rules"]
        and "AnA" not in app.store.read()["rules"],
    )
    entry.disable("global")
    test.record("Global rule action persists", Store(app.store.directory).read()["rules"].get("AnA") is False)
    doc.Text.String = "This paragraph changed."
    before = app.store.read()
    try:
        entry.disable("global")
        raise AssertionError("Stale finding was accepted")
    except ValueError:
        test.record("Stale menu actions refuse preference changes", app.store.read() == before)
    # Tables use a different XText, so resolving by document-wide offsets is wrong.
    table = doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(1, 2)
    doc.Text.insertTextContent(doc.Text.End, table, False)
    cell = table.getCellByName("A1")
    cell.String = "This is a example."
    c = cell.createTextCursor()
    c.goRight(8, False)
    c.goRight(1, True)
    controller.select(c)
    snap = selected_paragraph(controller)
    test.record("Popup resolves a table cell independently of body text", snap[1:] == (cell.String, 8, 9))
    app.store.update(lambda data: data.update(words=[]))
    app.changed()
    test.record(
        "Removing a global word also removes its Writer mirror",
        dictionaries.getDictionaryByName("LibreHarp personal words").getEntry(spelling["text"]) is None,
    )
    app.bindings.refresh()
    test.record(
        "Bindings attach one interceptor per Writer controller", len(app.context_menus.interceptors) == 2
    )
    doc.close(True)
    other.close(True)
    app.bindings.refresh()
    test.record(
        "Closed documents release interceptors and commands",
        not app.context_menus.interceptors and not app.context_menus.commands,
    )
    app.engine.close()


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Exception:
        code = 1
        test.REPORT["errors"].append(traceback.format_exc())
        traceback.print_exc()
    finally:
        test.stop()
        test.REPORT["passed"] = code == 0
        (test.ZONE / "context-menu-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
