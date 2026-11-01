"""Names, focus, and local keyboard navigation for native UNO controls."""

import uno
import unohelper
from com.sun.star.awt import XCallback, XKeyHandler

from .layout import focus_control

NAMES = {
    "issues": "Findings",
    "message": "Finding explanation and context",
    "suggestions": "Suggested replacement",
    "scope": "Settings scope",
    "more": "More actions",
    "status": "Status",
    "profile": "Profile name",
    "dialect": "English dialect",
    "limit": "Sentence word limit",
    "rules": "Rule overrides",
    "global": "Personal global rule overrides",
    "words": "Personal words",
    "terms": "Preferred terminology",
    "path": "Preferences import or export file",
    "search": "Search grammar rules",
    "detail": "Rule explanation and effective settings",
    "folder": "Project folder",
    "word": "Word to remember",
    "find": "Text to find",
    "replacement": "Replacement text",
    "preview_text": "Import preview",
}
OVERRIDES = {
    "RuleBrowser": {"rules": "Grammar rules"},
    "ScopedSettings": {"profile": "Profile override", "dialect": "Dialect override"},
    "Vocabulary": {"words": "Remembered words", "terms": "Saved terminology"},
    "Migration": {"path": "Optional dictionary file"},
    "SidebarReview": {"scope": "Scope for remembered words and disabled rules"},
}
ORDERS = {
    "Vocabulary": (
        "words",
        "word",
        "add_word",
        "remove_word",
        "terms",
        "find",
        "replacement",
        "add_term",
        "remove_term",
        "close",
        "status",
    ),
}


def mnemonic(label, used):
    if "~" in label:
        used.add(label.split("~", 1)[1][0].lower())
        return label
    for index, char in enumerate(label):
        if char.isalpha() and char.lower() not in used:
            used.add(char.lower())
            return label[:index] + "~" + label[index:]
    return label


def focused(control):
    flag = uno.getConstantByName("com.sun.star.accessibility.AccessibleStateType.FOCUSED")

    def walk(context, depth=0):
        if context.getAccessibleStateSet() & flag:
            return True
        return depth < 3 and any(
            walk(context.getAccessibleChild(i).getAccessibleContext(), depth + 1)
            for i in range(min(32, context.getAccessibleChildCount()))
        )

    return walk(control.getAccessibleContext())


def current_focus(app, exclude=None):
    for window in reversed(app.windows):
        if not window.closed and window is not exclude:
            for name in window.control_names:
                control = window.dialog.getControl(name)
                if focused(control):
                    return control, window
    return None


class Later(unohelper.Base, XCallback):
    def __init__(self, owner, fn):
        self.owner, self.fn = owner, fn

    def notify(self, data):
        if not self.owner.closed:
            self.fn()


class Keys(unohelper.Base, XKeyHandler):
    def __init__(self, owner, sidebar):
        self.owner, self.sidebar = owner, sidebar
        self.pending = None

    def keyPressed(self, event):
        if self.owner.closed:
            return False
        key = event.KeyCode
        status = event.Modifiers == 0 and key == uno.getConstantByName("com.sun.star.awt.Key.F8")
        escape = event.Modifiers == 0 and key == uno.getConstantByName("com.sun.star.awt.Key.ESCAPE")
        if not (status or escape):
            return False
        top = (
            self.owner.document.CurrentController.Frame.ContainerWindow
            if self.sidebar
            else self.owner.dialog.getPeer()
        )
        # During native dispatch, ActiveTopWindow can temporarily differ from the
        # window that actually received the key. The event source is authoritative.
        if not self.sidebar and event.Source != top and self.owner.key_toolkit.getActiveTopWindow() != top:
            return False
        # GTK embeds the installed panel in an intermediary native window.
        # Its source/active top is neither the Writer frame nor our peer;
        # current focus on one of this panel's controls establishes ownership.
        if self.sidebar and not any(
            focused(self.owner.dialog.getControl(n)) for n in self.owner.control_names
        ):
            return False

        if status:
            self.pending = (key, lambda: focus_control(self.owner, "status"))
        elif escape:
            expanded = uno.getConstantByName("com.sun.star.accessibility.AccessibleStateType.EXPANDED")
            if any(
                self.owner.dialog.getControl(n).getAccessibleContext().getAccessibleStateSet() & expanded
                for n in self.owner.control_names
            ):
                return False
            if self.sidebar:
                self.pending = (key, self.owner.document.CurrentController.Frame.ComponentWindow.setFocus)
            else:
                self.pending = (key, self.owner.close)
        return True

    def keyReleased(self, event):
        # Native GTK controls can consume these presses before the toolkit handler.
        # The release path retains the same ownership and modifier checks.
        if self.pending is None and event.KeyCode in (
            uno.getConstantByName("com.sun.star.awt.Key.ESCAPE"),
            uno.getConstantByName("com.sun.star.awt.Key.F8"),
        ):
            self.keyPressed(event)
        if self.pending and event.KeyCode == self.pending[0]:
            _, fn = self.pending
            self.pending = None
            self.owner.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.AsyncCallback", self.owner.ctx
            ).addCallback(Later(self.owner, fn), None)
            return True
        return False

    def disposing(self, event):
        pass


def configure(owner, sidebar=False):
    """Run after peer creation. TabIndex alone does not configure a plain container."""
    if hasattr(owner, "keys"):
        return
    names = list(ORDERS.get(type(owner).__name__, owner.control_names))
    names += [n for n in owner.control_names if n not in names]
    owner.keys = Keys(owner, sidebar)
    models = []
    for index, name in enumerate(names):
        control = owner.dialog.getControl(name)
        model = control.getModel()
        info = model.getPropertySetInfo()
        if info.hasPropertyByName("TabIndex"):
            model.TabIndex = index
        if not info.hasPropertyByName("Tabstop"):
            continue
        if model.supportsService("com.sun.star.awt.UnoControlFixedTextModel"):
            model.Tabstop = False
            continue
        model.Tabstop = True
        label = getattr(model, "Label", "").replace("~", "")
        accessible_name = label or OVERRIDES.get(type(owner).__name__, {}).get(name, NAMES.get(name, name))
        control.getPeer().setProperty("AccessibleName", accessible_name)
        if not model.HelpText:
            model.HelpText = accessible_name
        models.append(model)
    owner.key_toolkit = owner.ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.awt.Toolkit", owner.ctx
    )
    owner.key_toolkit.addKeyHandler(owner.keys)
    if sidebar:
        smgr = owner.ctx.ServiceManager
        tab_model = smgr.createInstanceWithContext("com.sun.star.awt.TabControllerModel", owner.ctx)
        tab_model.setControlModels(tuple(models))
        tab_model.setGroupControl(False)
        owner.tab_controller = smgr.createInstanceWithContext("com.sun.star.awt.TabController", owner.ctx)
        owner.tab_controller.setModel(tab_model)
        owner.tab_controller.setContainer(owner.dialog)
        owner.dialog.addTabController(owner.tab_controller)
        owner.tab_controller.activateTabOrder()
    owner.focus_name = next((n for n in names if owner.dialog.getControl(n).getModel() in models), None)


def focus_first(owner):
    if owner.focus_name:
        focus_control(owner, owner.focus_name)
