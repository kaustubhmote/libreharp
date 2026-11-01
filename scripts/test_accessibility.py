"""Native accessible-tree and real X11 keyboard checks in the isolated test profile."""

import copy
import json
import subprocess
import time
import traceback

import test_libreoffice as test
import uno
import unohelper
from com.sun.star.accessibility import XAccessibleEventListener

from libreharp.accessibility import focused
from libreharp.migration_ui import Migration
from libreharp.scope_ui import ScopedSettings, Vocabulary
from libreharp.sidebar import SidebarReview
from libreharp.store import DEFAULTS
from libreharp.uno_app import Review, RuleBrowser, Runtime, Settings


class Events(unohelper.Base, XAccessibleEventListener):
    def __init__(self):
        self.ids = []

    def notifyEvent(self, event):
        self.ids.append(event.EventId)

    def disposing(self, event):
        pass


def wait_for(fn, timeout=6):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if fn():
            return True
        time.sleep(0.05)
    return False


def window_id(title):
    return (
        subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--name", "^" + title + "$"], text=True
        )
        .strip()
        .splitlines()[-1]
    )


def key(xid, sequence):
    subprocess.run(["xdotool", "windowactivate", "--sync", xid], check=True, timeout=5)
    # Window-manager activation completes before Writer processes its focus event.
    time.sleep(0.2)
    subprocess.run(["xdotool", "key", "--clearmodifiers", sequence], check=True, timeout=5)
    time.sleep(0.15)


def has_focus(window, name):
    return focused(window.dialog.getControl(name))


def audit(window):
    missing = []
    names = {}
    for name in window.control_names:
        c = window.dialog.getControl(name)
        m = c.getModel()
        if m.PropertySetInfo.hasPropertyByName("Tabstop") and not m.supportsService(
            "com.sun.star.awt.UnoControlFixedTextModel"
        ):
            value = c.getAccessibleContext().getAccessibleName()
            names[name] = value
            if not value or not m.Tabstop:
                missing.append(name)
    test.REPORT.setdefault("accessible_names", {})[type(window).__name__] = names
    test.record(type(window).__name__ + " exposes named keyboard controls", not missing)


def main():
    ctx = test.start(visible=True)
    app = Runtime(ctx)
    app.store.update(lambda d: (d.clear(), d.update(copy.deepcopy(DEFAULTS))))
    doc = test.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    doc.Text.String = "This is a example. This is is incorrect."
    doc.CharLocale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    doc.storeAsURL(
        (test.ZONE / "LibreHarp-keyboard-test.odt").as_uri(),
        (test.prop("FilterName", "writer8"), test.prop("Overwrite", True)),
    )
    try:
        for cls in (Settings, RuleBrowser, ScopedSettings, Vocabulary, Migration, Review):
            window = cls(app) if cls is Settings else cls(app, doc)
            window.show()
            xid = window_id(window.model.Title)
            key(xid, "Tab")
            audit(window)
            if cls is Settings:
                test.record(
                    "Settings names distinguish dialect, words, and preferences file",
                    all(
                        window.dialog.getControl(n).getAccessibleContext().getAccessibleName() == value
                        for n, value in (
                            ("dialect", "English dialect"),
                            ("words", "Personal words"),
                            ("path", "Preferences import or export file"),
                        )
                    ),
                )
                window.dialog.getControl("profile").setFocus()
                key(xid, "Tab")
                test.record("Tab moves from profile to Load", wait_for(lambda: has_focus(window, "load")))
                key(xid, "Tab")
                test.record("Tab reaches the dialect combo", wait_for(lambda: has_focus(window, "dialect")))
                key(xid, "shift+Tab")
                test.record("Shift Tab returns to Load", wait_for(lambda: has_focus(window, "load")))
                events = Events()
                window.dialog.getControl("status").getAccessibleContext().addAccessibleEventListener(events)
                window.status("Keyboard status test")
                test.record(
                    "Status updates emit accessible text-change events",
                    wait_for(
                        lambda: (
                            uno.getConstantByName("com.sun.star.accessibility.AccessibleEventId.TEXT_CHANGED")
                            in events.ids
                        )
                    ),
                )
                key(xid, "F8")
                test.record(
                    "Status shortcut focuses readable feedback", wait_for(lambda: has_focus(window, "status"))
                )
                status = window.dialog.getControl("status")
                test.record(
                    "Status exposes its full readable text",
                    status.getAccessibleContext().getText() == "Keyboard status test",
                )
            if cls is Vocabulary:
                window.dialog.getControl("word").setFocus()
                key(xid, "Tab")
                test.record(
                    "Vocabulary tab order keeps word entry next to Add word",
                    wait_for(lambda: has_focus(window, "add_word")),
                )
                window.model.getByName("word").Text = "QzxKeyboardProbe"
                key(xid, "space")
                test.record(
                    "Space activates the focused Add word button",
                    wait_for(lambda: "QzxKeyboardProbe" in app.store.read()["words"]),
                )
                window.model.getByName("word").Text = "QzxMnemonicProbe"
                window.dialog.getControl("word").setFocus()
                key(xid, "alt+a")
                test.record(
                    "Button mnemonic activates Add word",
                    wait_for(lambda: "QzxMnemonicProbe" in app.store.read()["words"]),
                )
                window.model.getByName("word").Text = ""
                window.dialog.getControl("add_word").setFocus()
                key(xid, "space")
                test.record(
                    "Validation errors move focus to readable status",
                    wait_for(lambda: has_focus(window, "status"))
                    and "word" in window.model.getByName("status").Text.lower(),
                )
                window.dialog.getControl("replacement").setFocus()
                key(xid, "shift+Tab")
                test.record(
                    "Vocabulary reverse navigation reaches Find", wait_for(lambda: has_focus(window, "find"))
                )
            key(xid, "Escape")
            test.record(type(window).__name__ + " closes with Escape", wait_for(lambda: window.closed))
        # A native sidebar container attached to this document's Writer frame.
        panel = SidebarReview(app, doc, doc.CurrentController.Frame.ContainerWindow)
        panel.dialog.setPosSize(500, 100, 360, 600, 15)
        xid = (
            subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", "LibreHarp-keyboard-test.odt"], text=True
            )
            .strip()
            .splitlines()[-1]
        )
        assert wait_for(lambda: len(panel.rows) >= 2)
        key(xid, "F6")
        panel.dialog.getControl("issues").setFocus()
        audit(panel)
        key(xid, "Tab")
        test.record(
            "Sidebar Tab skips disabled Previous and reaches Next", wait_for(lambda: has_focus(panel, "next"))
        )
        key(xid, "shift+Tab")
        test.record("Sidebar Shift Tab returns to findings", wait_for(lambda: has_focus(panel, "issues")))
        key(xid, "F8")
        test.record("Sidebar status is keyboard reachable", wait_for(lambda: has_focus(panel, "status")))
        panel.dialog.getControl("more").setFocus()
        panel.check()
        assert wait_for(lambda: not panel.pending)
        test.record("Background review preserves keyboard focus", has_focus(panel, "more"))
        panel.dialog.getControl("more").setFocus()
        child = ScopedSettings(app, doc)
        child.show()
        key(window_id(child.model.Title), "Escape")
        returned = wait_for(lambda: child.closed and has_focus(panel, "more"))
        if not returned:
            print(
                "Return diagnostics",
                child.closed,
                None if child.closed else child.dialog.isVisible(),
                None if child.closed else child.key_toolkit.getActiveTopWindow() == child.dialog.getPeer(),
                [n for n in panel.control_names if has_focus(panel, n)],
                flush=True,
            )
        test.record(
            "Closing a child dialog restores its launching control",
            returned,
        )
        key(xid, "Escape")
        test.record(
            "Sidebar Escape leaves the panel open and returns to Writer",
            not panel.closed and wait_for(lambda: not any(has_focus(panel, n) for n in panel.control_names)),
        )
        key(xid, "F8")
        test.record(
            "Status shortcut does not capture F8 in Writer",
            not any(has_focus(panel, n) for n in panel.control_names),
        )
        panel.close()
    finally:
        for window in list(app.windows):
            window.close()
        doc.close(True)
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
        (test.ZONE / "accessibility-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
