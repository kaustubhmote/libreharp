"""A native, resizable Writer sidebar. Shares review behavior with the window."""

import threading

import uno
import unohelper
from com.sun.star.awt import XWindowListener
from com.sun.star.lang import XComponent, XServiceInfo
from com.sun.star.ui import XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory

from .scopes import ScopeTarget
from .uno_app import Action, Callback, Modify, Review, RuleBrowser, Selection, runtime, service

FACTORY = "org.libreharp.SidebarFactory"
RESOURCE = "private:resource/toolpanel/LibreHarpPanel"


def open_sidebar(app, frame, attempt=0):
    """Deck lists arrive after the frame's context event; activate on a later UI turn."""
    try:
        controller = frame.Controller
        if controller is None:
            return
        sidebar = controller.Sidebar
        sidebar.setVisible(True)
        if sidebar.Decks.hasByName("LibreHarpDeck"):
            sidebar.Decks.getByName("LibreHarpDeck").activate(True)
            sidebar.showDecks(True)
            return
        if attempt >= 30:
            raise RuntimeError(
                "LibreHarp's sidebar deck did not become available. Restart Writer after installation."
            )

        def post():
            service(app.ctx, "awt.AsyncCallback").addCallback(
                Callback(lambda: open_sidebar(app, frame, attempt + 1)), None
            )

        timer = threading.Timer(0.1, post)
        timer.daemon = True
        timer.start()
    except Exception:
        app.log_error()


class Models:
    def __init__(self):
        self.controls = {}

    def getByName(self, name):
        return self.controls[name]


class Resize(unohelper.Base, XWindowListener):
    def __init__(self, owner):
        self.owner = owner

    def windowResized(self, event):
        self.owner.layout(event.Width)

    def windowMoved(self, event):
        pass

    def windowShown(self, event):
        pass

    def windowHidden(self, event):
        pass

    def disposing(self, event):
        self.owner.close()


class SidebarReview(Review):
    def __init__(self, app, document, parent):
        self.app, self.ctx, self.document = app, app.ctx, document
        self.model = Models()
        self.dialog = service(self.ctx, "awt.UnoControlContainer")
        self.dialog.setModel(service(self.ctx, "awt.UnoControlContainerModel"))
        self.dialog.createPeer(service(self.ctx, "awt.Toolkit"), parent)
        self.actions = []
        self.closed = False
        self.rows, self.generation, self.timer = [], 0, None
        self.pending = False
        self.geometry = {}
        self.modify = Modify(self)
        self.add(
            "heading",
            "FixedText",
            8,
            8,
            284,
            32,
            Label="Save to keep document choices.",
        )
        self.add(
            "scope",
            "ListBox",
            8,
            44,
            284,
            28,
            Dropdown=True,
            StringItemList=("Remember for this document", "Remember for this project", "Remember everywhere"),
            SelectedItems=(0,),
        )
        self.add("issues", "ListBox", 8, 80, 284, 130, Dropdown=False, MultiSelection=False)
        self.selection = Selection(self, self.details)
        self.dialog.getControl("issues").addItemListener(self.selection)
        self.add("message", "Edit", 8, 218, 284, 70, MultiLine=True, ReadOnly=True, VScroll=True)
        self.add("suggestions", "ListBox", 8, 296, 284, 52, Dropdown=False)
        self.button("previous", "Previous", 8, 356, 84, lambda: self.move(-1))
        self.button("next", "Next", 100, 356, 84, lambda: self.move(1))
        self.button("apply", "Apply", 192, 356, 100, self.apply)
        self.button("ignore", "Ignore once", 8, 392, 138, self.ignore)
        self.button("locate", "Show in document", 154, 392, 138, self.locate)
        self.button("disable", "Disable rule", 8, 428, 138, self.disable)
        self.button("word", "Remember word", 154, 428, 138, self.word)
        self.button("rules", "Grammar rules", 8, 464, 138, self.browse_rules)
        self.button("settings", "Document / project", 154, 464, 138, self.settings)
        self.button("vocabulary", "Words and terminology", 8, 500, 284, self.vocabulary)
        self.add("auto", "CheckBox", 8, 536, 284, 24, Label="Recheck after edits", State=1)
        self.button("check", "Check document", 8, 568, 284, self.check)
        self.add("status", "FixedText", 8, 604, 284, 60, Label="Ready")
        self.resize = Resize(self)
        self.dialog.addWindowListener(self.resize)
        document.addModifyListener(self.modify)
        self.dialog.setVisible(True)
        app.windows.append(self)
        self.layout(300)
        self.post(self.check)

    def add(self, name, kind, x, y, width, height, **props):
        model = service(self.ctx, "awt.UnoControl" + kind + "Model")
        for key, value in props.items():
            setattr(model, key, value)
        control = service(self.ctx, "awt.UnoControl" + kind)
        control.setModel(model)
        self.dialog.addControl(name, control)
        self.model.controls[name] = model
        self.geometry[name] = (x, y, width, height)
        control.setPosSize(x, y, width, height, 15)
        control.setVisible(True)
        return model

    def button(self, name, label, x, y, width, fn):
        self.add(name, "Button", x, y, width, 28, Label=label)
        action = Action(self, fn)
        self.actions.append(action)
        self.dialog.getControl(name).addActionListener(action)

    def layout(self, width):
        if self.closed:
            return
        scale = max(300, width) / 300
        for name, (x, y, w, h) in self.geometry.items():
            self.dialog.getControl(name).setPosSize(round(x * scale), y, round(w * scale), h, 15)

    def target(self):
        scope = self.dialog.getControl("scope").getSelectedItemPos()
        return (
            None
            if scope == 2
            else ScopeTarget(self.app, self.document, "project" if scope == 1 else "document")
        )

    def disable(self):
        _, (_, _, issue) = self.selected()
        target = self.target()
        if target:
            target.update(lambda d: d.setdefault("rules", {}).update({issue["rule"]: False}))
        else:
            self.app.store.set_rule(issue["rule"], False)
            self.app.changed()

    def word(self):
        _, (_, _, issue) = self.selected()
        if issue["rule"] != "SpellCheck":
            raise ValueError("Select a spelling finding to remember a word.")
        target = self.target()
        if target:
            target.update(lambda d: d.update(words=sorted(set(d.get("words", [])) | {issue["text"]})))
        else:
            self.app.store.add_word(issue["text"])
            self.app.changed()

    def vocabulary(self):
        from .scope_ui import Vocabulary

        target = self.target()
        Vocabulary(
            self.app, self.document, target.kind if target else "global", target.path if target else None
        ).show()

    def browse_rules(self):
        scope = self.dialog.getControl("scope").getSelectedItemPos()
        RuleBrowser(self.app, self.document, {0: 2, 1: 3, 2: 0}.get(scope, 2)).show()

    def show(self):
        self.dialog.setVisible(True)


class Panel(unohelper.Base, XUIElement, XToolPanel, XSidebarPanel, XComponent):
    def __init__(self, app, frame, parent):
        self.frame = frame
        self.review = SidebarReview(app, frame.Controller.Model, parent)
        self.Window = self.review.dialog
        self.Frame = frame
        self.ResourceURL = RESOURCE
        self.Type = uno.getConstantByName("com.sun.star.ui.UIElementType.TOOLPANEL")
        self.listeners = []
        self.disposed = False

    def getFrame(self):
        return self.frame

    def getResourceURL(self):
        return RESOURCE

    def getType(self):
        return uno.getConstantByName("com.sun.star.ui.UIElementType.TOOLPANEL")

    def getRealInterface(self):
        return self

    def getWindow(self):
        return self.review.dialog

    def createAccessible(self, parent):
        return self.review.dialog.getPeer()

    def getHeightForWidth(self, width):
        self.review.layout(width)
        result = uno.createUnoStruct("com.sun.star.ui.LayoutSize")
        result.Minimum, result.Preferred, result.Maximum = 672, 672, -1
        return result

    def getMinimalWidth(self):
        return 300

    def addEventListener(self, listener):
        self.listeners.append(listener)

    def removeEventListener(self, listener):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.review.close()
        event = uno.createUnoStruct("com.sun.star.lang.EventObject", self)
        for listener in self.listeners:
            try:
                listener.disposing(event)
            except Exception:
                pass
        self.listeners = []


class SidebarFactory(unohelper.Base, XUIElementFactory, XServiceInfo):
    def __init__(self, ctx):
        self.app = runtime(ctx)

    def getImplementationName(self):
        return FACTORY

    def getSupportedServiceNames(self):
        return ("com.sun.star.ui.UIElementFactory",)

    def supportsService(self, name):
        return name in self.getSupportedServiceNames()

    def createUIElement(self, url, args):
        try:
            if url != RESOURCE:
                raise ValueError("Unknown LibreHarp panel resource.")
            values = {arg.Name: arg.Value for arg in args}
            return Panel(self.app, values["Frame"], values["ParentWindow"])
        except Exception:
            self.app.log_error()
            raise
