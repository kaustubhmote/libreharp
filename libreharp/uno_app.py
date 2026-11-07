"""Native Writer integration. All document reads and edits run on the UI thread."""

import threading
import traceback
from pathlib import Path

import uno
import unohelper
from com.sun.star.awt import XActionListener, XCallback, XItemListener, XTopWindowListener
from com.sun.star.frame import XDispatch, XDispatchProvider
from com.sun.star.lang import XInitialization, XServiceDisplayName, XServiceInfo
from com.sun.star.linguistic2 import XLinguServiceEventBroadcaster, XProofreader
from com.sun.star.util import XModifyListener

from . import __version__, accessibility, layout
from .bundled import WEIR_BINARY, engine_directory, engine_metadata
from .catalog import filter_rules, load_catalog
from .checker import Checker, replacement_is_current
from .engine import Engine
from .ignores import ignore_key, update_ignores
from .rule_help import explanation
from .statistics import Statistics
from .store import Store, fingerprint
from .vocabulary import is_word_finding
from .weir import RULE_PREFIX, WeirEngine

ROOT = Path(__file__).resolve().parent.parent
PROOFREADER = "org.libreharp.Proofreader"
PROTOCOL = "org.libreharp.ProtocolHandler"
_runtime = None
_runtime_lock = threading.RLock()


def service(ctx, name):
    return ctx.ServiceManager.createInstanceWithContext("com.sun.star." + name, ctx)


def units(text):
    return len(text.encode("utf-16-le")) // 2


class Runtime:
    def __init__(self, ctx):
        self.ctx = ctx
        user = service(ctx, "util.PathSubstitution").substituteVariables("$(user)", True)
        self.store = Store(Path(uno.fileUrlToSystemPath(user)) / "LibreHarp")
        self.statistics = Statistics(self.store.directory)
        directory = engine_directory()
        metadata = engine_metadata(directory)
        self.engine = Engine(directory / "harper-ls", data_dir=self.store.directory / "engine")
        self.weir = None
        if "weir_core_commit" in metadata:
            bridge = (
                ROOT / "build" / WEIR_BINARY
                if directory.parent.name == "releases"
                else directory / WEIR_BINARY
            )
            self.weir = WeirEngine(bridge)
        self.checker = Checker(self.store, self.engine, self.weir, metadata)
        self.proofreaders = []
        self.windows = []
        from .context_menu import ContextMenus

        self.context_menus = ContextMenus(self)
        from .bindings import Bindings

        self.bindings = Bindings(self)

    def log_error(self):
        # No paragraph text is logged. Tracebacks help distinguish engine/UI failures.
        with (self.store.directory / "errors.log").open("a") as stream:
            stream.write(traceback.format_exc() + "\n")

    def changed(self):
        self.context_menus.sync_words()
        for proofreader in self.proofreaders:
            proofreader.recheck()
        for window in tuple(self.windows):
            if isinstance(window, Review) and not window.closed:
                window.check()

    def record(self, action, issue):
        try:
            if self.store.advanced()["record_statistics"]:
                self.statistics.record(action, issue["rule"])
        except Exception:
            self.log_error()


def runtime(ctx):
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = Runtime(ctx)
        return _runtime


class Proofreader(
    unohelper.Base, XProofreader, XServiceInfo, XServiceDisplayName, XLinguServiceEventBroadcaster
):
    def __init__(self, ctx):
        self.app = runtime(ctx)
        self.listeners = []
        self.ignored = set()
        self.app.proofreaders.append(self)

    def getImplementationName(self):
        return PROOFREADER

    def supportsService(self, name):
        return name in self.getSupportedServiceNames()

    def getSupportedServiceNames(self):
        return ("com.sun.star.linguistic2.Proofreader",)

    def getServiceDisplayName(self, locale):
        return "LibreHarp"

    def getLocales(self):
        return tuple(
            uno.createUnoStruct("com.sun.star.lang.Locale", "en", c, "")
            for c in ("US", "GB", "AU", "CA", "IN")
        )

    def hasLocale(self, locale):
        return locale.Language == "en" and locale.Country in ("", "US", "GB", "AU", "CA", "IN")

    def isSpellChecker(self):
        return False

    def addLinguServiceEventListener(self, listener):
        if listener not in self.listeners:
            self.listeners.append(listener)
        return True

    def removeLinguServiceEventListener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)
        return True

    def recheck(self):
        event = uno.createUnoStruct("com.sun.star.linguistic2.LinguServiceEvent")
        event.Source = self
        event.nEvent = uno.getConstantByName(
            "com.sun.star.linguistic2.LinguServiceEventFlags.PROOFREAD_AGAIN"
        )
        for listener in tuple(self.listeners):
            try:
                listener.processLinguServiceEvent(event)
            except Exception:
                self.listeners.remove(listener)

    def ignoreRule(self, rule, locale):
        # The UNO callback provides no reliable document identity. Never guess it.
        self.ignored.add(rule)
        self.recheck()

    def resetIgnoreRules(self):
        self.ignored.clear()
        self.recheck()

    def doProofreading(self, document, text, locale, start, suggested_end, properties):
        result = uno.createUnoStruct("com.sun.star.linguistic2.ProofreadingResult")
        result.aDocumentIdentifier, result.aText, result.aLocale = document, text, locale
        result.nStartOfSentencePosition = start
        result.nStartOfNextSentencePosition = units(text)
        result.nBehindEndOfSentencePosition = units(text)
        result.xProofreader = self
        result.aProperties = properties
        errors = []
        try:
            if self.hasLocale(locale):
                overrides = self.app.bindings.for_id(document)
                ready = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
                ready.Name, ready.Value = "LibreHarp.ScopeReady", overrides is not None
                result.aProperties = tuple(properties) + (ready,)
                if overrides is None:
                    # A first check establishes the document handshake. Never publish
                    # personal defaults as if they were this document's scoped result.
                    result.aErrors = ()
                    return result
                for issue in self.app.checker.check(text, locale.Country, overrides):
                    if issue["rule"] in self.ignored or units(text[: issue["start"]]) < start:
                        continue
                    error = uno.createUnoStruct("com.sun.star.linguistic2.SingleProofreadingError")
                    error.nErrorStart = units(text[: issue["start"]])
                    error.nErrorLength = units(issue["text"])
                    error.nErrorType = uno.getConstantByName("com.sun.star.text.TextMarkupType.PROOFREADING")
                    error.aRuleIdentifier = issue["rule"]
                    error.aShortComment = issue["message"].split("\n")[0]
                    error.aFullComment = issue["message"]
                    error.aSuggestions = tuple(issue["suggestions"])
                    errors.append(error)
        except Exception:
            self.app.log_error()
        result.aErrors = tuple(errors)
        return result


class Callback(unohelper.Base, XCallback):
    def __init__(self, fn):
        self.fn = fn

    def notify(self, data):
        self.fn()


class Action(unohelper.Base, XActionListener):
    def __init__(self, owner, fn):
        self.owner, self.fn = owner, fn

    def actionPerformed(self, event):
        try:
            self.fn()
        except ValueError as exc:
            self.owner.status(str(exc))
            layout.focus_control(self.owner, "status")
        except Exception as exc:
            self.owner.status(str(exc))
            layout.focus_control(self.owner, "status")
            self.owner.app.log_error()

    def disposing(self, event):
        pass


class Selection(unohelper.Base, XItemListener):
    def __init__(self, owner, fn):
        self.owner, self.fn = owner, fn

    def itemStateChanged(self, event):
        try:
            self.fn()
        except ValueError:
            pass
        except Exception:
            self.owner.app.log_error()

    def disposing(self, event):
        pass


class Closing(unohelper.Base, XTopWindowListener):
    def __init__(self, owner):
        self.owner = owner

    def windowClosing(self, event):
        self.owner.close()

    def windowOpened(self, event):
        pass

    def windowClosed(self, event):
        pass

    def windowMinimized(self, event):
        pass

    def windowNormalized(self, event):
        pass

    def windowActivated(self, event):
        pass

    def windowDeactivated(self, event):
        pass

    def disposing(self, event):
        pass


class Modify(unohelper.Base, XModifyListener):
    def __init__(self, owner):
        self.owner = owner

    def modified(self, event):
        self.owner.modified()

    def disposing(self, event):
        self.owner.close()


class Window:
    def __init__(self, app, title, width=370, height=280):
        self.app, self.ctx = app, app.ctx
        self.model = service(self.ctx, "awt.UnoControlDialogModel")
        self.model.Title, self.model.Width, self.model.Height = title, width, height
        self.dialog = service(self.ctx, "awt.UnoControlDialog")
        self.dialog.setModel(self.model)
        self.actions = []
        self.closed = False
        self.control_names = []
        self.mnemonics = set()
        self.return_focus = accessibility.current_focus(app)

    def add(self, name, kind, x, y, width, height, **props):
        if name == "status":
            kind = "Edit"
            props.update(
                Text=props.pop("Label", ""),
                ReadOnly=True,
                MultiLine=True,
                VScroll=True,
                Border=0,
                HelpText="Status and errors. Press F8 to read this field.",
            )
        if kind == "Button":
            props["Label"] = accessibility.mnemonic(props["Label"], self.mnemonics)
        model = self.model.createInstance("com.sun.star.awt.UnoControl" + kind + "Model")
        for key, value in {
            "Name": name,
            "PositionX": x,
            "PositionY": y,
            "Width": width,
            "Height": height,
            **props,
        }.items():
            setattr(model, key, value)
        self.model.insertByName(name, model)
        self.control_names.append(name)
        return model

    def button(self, name, text, x, y, width, fn):
        model = self.add(name, "Button", x, y, width, 16, Label=text)
        if name == "close":
            model.PushButtonType = 2  # Native Cancel semantics, including Escape from combo boxes.
        listener = Action(self, fn)
        self.actions.append(listener)
        self.dialog.getControl(name).addActionListener(listener)

    def status(self, message):
        self.model.getByName("status").Text = message

    def show(self):
        self.return_focus = self.return_focus or accessibility.current_focus(self.app, exclude=self)
        layout.prepare_dialog(self)
        self.dialog.createPeer(service(self.ctx, "awt.Toolkit"), None)
        accessibility.configure(self)
        self.closing = Closing(self)
        self.dialog.addTopWindowListener(self.closing)
        self.dialog.setVisible(True)
        self.app.windows.append(self)
        accessibility.focus_first(self)
        service(self.ctx, "awt.AsyncCallback").addCallback(Callback(lambda: layout.fit_dialog(self)), None)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if hasattr(self, "keys"):
            self.key_toolkit.removeKeyHandler(self.keys)
        self.dialog.dispose()
        if self in self.app.windows:
            self.app.windows.remove(self)
        if self.return_focus:

            def restore():
                control, parent = self.return_focus
                if not parent.closed:
                    try:
                        top = (
                            parent.document.CurrentController.Frame.ContainerWindow
                            if hasattr(parent, "geometry")
                            else parent.dialog
                        )
                        top.toFront()
                        control.setFocus()
                    except Exception:
                        pass

            service(self.ctx, "awt.AsyncCallback").addCallback(Callback(restore), None)


def paragraphs(document):
    """Review body, tables, text frames, notes and headers/footers of used page styles."""
    visited = []

    def walk(text):
        if any(text == old for old in visited):
            return
        visited.append(text)
        enum = text.createEnumeration()
        while enum.hasMoreElements():
            item = enum.nextElement()
            if item.supportsService("com.sun.star.text.Paragraph"):
                yield item
            elif item.supportsService("com.sun.star.text.TextTable"):
                for name in item.getCellNames():
                    yield from walk(item.getCellByName(name))

    yield from walk(document.Text)
    for name in document.TextFrames.getElementNames():
        yield from walk(document.TextFrames.getByName(name).Text)
    for collection in (document.Footnotes, document.Endnotes):
        for index in range(collection.Count):
            yield from walk(collection.getByIndex(index))
    styles = document.StyleFamilies.getByName("PageStyles")
    for name in styles.getElementNames():
        style = styles.getByName(name)
        if not style.isInUse():
            continue
        for kind in ("Header", "Footer"):
            if not style.getPropertyValue(kind + "IsOn"):
                continue
            for suffix in ("Text", "TextLeft", "TextRight", "TextFirst"):
                property_name = kind + suffix
                if style.PropertySetInfo.hasPropertyByName(property_name):
                    text = style.getPropertyValue(property_name)
                    if text is not None:
                        yield from walk(text)


def mapped_portions(paragraph):
    """Keep display offsets and native ranges together; refuse ambiguous representations."""
    enum = paragraph.createEnumeration()
    result, combined = [], ""
    while enum.hasMoreElements():
        portion = enum.nextElement()
        text = portion.String
        result.append((len(combined), len(combined) + len(text), portion))
        combined += text
    return result if combined == paragraph.String else None


def language_runs(paragraph):
    """Snapshot English plain text; fields are boundaries, never editable prose."""
    portions = mapped_portions(paragraph)
    if portions is None:
        return []
    parts = []
    boundary = True
    for begin, end, portion in portions:
        if portion.TextPortionType != "Text":
            boundary = True
            continue
        if end > begin:
            locale = portion.CharLocale
            if locale.Language == "en":
                country = locale.Country or "US"
                if not boundary and parts and parts[-1][1] == begin and parts[-1][2] == country:
                    parts[-1] = (parts[-1][0], end, country)
                else:
                    parts.append((begin, end, country))
                boundary = False
            else:
                boundary = True
    return parts


def apply_replacement(document, paragraph, original, issue, replacement):
    if not replacement_is_current(original, paragraph.String, issue):
        raise ValueError("This paragraph changed. Check again before applying this suggestion.")
    if document.isReadonly():
        raise ValueError("This document is read-only.")
    portions = mapped_portions(paragraph)
    if portions is None:
        raise ValueError("This paragraph contains unsupported fields. No replacement was made.")
    touched = [
        (begin, end, p)
        for begin, end, p in portions
        if max(begin, issue["start"]) < min(end, issue["end"])
        or (begin == end and issue["start"] < begin < issue["end"] and p.TextPortionType == "TextField")
    ]
    if not touched or any(p.TextPortionType != "Text" for _, _, p in touched):
        raise ValueError("The suggestion crosses a field or has no editable text. No replacement was made.")

    def endpoint(entry, offset):
        begin, _, portion = entry
        point = paragraph.Text.createTextCursorByRange(portion.Start)
        remaining = offset - begin
        while remaining:
            step = min(remaining, 32767)
            if not point.goRight(step, False):
                raise ValueError("Could not locate the suggestion.")
            remaining -= step
        return point

    # Fields may occupy one cursor position but display many characters. Start from
    # the actual text portion, not a paragraph-wide character count.
    cursor = endpoint(touched[0], issue["start"])
    cursor.gotoRange(endpoint(touched[-1], issue["end"]), True)
    # Confirm the range, including fields/non-BMP characters, before touching it.
    if cursor.String != issue["text"]:
        raise ValueError("The text range does not match. No replacement was made.")
    undo = document.getUndoManager()
    undo.enterUndoContext("LibreHarp: apply suggestion")
    try:
        cursor.String = replacement
    finally:
        undo.leaveUndoContext()


class Review(Window):
    def __init__(self, app, document):
        super().__init__(app, "LibreHarp — review", 420, 295)
        self.document = document
        self.rows, self.generation, self.timer = [], 0, None
        self.pending = False
        self.modify = Modify(self)
        self.add(
            "heading",
            "FixedText",
            8,
            6,
            400,
            14,
            Label="Review English text, including tables, notes, frames, headers and footers.",
        )
        self.add("issues", "ListBox", 8, 24, 404, 90, Dropdown=False, MultiSelection=False)
        self.selection = Selection(self, self.details)
        self.dialog.getControl("issues").addItemListener(self.selection)
        self.button("previous", "Previous", 8, 118, 70, lambda: self.move(-1))
        self.button("next", "Next", 84, 118, 70, lambda: self.move(1))
        self.button("locate", "Show in document", 160, 118, 100, self.locate)
        self.button(
            "rules", "Browse rules", 312, 118, 100, lambda: RuleBrowser(self.app, self.document).show()
        )
        self.add("message", "Edit", 8, 139, 404, 36, MultiLine=True, ReadOnly=True)
        self.add("suggestions", "ListBox", 8, 180, 250, 40, Dropdown=False, MultiSelection=False)
        self.button("apply", "Apply replacement", 270, 180, 142, self.apply)
        self.button("word", "Remember selected word", 270, 202, 142, self.word)
        self.button("ignore", "Ignore once", 8, 226, 80, self.ignore)
        self.button("disable", "Disable rule everywhere", 94, 226, 130, self.disable)
        self.button("settings", "Document settings", 230, 226, 82, self.settings)
        self.button("check", "Check document", 318, 226, 94, self.check)
        self.add("auto", "CheckBox", 8, 249, 180, 12, Label="Recheck after edits", State=1)
        self.button("close", "Close", 330, 248, 82, self.close)
        self.add("status", "FixedText", 8, 268, 404, 24, Label="Ready")
        document.addModifyListener(self.modify)

    def selected(self):
        index = self.dialog.getControl("issues").getSelectedItemPos()
        if index < 0 or index >= len(self.rows):
            raise ValueError("Select a finding first.")
        return index, self.rows[index]

    def details(self):
        _, (_, _, issue) = self.selected()
        self.model.getByName("message").Text = issue["rule"] + ": " + issue["message"]
        self.set_suggestions(issue)

    def set_suggestions(self, issue):
        self.model.getByName("suggestions").StringItemList = tuple(issue["suggestions"])
        if issue["suggestions"]:
            self.dialog.getControl("suggestions").selectItemPos(0, True)

    def move(self, delta):
        index, _ = self.selected()
        self.dialog.getControl("issues").selectItemPos(max(0, min(len(self.rows) - 1, index + delta)), True)
        self.details()

    def locate(self):
        _, (paragraph, original, issue) = self.selected()
        if paragraph.String != original:
            raise ValueError("This paragraph changed. Check again to locate it.")
        self.document.CurrentController.select(paragraph)

    def display(self, index=0):
        self.model.getByName("issues").StringItemList = tuple(
            f"{i + 1}. {r[2]['text'][:50]} — {r[2]['message'][:85]}" for i, r in enumerate(self.rows)
        )
        self.model.getByName("message").Text = ""
        self.model.getByName("suggestions").StringItemList = ()
        if self.rows:
            self.dialog.getControl("issues").selectItemPos(index, True)
            self.details()

    def apply(self):
        _, (paragraph, original, issue) = self.selected()
        choice = self.dialog.getControl("suggestions").getSelectedItemPos()
        if choice < 0:
            raise ValueError("This finding has no selected replacement.")
        apply_replacement(self.document, paragraph, original, issue, issue["suggestions"][choice])
        self.app.record("Applied", issue)
        self.check()

    def word(self):
        _, (paragraph, original, issue) = self.selected()
        if not is_word_finding(issue):
            raise ValueError("Select a spelling or word-splitting finding to remember a word.")
        if not replacement_is_current(original, paragraph.String, issue):
            raise ValueError("This paragraph changed. Check again before remembering its word.")
        self.app.store.add_word(issue["text"])
        self.app.record("Remembered word", issue)
        self.app.changed()
        self.check()

    def disable(self):
        _, (_, _, issue) = self.selected()
        self.app.store.set_rule(issue["rule"], False)
        self.app.changed()
        self.check()

    def ignore(self):
        index, (_, _, issue) = self.selected()
        self.rows.pop(index)
        self.app.record("Ignored", issue)
        self.display()
        self.status(
            "Ignored until the next document check. Use Disable rule everywhere for a permanent choice."
        )

    def remember_ignore(self):
        _, (paragraph, original, issue) = self.selected()
        if not replacement_is_current(original, paragraph.String, issue):
            raise ValueError("This paragraph changed. Check again before saving an ignore.")
        for begin, end, _ in language_runs(paragraph):
            if begin <= issue["start"] < issue["end"] <= end:
                key = ignore_key(
                    original[begin:end],
                    {
                        **issue,
                        "start": issue["start"] - begin,
                        "end": issue["end"] - begin,
                    },
                )
                break
        else:
            raise ValueError("This finding no longer matches an English text run. Check again.")
        label = (issue["rule"][:100] + " · " + " ".join(issue["text"].split()))[:240]
        update_ignores(self.app, self.document, lambda values: values.update({key: label}))
        self.app.record("Ignored", issue)
        self.rows = [row for row in self.rows if row != (paragraph, original, issue)]
        self.display()
        self.status("Ignore saved in this document. Save the document to keep it after closing.")

    def manage_ignores(self):
        from .scope_ui import SavedIgnores

        SavedIgnores(self.app, self.document).show()

    def settings(self):
        from .scope_ui import ScopedSettings

        ScopedSettings(self.app, self.document).show()

    def modified(self):
        self.generation += 1
        if self.timer:
            self.timer.cancel()
        if self.closed or not self.model.getByName("auto").State:
            return
        delay = self.app.store.advanced()["delay_ms"] / 1000
        self.timer = threading.Timer(delay, lambda: self.post(self.check))
        self.timer.daemon = True
        self.timer.start()

    def post(self, fn):
        if not self.closed:
            service(self.ctx, "awt.AsyncCallback").addCallback(
                Callback(lambda: None if self.closed else fn()), None
            )

    def check(self):
        if self.closed:
            return
        if self.pending:
            self.generation += 1
            self.status("Checking; a fresh check will follow your latest edit.")
            return
        if self.timer:
            self.timer.cancel()
        self.generation += 1
        generation = self.generation
        try:
            snapshot = [
                (p, p.String, language_runs(p)) for p in paragraphs(self.document) if p.String.strip()
            ]
            overrides = self.app.bindings.for_document(self.document)
            options = self.app.store.advanced()
            excluded = self.app.checker.skip_reason("", overrides, options)
        except Exception as exc:
            self.rows = []
            self.display()
            self.status("Check failed: " + str(exc))
            return
        if excluded:
            self.rows = []
            self.display()
            self.status(excluded)
            return
        self.pending = True
        skipped = sum(not runs for _, _, runs in snapshot)
        self.status(f"Checking {len(snapshot)} paragraphs…")

        def work():
            rows, error, oversized = [], None, 0
            warnings = set()
            try:
                for paragraph, text, runs in snapshot:
                    if self.closed or generation != self.generation:
                        break
                    for begin, end, country in runs:
                        if self.app.checker.skip_reason(text[begin:end], overrides, options):
                            oversized += 1
                            continue
                        for issue in self.app.checker.check(
                            text[begin:end], country, overrides, warnings=warnings
                        ):
                            issue["start"] += begin
                            issue["end"] += begin
                            rows.append((paragraph, text, issue))
            except Exception as exc:
                error = str(exc)
                self.app.log_error()

            def finish():
                self.pending = False
                if generation != self.generation:
                    self.check()
                    return
                self.rows = rows if not error else []
                self.display()
                self.status(
                    "Check failed: " + error
                    if error
                    else f"{len(rows)} suggestions · {self.app.engine.version}"
                    + (f" · {skipped} paragraphs skipped (language or fields)" if skipped else "")
                    + (f" · {oversized} text runs exceed the size limit" if oversized else "")
                    + (" · Weir skipped: " + " | ".join(sorted(warnings)) if warnings else "")
                )

            self.post(finish)

        threading.Thread(target=work, daemon=True).start()

    def close(self):
        if self.timer:
            self.timer.cancel()
        try:
            self.document.removeModifyListener(self.modify)
        except Exception:
            pass
        super().close()


class About(Window):
    def __init__(self, app):
        super().__init__(app, f"About LibreHarp {__version__}", 220, 83)
        self.add("version", "FixedText", 8, 9, 204, 14, Label=f"LibreHarp {__version__}")
        harper = engine_metadata(engine_directory())["version"]
        self.add("engine_version", "FixedText", 8, 27, 204, 14, Label=f"Harper {harper}")
        self.button("close", "Close", 134, 54, 78, self.close)


class Settings(Window):
    def __init__(self, app):
        super().__init__(app, "LibreHarp — settings", 420, 375)
        data = app.store.read()
        self.loaded_revision = fingerprint(data)
        profile = data["profiles"][data["profile"]]
        self.add(
            "profile_label",
            "FixedText",
            8,
            6,
            400,
            12,
            Label="Profile name (save a new name to create a profile)",
        )
        self.add(
            "profile",
            "ComboBox",
            8,
            20,
            200,
            14,
            Dropdown=True,
            Text=data["profile"],
            StringItemList=tuple(data["profiles"]),
        )
        self.button("load", "Load profile", 220, 20, 90, self.load)
        self.add(
            "dialect",
            "ComboBox",
            8,
            40,
            200,
            14,
            Dropdown=True,
            Text=profile["dialect"],
            StringItemList=("auto", "American", "British", "Australian", "Canadian", "Indian"),
        )
        self.add(
            "limitlabel", "FixedText", 220, 40, 190, 12, Label="Sentence word limit (0 = Harper default)"
        )
        self.add("limit", "Edit", 220, 55, 90, 14, Text=str(profile["sentence_limit"]))
        self.add(
            "ruleslabel",
            "FixedText",
            8,
            73,
            404,
            12,
            Label="Profile rules: one RuleName=true or RuleName=false per line",
        )
        self.add(
            "rules",
            "Edit",
            8,
            87,
            404,
            48,
            MultiLine=True,
            VScroll=True,
            Text=self.rule_text(profile["rules"]),
        )
        self.add(
            "globallabel",
            "FixedText",
            8,
            139,
            404,
            12,
            Label="Global rule overrides (take precedence over every profile; remove a line to reset)",
        )
        self.add(
            "global",
            "Edit",
            8,
            153,
            404,
            40,
            MultiLine=True,
            VScroll=True,
            Text=self.rule_text(data["rules"]),
        )
        self.add(
            "wordslabel", "FixedText", 8, 197, 190, 12, Label="Personal words — one per line, case-sensitive"
        )
        self.add(
            "termslabel",
            "FixedText",
            220,
            197,
            190,
            12,
            Label="Terminology — one find => replacement per line",
        )
        self.add(
            "words", "Edit", 8, 211, 198, 64, MultiLine=True, VScroll=True, Text="\n".join(data["words"])
        )
        self.add(
            "terms",
            "Edit",
            220,
            211,
            192,
            64,
            MultiLine=True,
            VScroll=True,
            Text="\n".join(t["find"] + " => " + t["replace"] for t in data["terms"]),
        )
        self.add("path", "Edit", 8, 281, 245, 14, Text=str(app.store.directory / "export.json"))
        self.button("export", "Export saved", 260, 281, 72, self.export)
        self.button("import", "Import", 338, 281, 74, self.import_file)
        self.button("save", "Save and activate", 8, 306, 130, self.save)
        self.button("advanced", "Advanced settings…", 148, 306, 152, self.advanced)
        self.button("close", "Close", 330, 306, 82, self.close)
        self.add(
            "status",
            "FixedText",
            8,
            328,
            404,
            40,
            Label="Settings are local. Disabling LongSentences here persists across restarts.",
        )

    @staticmethod
    def rule_text(rules):
        return "\n".join(f"{k}={str(v).lower()}" for k, v in sorted(rules.items()))

    @staticmethod
    def parse_rules(text):
        rules = {}
        for line in text.splitlines():
            if not line.strip():
                continue
            key, sep, value = line.partition("=")
            if not sep or not key.strip() or value.strip() not in ("true", "false"):
                raise ValueError("Use RuleName=true or RuleName=false on each rule line.")
            rules[key.strip()] = value.strip() == "true"
        return rules

    def value(self, name):
        return self.model.getByName(name).Text

    def load(self):
        data = self.app.store.read()
        name = self.value("profile").strip()
        if name not in data["profiles"]:
            raise ValueError("That profile is new. Edit its fields and save it.")
        p = data["profiles"][name]
        self.model.getByName("rules").Text = self.rule_text(p["rules"])
        self.model.getByName("dialect").Text = p["dialect"]
        self.model.getByName("limit").Text = str(p["sentence_limit"])
        self.status("Profile loaded for editing. Save and activate to use it.")

    def save(self):
        if fingerprint(self.app.store.read()) != self.loaded_revision:
            raise ValueError(
                "Preferences changed in another window. Reopen Settings before saving to preserve those changes."
            )
        name = self.value("profile").strip()
        if not name:
            raise ValueError("Enter a profile name.")
        profile = {
            "rules": self.parse_rules(self.value("rules")),
            "dialect": self.value("dialect"),
            "sentence_limit": int(self.value("limit")),
        }
        rules = self.parse_rules(self.value("global"))
        terms = []
        for line in self.value("terms").splitlines():
            if not line.strip():
                continue
            find, sep, replacement = line.partition("=>")
            if not sep or not find.strip():
                raise ValueError("Use find => replacement for each terminology rule.")
            terms.append({"find": find.strip(), "replace": replacement.strip()})
        words = sorted(set(w.strip() for w in self.value("words").splitlines() if w.strip()))

        def change(data):
            if fingerprint(data) != self.loaded_revision:
                raise ValueError("Preferences changed in another window. Reopen Settings before saving.")
            data["profiles"][name] = profile
            data.update(profile=name, rules=rules, terms=terms, words=words)

        saved = self.app.store.update(change)
        self.loaded_revision = fingerprint(saved)
        self.app.changed()
        self.status("Saved. Persistent choices apply to inline checking and the review window.")
        for window in tuple(self.app.windows):
            if isinstance(window, Review):
                window.check()

    def export(self):
        self.app.store.export_to(self.value("path"))
        self.status("Saved preferences exported.")

    def import_file(self):
        self.app.store.import_from(self.value("path"))
        self.app.changed()
        self.status("Imported. Close and reopen Settings to edit the imported preferences.")

    def advanced(self):
        from .advanced_ui import AdvancedSettings

        AdvancedSettings(self.app, self).show()


class RuleBrowser(Window):
    """Searchable native rule controls; persisted choices apply immediately."""

    def __init__(self, app, document=None, initial_scope=None):
        super().__init__(app, "LibreHarp — grammar rules", 420, 375)
        self.document = document
        self.catalog = load_catalog()
        self.visible_rules = []
        self.add("search", "Edit", 8, 8, 245, 15, Text="")
        self.button("searchbutton", "Search", 260, 8, 72, self.refresh)
        if app.weir:
            self.button("weir", "Weir rules…", 338, 8, 74, self.edit_weir)
        self.add(
            "scope",
            "ListBox",
            8,
            30,
            404,
            16,
            Dropdown=True,
            StringItemList=("Personal global override", "Active personal profile")
            + (("This document", "Project (document folder if new)") if document else ()),
            SelectedItems=((initial_scope if initial_scope is not None else 2 if document else 0),),
        )
        self.filters = Selection(self, self.refresh)
        categories = tuple(sorted({rule["category"] for rule in self.catalog if rule["category"]}))
        if app.weir:
            categories += ("Personal Weir rules",)
        subsets = ("All rules", "Overrides")
        if any(rule["new"] for rule in self.catalog):
            subsets += ("New in bundled Harper",)
        for name, x, width, label, items in (
            ("category", 8, 154, "Rule category", ("All categories", *categories)),
            ("enabled", 168, 98, "Effective rule state", ("Any state", "Enabled", "Disabled")),
            ("subset", 272, 140, "Rule subset", subsets),
        ):
            self.add(
                name,
                "ListBox",
                x,
                52,
                width,
                16,
                Dropdown=True,
                StringItemList=items,
                SelectedItems=(0,),
                HelpText=label,
            )
            self.dialog.getControl(name).addItemListener(self.filters)
        self.add("rules", "ListBox", 8, 74, 404, 100, Dropdown=False, MultiSelection=False)
        self.selection = Selection(self, self.details)
        self.dialog.getControl("rules").addItemListener(self.selection)
        self.add("detail", "Edit", 8, 180, 404, 132, MultiLine=True, ReadOnly=True, VScroll=True)
        self.button("enable", "Enable", 8, 318, 80, lambda: self.set(True))
        self.button("disable", "Disable", 94, 318, 80, lambda: self.set(False))
        self.button("reset", "Use inherited default", 180, 318, 140, lambda: self.set(None))
        self.button("close", "Close", 330, 318, 82, self.close)
        self.add(
            "status",
            "FixedText",
            8,
            342,
            404,
            24,
            Label="Choose a scope, then enable, disable, or restore an inherited default.",
        )
        self.refresh()

    def selected(self):
        index = self.dialog.getControl("rules").getSelectedItemPos()
        if index < 0:
            selected = self.model.getByName("rules").SelectedItems
            index = selected[0] if selected else -1
        if index < 0 or index >= len(self.visible_rules):
            raise ValueError("Select a rule first.")
        return self.visible_rules[index]

    def refresh(self):
        index = self.dialog.getControl("rules").getSelectedItemPos()
        previous = self.visible_rules[index]["name"] if 0 <= index < len(self.visible_rules) else None
        overrides = self.app.bindings.for_document(self.document) if self.document else None
        prefs = self.app.store.effective(overrides)
        catalog = self.catalog + [
            {
                "name": RULE_PREFIX + name,
                "label": name,
                "category": "Personal Weir rules",
                "default": True,
                "description": rule["description"],
                "alternatives": [],
                "new": False,
            }
            for name, rule in sorted(prefs["weir"].items())
            if self.app.weir
        ]
        category = self.dialog.getControl("category").getSelectedItem()
        enabled = self.dialog.getControl("enabled").getSelectedItem()
        subset = self.dialog.getControl("subset").getSelectedItem()
        self.visible_rules = filter_rules(
            catalog,
            prefs["rules"],
            query=self.model.getByName("search").Text,
            category="" if category == "All categories" else category,
            enabled={"Enabled": True, "Disabled": False}.get(enabled),
            subset=subset,
        )
        self.model.getByName("rules").StringItemList = tuple(
            ("On" if prefs["rules"].get(r["name"], r["default"]) else "Off")
            + " · "
            + r["label"]
            + " · "
            + r["category"]
            for r in self.visible_rules
        )
        self.model.getByName("detail").Text = ""
        if self.visible_rules:
            index = next((i for i, rule in enumerate(self.visible_rules) if rule["name"] == previous), 0)
            self.model.getByName("rules").SelectedItems = (index,)
            self.details()
        for name in ("enable", "disable", "reset"):
            self.model.getByName(name).Enabled = bool(self.visible_rules)
        self.status(f"{len(self.visible_rules)} of {len(catalog)} rules · changes are saved immediately")

    def edit_weir(self):
        from .weir_ui import WeirRules

        WeirRules(self).show()

    def details(self):
        rule = self.selected()
        data = self.app.store.read()
        project_settings, document_settings = {}, {}
        project = None
        if self.document:
            from .scopes import ProjectStore, project_path, read_document

            project = project_path(self.document.URL)
            project_settings = ProjectStore(project).read() if project else {}
            document_settings = read_document(self.document)
        profile = document_settings.get("profile", project_settings.get("profile", data["profile"]))
        default = "Personal Weir rule" if rule["name"].startswith(RULE_PREFIX) else "Harper default"
        state, origin = rule["default"], default
        for choices, label in (
            (data["profiles"].get(profile, {}), "profile: " + profile),
            (data, "personal global override"),
            (project_settings, "project: " + str(project)),
            (document_settings, "document override"),
        ):
            if rule["name"] in choices.get("rules", {}):
                state, origin = choices["rules"][rule["name"]], label
        if rule["name"] == "LongSentences":
            personal = data["profiles"].get(profile, {}).get("sentence_limit", 0)
            if document_settings.get("sentence_limit", project_settings.get("sentence_limit", personal)):
                state, origin = False, "custom sentence word limit"
        self.model.getByName(
            "detail"
        ).Text = f"{rule['name']}: {'enabled' if state else 'disabled'} ({origin}).\n{rule['description']}\n{default}: {'enabled' if rule['default'] else 'disabled'}."
        if explanation(rule["name"]):
            self.model.getByName("detail").Text += "\n\n" + explanation(rule["name"])

    def set(self, enabled):
        rule = self.selected()
        scope = self.dialog.getControl("scope").getSelectedItemPos()
        global_scope = scope == 0

        def change(data):
            rules = (
                data.setdefault("rules", {})
                if global_scope or scope >= 2
                else data["profiles"][data["profile"]]["rules"]
            )
            if enabled is None:
                rules.pop(rule["name"], None)
            else:
                rules[rule["name"]] = enabled
                if enabled:
                    for alternative in rule["alternatives"]:
                        rules[alternative] = False

        if scope >= 2:
            from .scopes import ScopeTarget

            ScopeTarget(self.app, self.document, "document" if scope == 2 else "project").update(change)
        else:
            self.app.store.update(change)
        self.app.changed()
        self.refresh()
        for window in tuple(self.app.windows):
            if isinstance(window, Review):
                window.check()


class ProtocolHandler(unohelper.Base, XDispatchProvider, XDispatch, XInitialization, XServiceInfo):
    def __init__(self, ctx):
        self.app, self.frame = runtime(ctx), None

    def getImplementationName(self):
        return PROTOCOL

    def supportsService(self, name):
        return name in self.getSupportedServiceNames()

    def getSupportedServiceNames(self):
        return ("com.sun.star.frame.ProtocolHandler",)

    def initialize(self, args):
        if args:
            self.frame = args[0]

    def queryDispatch(self, url, target, flags):
        return self if url.Protocol == "org.libreharp:" else None

    def queryDispatches(self, requests):
        return tuple(self.queryDispatch(r.FeatureURL, r.FrameName, r.SearchFlags) for r in requests)

    def addStatusListener(self, listener, url):
        pass

    def removeStatusListener(self, listener, url):
        pass

    def dispatch(self, url, args):
        try:
            if url.Path.startswith("context/"):
                self.app.context_menus.execute(url.Path, self.frame)
                return
            if url.Path in ("english", "restore-english"):
                from .english_checking import configure

                configure(self.app, restore=url.Path == "restore-english")
                return
            document = (
                self.frame.Controller.Model
                if self.frame
                else service(self.app.ctx, "frame.Desktop").getCurrentComponent()
            )
            if url.Path == "about":
                About(self.app).show()
            elif url.Path == "settings":
                Settings(self.app).show()
            elif url.Path == "rules":
                RuleBrowser(self.app, document).show()
            elif url.Path == "scopes":
                from .scope_ui import ScopedSettings

                ScopedSettings(self.app, document).show()
            elif url.Path == "vocabulary":
                from .scope_ui import Vocabulary

                Vocabulary(self.app, document).show()
            elif url.Path == "migrate":
                from .migration_ui import Migration

                Migration(self.app, document).show()
            elif url.Path == "sidebar":
                from .sidebar import open_sidebar

                open_sidebar(self.app, self.frame)
            else:
                document = (
                    self.frame.Controller.Model
                    if self.frame
                    else service(self.app.ctx, "frame.Desktop").getCurrentComponent()
                )
                if not document or not document.supportsService("com.sun.star.text.TextDocument"):
                    return
                for window in self.app.windows:
                    if isinstance(window, Review) and window.document == document and not window.closed:
                        window.dialog.setVisible(True)
                        window.check()
                        return
                window = Review(self.app, document)
                window.show()
                window.check()
        except Exception:
            self.app.log_error()
