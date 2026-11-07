"""Writer context menus, with commands bound to immutable finding snapshots."""

import copy
import uuid

import uno
import unohelper
from com.sun.star.lang import XEventListener
from com.sun.star.ui import XContextMenuInterceptor

from .checker import replacement_is_current
from .scopes import ScopeTarget, local_path
from .vocabulary import is_word_finding

SPELL_MENU = "private:resource/SpellContextMenu"
GRAMMAR_MENU = "private:resource/GrammarContextMenu"


def action(value):
    return uno.Enum("com.sun.star.ui.ContextMenuInterceptorAction", value)


def selected_paragraph(controller):
    """Use Writer's popup selection, including text in tables and notes."""
    selection = controller.getSelection()
    if not hasattr(selection, "getCount") or selection.getCount() != 1:
        return None
    selected = selection.getByIndex(0)
    if not hasattr(selected, "getText"):
        return None
    text = selected.Text
    cursor = text.createTextCursorByRange(selected.Start)
    cursor.gotoStartOfParagraph(False)
    start = cursor.Start
    cursor.gotoRange(selected.Start, True)
    begin = len(cursor.String)
    cursor.gotoRange(start, False)
    cursor.gotoRange(selected.End, True)
    end = len(cursor.String)
    cursor.gotoRange(start, False)
    cursor.gotoEndOfParagraph(True)
    enum = cursor.createEnumeration()
    if not enum.hasMoreElements():
        return None
    paragraph = enum.nextElement()
    if not paragraph.supportsService("com.sun.star.text.Paragraph"):
        return None
    original = paragraph.String
    if end > len(original) or original[begin:end] != selected.String:
        return None
    return paragraph, original, begin, end


class ContextMenus:
    def __init__(self, app):
        self.app = app
        self.interceptors = []
        self.commands = {}
        self.words = None

    def sync_words(self):
        """Mirror personal words in an in-memory Writer dictionary, rebuilt on startup."""
        from .uno_app import service

        words = set(self.app.store.read()["words"])
        if words == self.words:
            return
        dictionaries = service(self.app.ctx, "linguistic2.DictionaryList")
        name = "LibreHarp personal words"
        dictionary = dictionaries.getDictionaryByName(name)
        if dictionary is None:
            dictionary = dictionaries.createDictionary(
                name,
                uno.createUnoStruct("com.sun.star.lang.Locale"),
                uno.Enum("com.sun.star.linguistic2.DictionaryType", "POSITIVE"),
                "",
            )
            dictionaries.addDictionary(dictionary)
        dictionary.setActive(False)
        dictionary.clear()
        for word in sorted(words):
            dictionary.add(word, False, "")
        dictionary.setActive(True)
        self.words = words

    def attach(self, controller):
        if any(item.controller == controller for item in self.interceptors):
            return
        interceptor = Interceptor(self, controller)
        controller.registerContextMenuInterceptor(interceptor)
        controller.addEventListener(interceptor)
        self.interceptors.append(interceptor)

    def forget(self, interceptor):
        self.commands = {k: v for k, v in self.commands.items() if v[0] is not interceptor}
        if interceptor in self.interceptors:
            self.interceptors.remove(interceptor)

    def prune(self, live_uids):
        for item in tuple(self.interceptors):
            if item.uid not in live_uids:
                self.forget(item)
                try:
                    item.controller.releaseContextMenuInterceptor(item)
                    item.controller.removeEventListener(item)
                except Exception:
                    pass

    def command(self, interceptor, callback):
        token = "context/" + uuid.uuid4().hex
        self.commands[token] = (interceptor, callback)
        return "org.libreharp:" + token

    def execute(self, token, frame):
        entry = self.commands.pop(token, None)
        if entry is None:
            return
        interceptor, callback = entry
        if frame is None or frame != interceptor.controller.Frame:
            return
        try:
            callback()
        except ValueError as exc:
            from .uno_app import service

            box = service(self.app.ctx, "awt.Toolkit").createMessageBox(
                frame.ContainerWindow,
                uno.Enum("com.sun.star.awt.MessageBoxType", "INFOBOX"),
                1,
                "LibreHarp",
                str(exc),
            )
            box.execute()
            box.dispose()


class Interceptor(unohelper.Base, XContextMenuInterceptor, XEventListener):
    def __init__(self, owner, controller):
        self.owner, self.app, self.controller = owner, owner.app, controller
        self.document = controller.Model
        self.uid = str(self.document.RuntimeUID)

    def disposing(self, event):
        self.owner.forget(self)

    def notifyContextMenuExecute(self, event):
        try:
            return self.populate(event.ActionTriggerContainer)
        except Exception:
            self.app.log_error()
            return action("IGNORED")

    def populate(self, container):
        from .uno_app import language_runs

        self.owner.commands = {k: v for k, v in self.owner.commands.items() if v[0] is not self}
        snapshot = selected_paragraph(self.controller)
        if snapshot is None:
            return action("IGNORED")
        paragraph, original, begin, end = snapshot
        runs = language_runs(paragraph)
        if not any(a <= begin < b and end <= b for a, b, _ in runs):
            return action("IGNORED")
        name = container.getName()
        linguistic = name in (SPELL_MENU, GRAMMAR_MENU)
        overrides = self.app.bindings.for_document(self.document)
        findings, pending = [], False
        for a, b, country in runs:
            if not (a <= begin < b and end <= b):
                continue
            cached = self.app.checker.cached(original[a:b], country, overrides)
            if cached is None:
                pending = True
                continue
            for issue in cached:
                issue["start"] += a
                issue["end"] += a
                if (begin == end and issue["start"] <= begin < issue["end"]) or (
                    begin < end and max(begin, issue["start"]) < min(end, issue["end"])
                ):
                    findings.append(issue)
        if not findings and not linguistic:
            return action("IGNORED")
        menu = container.createInstance("com.sun.star.ui.ActionTriggerContainer")

        def add(target, label, callback=None, submenu=None):
            item = container.createInstance("com.sun.star.ui.ActionTrigger")
            item.setPropertyValue("Text", label.replace("~", "~~"))
            item.setPropertyValue("CommandURL", self.owner.command(self, callback) if callback else "")
            if submenu is not None:
                item.setPropertyValue("SubContainer", submenu)
            target.insertByIndex(target.Count, item)

        def separate():
            item = container.createInstance("com.sun.star.ui.ActionTriggerSeparator")
            item.setPropertyValue("SeparatorType", 0)
            menu.insertByIndex(menu.Count, item)

        def group(label, choices):
            if not choices:
                return
            # These are flat menu rows, not nested submenus. Each branch keeps
            # its own immutable finding/scope callback and takes one click.
            # Writer drops rows with no command, including section labels.
            # A no-op keeps the heading visible without changing the document.
            add(menu, label, lambda: None)
            for index, (text, callback) in enumerate(choices):
                branch = "└─" if index == len(choices) - 1 else "├─"
                add(menu, "  " + branch + " " + text, callback)

        def sidebar():
            from .sidebar import open_sidebar

            open_sidebar(self.app, self.controller.Frame)

        readonly = self.document.isReadonly()
        project = bool(local_path(self.document.URL))
        for index, issue in enumerate(findings):
            if index:
                separate()
            entry = Finding(self, paragraph, original, copy.deepcopy(issue), name)
            title = (
                '"' + issue["text"] + '"'
                if issue["rule"] == "SpellCheck"
                else issue["message"].splitlines()[0]
            )
            add(menu, "LibreHarp: " + title[:100], sidebar)
            if not readonly:
                group(
                    "Replace",
                    [
                        (
                            '"' + replacement + '"' if replacement else "Delete this text",
                            lambda value=replacement, e=entry: e.replace(value),
                        )
                        for replacement in issue["suggestions"]
                    ],
                )
                add(menu, "Ignore once", entry.ignore)
            if is_word_finding(issue):
                words = [("Globally", lambda e=entry: e.word("global"))]
                if not readonly:
                    words.append(("In this document", lambda e=entry: e.word("document")))
                if project:
                    words.append(("In this project", lambda e=entry: e.word("project")))
                group("Remember word", words)
            rules = []
            if not readonly:
                rules.append(("In this document", lambda e=entry: e.disable("document")))
            if project:
                rules.append(("In this project", lambda e=entry: e.disable("project")))
            rules.append(("Globally", lambda e=entry: e.disable("global")))
            group("Disable rule", rules)
        if not findings:
            add(menu, "LibreHarp: check in sidebar" if pending else "LibreHarp: no finding here", sidebar)
        separate()
        add(menu, "Open sidebar", sidebar)
        from .scope_ui import Vocabulary
        from .uno_app import RuleBrowser

        add(menu, "Words and terminology…", lambda: Vocabulary(self.app, self.document).show())
        add(menu, "Manage rules…", lambda: RuleBrowser(self.app, self.document).show())
        if linguistic:
            # Keep tracked-change actions, which may share a spelling popup.
            retained = []
            for index in range(container.Count):
                item = container.getByIndex(index)
                if item.PropertySetInfo.hasPropertyByName("CommandURL") and item.getPropertyValue(
                    "CommandURL"
                ) in (
                    ".uno:AcceptTrackedChange",
                    ".uno:RejectTrackedChange",
                    ".uno:NextTrackedChange",
                    ".uno:PreviousTrackedChange",
                ):
                    retained.append(item)
            # Build everything first so a failure leaves the original popup usable.
            while container.Count:
                container.removeByIndex(container.Count - 1)
            for i in range(menu.Count):
                container.insertByIndex(container.Count, menu.getByIndex(i))
            for item in retained:
                container.insertByIndex(container.Count, item)
        else:
            item = container.createInstance("com.sun.star.ui.ActionTrigger")
            item.setPropertyValue("Text", "LibreHarp")
            item.setPropertyValue("SubContainer", menu)
            container.insertByIndex(0, item)
        return action("CONTINUE_MODIFIED")


class Finding:
    def __init__(self, interceptor, paragraph, original, issue, menu_name):
        self.interceptor, self.paragraph, self.original, self.issue = interceptor, paragraph, original, issue
        self.app, self.document = interceptor.app, interceptor.document
        self.menu_name = menu_name

    def validate(self):
        if not replacement_is_current(self.original, self.paragraph.String, self.issue):
            raise ValueError("This paragraph changed. Right-click the finding again.")

    def replace(self, replacement):
        from .uno_app import apply_replacement

        self.validate()
        apply_replacement(self.document, self.paragraph, self.original, self.issue, replacement)
        self.app.changed()

    def word(self, scope):
        self.validate()
        if not is_word_finding(self.issue):
            raise ValueError("Only spelling or word-splitting findings can be added to the dictionary.")
        word = self.issue["text"]
        if scope == "global":
            self.app.store.add_word(word)
            self.app.changed()
        else:
            ScopeTarget(self.app, self.document, scope).update(
                lambda data: data.update(words=sorted(set(data.get("words", [])) | {word}))
            )

    def disable(self, scope):
        self.validate()
        rule = self.issue["rule"]
        if scope == "global":
            self.app.store.set_rule(rule, False)
            self.app.changed()
        else:
            ScopeTarget(self.app, self.document, scope).update(
                lambda data: data.setdefault("rules", {}).update({rule: False})
            )

    def ignore(self):
        """Use Writer's occurrence-specific marker; never disable the entire rule."""
        from .uno_app import service

        self.validate()
        cursor = self.paragraph.Text.createTextCursorByRange(self.paragraph.Start)
        for distance, expand in (
            (self.issue["start"], False),
            (self.issue["end"] - self.issue["start"], True),
        ):
            while distance:
                step = min(distance, 32767)
                if not cursor.goRight(step, expand):
                    raise ValueError("Could not locate this finding. Right-click it again.")
                distance -= step
        if cursor.String != self.issue["text"]:
            raise ValueError("Could not locate this finding. Right-click it again.")
        prop = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
        prop.Name = "Type"
        # Writer can put both spell and proofreading marks on this occurrence.
        kinds = ("Spelling", "Grammar") if self.menu_name == SPELL_MENU else ("Grammar",)
        for kind in kinds:
            self.interceptor.controller.select(cursor)
            prop.Value = kind
            service(self.app.ctx, "frame.DispatchHelper").executeDispatch(
                self.interceptor.controller.Frame, ".uno:SpellCheckIgnore", "", 0, (prop,)
            )
        for window in tuple(self.app.windows):
            if getattr(window, "document", None) == self.document and hasattr(window, "rows"):
                window.rows = [
                    row
                    for row in window.rows
                    if not (row[0] == self.paragraph and row[1] == self.original and row[2] == self.issue)
                ]
                window.display()
