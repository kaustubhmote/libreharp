"""Exercise the installed popup with real keyboard input in an isolated display."""

import argparse
import copy
import json
import re
import subprocess
import time
import traceback

import test_libreoffice as test
import uno
import unohelper
from com.sun.star.ui import XContextMenuInterceptor
from test_accessibility import wait_for

from libreharp import __version__
from libreharp.store import DEFAULTS, Store

documents = []


class Observer(unohelper.Base, XContextMenuInterceptor):
    name = None

    def notifyContextMenuExecute(self, event):
        self.container = event.ActionTriggerContainer
        self.name = self.container.getName()
        return uno.Enum("com.sun.star.ui.ContextMenuInterceptorAction", "IGNORED")

    @property
    def rows(self):
        # Read after all interceptors finish; Writer may call this observer first.
        container = self.container
        if self.name not in ("private:resource/SpellContextMenu", "private:resource/GrammarContextMenu"):
            container = next(
                container.getByIndex(i).getPropertyValue("SubContainer")
                for i in range(container.Count)
                if getattr(container.getByIndex(i), "Text", "") == "LibreHarp"
            )
        return tuple(
            (getattr(container.getByIndex(i), "Text", ""), getattr(container.getByIndex(i), "CommandURL", ""))
            for i in range(container.Count)
        )


def key(sequence):
    subprocess.run(["xdotool", "key", "--clearmodifiers", sequence], check=True, timeout=5)
    time.sleep(0.2)


def main(keyboard_only=False):
    ctx = test.start(True)
    store = Store(test.PROFILE / "user/LibreHarp")
    store.update(lambda d: (d.clear(), d.update(copy.deepcopy(DEFAULTS))))
    error_log = store.directory / "errors.log"
    before_errors = error_log.read_text() if error_log.exists() else ""
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    doc = test.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    documents.append(doc)
    text = "This is a example. The Qzxmenuglobalprobe works."
    doc.Text.String, doc.CharLocale = text, locale
    doc.CurrentController.ViewSettings.ZoomValue = 120
    doc.storeAsURL((test.ZONE / "LibreHarp-popup-test.odt").as_uri(), (test.prop("Overwrite", True),))
    time.sleep(1)
    xid = (
        subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--name", "LibreHarp-popup-test.odt"], text=True
        )
        .strip()
        .splitlines()[-1]
    )

    def activate():
        def active_window():
            result = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=5)
            return result.stdout.strip()

        if active_window() == xid:
            return
        subprocess.run(["xdotool", "windowactivate", xid], check=True, timeout=5)
        if not wait_for(lambda: active_window() == xid):
            subprocess.run(
                ["import", "-window", "root", str(test.ZONE / "popup-focus-failure.png")],
                check=True,
                timeout=10,
            )
            raise AssertionError("The isolated Writer window did not receive focus.")

    activate()
    linguistic = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.LinguServiceManager", ctx
    )
    linguistic.setConfiguredServices(
        "com.sun.star.linguistic2.Proofreader", locale, ("org.libreharp.Proofreader",)
    )
    properties = ctx.ServiceManager.createInstanceWithContext("com.sun.star.linguistic2.LinguProperties", ctx)
    properties.IsSpellAuto = True
    iterator = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.ProofreadingIterator", ctx
    )

    def find_accessible(predicate):
        def walk(context, depth=0):
            if context is None:
                return None
            if predicate(context):
                return context
            if depth < 16:
                for index in range(min(200, context.getAccessibleChildCount())):
                    found = walk(context.getAccessibleChild(index).getAccessibleContext(), depth + 1)
                    if found is not None:
                        return found
            return None

        accessible = doc.CurrentController.Frame.ContainerWindow.getProperty("XAccessible")
        return walk(accessible.getAccessibleContext()) if accessible else None

    def accessible_text():
        result = find_accessible(
            lambda c: hasattr(c, "getTextMarkupCount") and c.getText() == doc.Text.String
        )
        assert result is not None, "Document text is missing from the accessible tree"
        return result

    menu_rows = []

    def popup(offset, mouse=False):
        activate()
        time.sleep(0.3)
        # Use the installed engine through Writer, including its document handshake.
        flat = doc.getFlatParagraphIterator(2, False).getFirstPara()
        for _ in range(30):
            result = iterator.checkSentenceAtPosition(
                doc, flat, doc.Text.String, locale, 0, len(doc.Text.String), offset
            )
            if result.aErrors:
                break
            time.sleep(0.1)
        key("ctrl+Home")
        cursor = doc.Text.createTextCursor()
        cursor.goRight(offset, False)
        doc.CurrentController.select(cursor)
        doc.CurrentController.Frame.ContainerWindow.toFront()
        time.sleep(0.5)
        observer = Observer()
        doc.CurrentController.registerContextMenuInterceptor(observer)
        if mouse:
            context = accessible_text()
            position = context.getLocationOnScreen()
            rect = context.getCharacterBounds(offset)
            # GTK's nested-display accessibility coordinates omit some chrome.
            # Locate the rendered red underline near the expected character.
            shot = test.ZONE / "pointer-target.png"
            subprocess.run(["import", "-window", "root", str(shot)], check=True, timeout=10)
            x = max(0, position.X + rect.X)
            y = max(0, position.Y + rect.Y - 40)
            pixels = subprocess.check_output(
                ["convert", str(shot), "-crop", f"{max(20, rect.Width)}x120+{x}+{y}", "-depth", "8", "txt:-"],
                text=True,
            )
            red = []
            for line in pixels.splitlines():
                match = re.match(r"(\d+),(\d+):.*?\((\d+),(\d+),(\d+)", line)
                if match:
                    px, py, r, g, b = map(int, match.groups())
                    if r > 180 and g < 100 and b < 100:
                        red.append((py, px))
            assert red, "The target word has no visible spelling underline"
            py, px = sorted(red)[len(red) // 2]
            subprocess.run(
                ["xdotool", "mousemove", str(x + px), str(y + py - 6), "click", "3"], check=True, timeout=5
            )
            time.sleep(0.3)
        else:
            key("shift+F10")
        doc.CurrentController.releaseContextMenuInterceptor(observer)
        if not observer.name:
            subprocess.run(["import", "-window", "root", str(test.ZONE / "popup-failure.png")], check=True)
        assert observer.name, "Writer did not open a context menu"
        if observer.name not in ("private:resource/SpellContextMenu", "private:resource/GrammarContextMenu"):
            key("Home")
            key("Right")
        menu_rows[:] = observer.rows
        return result

    def choose(label, group=None):
        active = group is None
        target = None
        rows = [row for row in menu_rows if row[0]]
        for index, (text, command) in enumerate(rows):
            if group and not text.startswith(("  ├─ ", "  └─ ")):
                active = text == group
            if active and (text[5:] if text.startswith(("  ├─ ", "  └─ ")) else text) == label:
                target = index
                assert command, "Target has no command"
                break
        assert target is not None, (label, group, rows)
        key("Home")
        for _ in range(target):
            key("Down")
        key("Return")

    popup(text.index("a example"))
    subprocess.run(["import", "-window", "root", str(test.ZONE / "grammar-popup.png")], check=True)
    test.record(
        "Installed menu has flat Unicode branches", any(text.startswith("  └─ ") for text, _ in menu_rows)
    )
    test.record(
        "Installed menu has no suggestion-card entry",
        all(text != "Review suggestion…" for text, _ in menu_rows),
    )
    choose('"an"', "Replace")
    test.record(
        "Installed grammar branch applies its suggestion",
        wait_for(lambda: "an example" in doc.Text.String),
    )
    doc.UndoManager.undo()
    test.record("Installed popup replacement is undoable", doc.Text.String == text)
    if keyboard_only:
        url = uno.createUnoStruct("com.sun.star.util.URL")
        url.Complete, url.Protocol, url.Path = test.about_command(ctx), "org.libreharp:", "about"
        frame = doc.CurrentController.Frame
        frame.queryDispatch(url, "_self", 0).dispatch(url, ())
        test.record(
            "Writer shows the About version on screen", wait_for(lambda: test.about_shows_version(ctx))
        )
        key("Escape")
        return
    if not doc.CurrentController.Frame.ContainerWindow.getProperty("XAccessible"):
        reason = "Writer exposes no accessibility tree for targeting mouse actions in this build."
        test.REPORT["skipped"] = reason
        print("SKIP", reason, flush=True)
        return
    result = popup(text.index("Qzx"), mouse=True)
    subprocess.run(["import", "-window", "root", str(test.ZONE / "context-menu.png")], check=True, timeout=10)
    choose("Globally", "Remember word")
    test.record(
        "Installed spelling popup adds a word globally",
        wait_for(lambda: "Qzxmenuglobalprobe" in store.read()["words"]),
    )
    dictionaries = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.DictionaryList", ctx
    )
    test.record(
        "Global popup word is accepted by Writer's dictionary",
        dictionaries.getDictionaryByName("LibreHarp personal words").getEntry("Qzxmenuglobalprobe")
        is not None,
    )
    # An ignore must keep both occurrences' text and avoid changing rule preferences.
    doc.Text.String = "This is a example. This is a example."
    snapshot = store.read()
    result = popup(8)
    choose("Ignore once")
    test.record(
        "Installed Ignore once leaves text and persistent rules unchanged",
        doc.Text.String == "This is a example. This is a example." and store.read() == snapshot,
    )
    doc.Text.String = "The Qzxignoreprobe works. The Qzxignoreprobe works."
    result = popup(5, mouse=True)
    test.record(
        "Both repeated misspellings have native underlines", accessible_text().getTextMarkupCount(1) == 2
    )
    choose("Ignore once")
    test.record(
        "Ignore once removes only the clicked spelling underline",
        wait_for(lambda: accessible_text().getTextMarkupCount(1) == 1),
    )
    sentence, word = "The Qzxsidebarprobe works.", "Qzxsidebarprobe"
    doc.Text.String = " ".join([sentence] * 3)
    sidebar = doc.CurrentController.Sidebar
    sidebar.setVisible(False)

    def shows_occurrence(number):
        details = find_accessible(lambda c: c.getAccessibleName() == "Finding explanation and context")
        marked = sentence.replace(word, f"[{word}]")
        expected = " ".join(marked if index == number else sentence for index in range(1, 4))
        return details is not None and expected in details.getText()

    popup(len(sentence) + 1 + sentence.index(word), mouse=True)
    choose("Open sidebar")
    test.record(
        "Opening a closed sidebar selects the clicked spelling occurrence",
        wait_for(lambda: shows_occurrence(2)),
    )
    popup(2 * (len(sentence) + 1) + sentence.index(word), mouse=True)
    choose("Open sidebar")
    test.record(
        "Opening an already visible sidebar selects the new spelling occurrence",
        wait_for(lambda: shows_occurrence(3)),
    )
    menu_role = uno.getConstantByName("com.sun.star.accessibility.AccessibleRole.MENU")
    libreharp_menu = find_accessible(
        lambda context: (
            context.getAccessibleRole() == menu_role and context.getAccessibleName() == "LibreHarp"
        )
    )
    assert libreharp_menu is not None, "LibreHarp is missing from the Writer menu bar"
    about_item = next(
        context
        for index in range(libreharp_menu.getAccessibleChildCount())
        if (context := libreharp_menu.getAccessibleChild(index).getAccessibleContext())
        and context.getAccessibleName() == "About LibreHarp…"
    )
    about_item.doAccessibleAction(0)
    toolkit = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)

    def about_shows_version():
        for index in range(toolkit.getTopWindowCount()):
            window = toolkit.getTopWindow(index)
            if not hasattr(window, "getProperty"):
                continue
            accessible = window.getProperty("XAccessible")
            if accessible is None:
                continue
            context = accessible.getAccessibleContext()
            if context is None or context.getAccessibleName() != f"About LibreHarp {__version__}":
                continue
            for child_index in range(context.getAccessibleChildCount()):
                child = context.getAccessibleChild(child_index).getAccessibleContext()
                if child.getAccessibleName() == f"LibreHarp {__version__}":
                    return True
        return False

    test.record("Writer's About menu shows the installed extension version", wait_for(about_shows_version))
    key("Escape")
    test.record(
        "Installed popup actions produce no component exceptions",
        (error_log.read_text() if error_log.exists() else "") == before_errors,
    )
    doc.close(True)
    test.stop()
    ctx = test.start()
    checker = ctx.ServiceManager.createInstanceWithContext("org.libreharp.Proofreader", ctx)
    doc, identity = test.bound_document(ctx, locale, text)
    documents.append(doc)
    result = checker.doProofreading(identity, text, locale, 0, len(text), ())
    test.record(
        "Popup global word survives restart",
        not any(e.aRuleIdentifier == "SpellCheck" for e in result.aErrors),
    )
    dictionaries = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.DictionaryList", ctx
    )
    test.record(
        "Writer dictionary is rebuilt from persisted LibreHarp words",
        dictionaries.getDictionaryByName("LibreHarp personal words").getEntry("Qzxmenuglobalprobe")
        is not None,
    )
    doc.close(True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--keyboard-only", action="store_true", help="Exercise the keyboard popup and About dialog"
    )
    code = 0
    try:
        main(parser.parse_args().keyboard_only)
    except Exception:
        code = 1
        test.REPORT["errors"].append(traceback.format_exc())
        traceback.print_exc()
    finally:
        subprocess.run(["xdotool", "key", "Escape"], check=False, timeout=5)
        for document in documents:
            try:
                document.close(True)
            except Exception:
                pass
        test.stop()
        test.REPORT["passed"] = code == 0
        (test.ZONE / "popup-writer-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
