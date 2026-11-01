"""A native, resizable Writer sidebar. Shares review behavior with the window."""

import threading

import uno
import unohelper
from com.sun.star.awt import XWindowListener
from com.sun.star.lang import XComponent, XServiceInfo
from com.sun.star.ui import XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory

from .rule_help import finding_text
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
        self.owner.layout(event.Width, event.Height)

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
            "issues",
            "ListBox",
            8,
            8,
            284,
            28,
            Dropdown=True,
            LineCount=12,
            MultiSelection=False,
            HelpText="Findings in this document",
        )
        self.selection = Selection(self, self.details)
        self.dialog.getControl("issues").addItemListener(self.selection)
        self.button("previous", "~Previous", 8, 42, 90, lambda: self.move(-1))
        self.button("next", "~Next", 104, 42, 90, lambda: self.move(1))
        self.button("ignore", "~Ignore once", 200, 42, 92, self.ignore)
        self.add(
            "message",
            "Edit",
            8,
            74,
            284,
            342,
            MultiLine=True,
            ReadOnly=True,
            VScroll=True,
            HelpText="Selected finding, context, explanation, and example",
        )
        self.add(
            "suggestions",
            "ListBox",
            8,
            422,
            204,
            28,
            Dropdown=True,
            LineCount=8,
            HelpText="Suggested replacement",
        )
        self.button("apply", "~Apply", 218, 422, 74, self.apply)
        self.add(
            "scope",
            "ListBox",
            8,
            456,
            284,
            26,
            Dropdown=True,
            StringItemList=("Remember for this document", "Remember for this project", "Remember everywhere"),
            SelectedItems=(0,),
            HelpText="Scope for Disable rule and Remember word. Save the document to retain document choices.",
        )
        self.add(
            "more",
            "ListBox",
            8,
            488,
            204,
            28,
            Dropdown=True,
            LineCount=7,
            StringItemList=(
                "More actions...",
                "Show in document",
                "Disable rule",
                "Remember word",
                "Grammar rules",
                "Document / project settings",
                "Words and terminology",
            ),
            SelectedItems=(0,),
            HelpText="Choose an action, then press Go",
        )
        self.button("run", "~Go", 218, 488, 74, self.run_action)
        self.add("auto", "CheckBox", 8, 522, 194, 24, Label="Recheck after ~edits", State=1)
        self.button("check", "~Check", 208, 522, 84, self.check)
        self.add("status", "FixedText", 8, 552, 284, 40, Label="Ready", MultiLine=True)
        self.resize = Resize(self)
        self.dialog.addWindowListener(self.resize)
        document.addModifyListener(self.modify)
        self.dialog.setVisible(True)
        app.windows.append(self)
        self.layout(300, 600)
        self.post(self.check)

    def add(self, name, kind, x, y, width, height, **props):
        model = service(self.ctx, "awt.UnoControl" + kind + "Model")
        if model.getPropertySetInfo().hasPropertyByName("TabIndex"):
            model.TabIndex = len(self.model.controls)
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

    def layout(self, width, height=None):
        if self.closed:
            return
        height = max(440, height if height is not None else self.dialog.getPosSize().Height)
        message_height = height - 258
        scale = max(300, width) / 300
        for name, (x, y, w, h) in self.geometry.items():
            if name == "message":
                h = message_height
            elif y >= 422:
                y += message_height - 342
            self.dialog.getControl(name).setPosSize(round(x * scale), y, round(w * scale), h, 15)

    def details(self):
        super().details()
        index, (_, original, issue) = self.selected()
        self.model.getByName("message").Text = finding_text(original, issue, index + 1, len(self.rows))
        self.model.getByName("apply").Enabled = bool(issue["suggestions"])
        self.model.getByName("previous").Enabled = index > 0
        self.model.getByName("next").Enabled = index + 1 < len(self.rows)

    def display(self):
        index = self.dialog.getControl("issues").getSelectedItemPos()
        super().display()
        if self.rows:
            self.dialog.getControl("issues").selectItemPos(max(0, min(index, len(self.rows) - 1)), True)
            self.details()
            self.model.getByName("ignore").Enabled = True
        else:
            self.model.getByName("message").Text = "No findings to display. Use Check to review the document."
            self.model.getByName("apply").Enabled = False
            for name in ("previous", "next", "ignore"):
                self.model.getByName(name).Enabled = False

    def run_action(self):
        index = self.dialog.getControl("more").getSelectedItemPos()
        actions = (self.locate, self.disable, self.word, self.browse_rules, self.settings, self.vocabulary)
        if index > 0:
            actions[index - 1]()
            self.dialog.getControl("more").selectItemPos(0, True)

    def ignore(self):
        index, _ = self.selected()
        self.rows.pop(index)
        self.display()
        self.status("Ignored until the next check. More actions > Disable rule saves a lasting choice.")

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
        result.Minimum, result.Preferred, result.Maximum = 440, 600, -1
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
