"""A native, resizable Writer sidebar. Shares review behavior with the window."""

import threading

import uno
import unohelper
from com.sun.star.awt import XWindowListener
from com.sun.star.lang import XComponent, XServiceInfo
from com.sun.star.ui import XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory

from . import accessibility, layout
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
            service(app.ctx, "awt.AsyncCallback").addCallback(Callback(lambda: focus_panel(app, frame)), None)
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


def focus_panel(app, frame):
    for window in app.windows:
        if (
            isinstance(window, SidebarReview)
            and not window.closed
            and window.document.CurrentController.Frame == frame
        ):
            accessibility.focus_first(window)
            break


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
        self.dialog = service(self.ctx, "awt.UnoControlDialog")
        viewport_model = service(self.ctx, "awt.UnoControlDialogModel")
        viewport_model.Decoration = False
        viewport_model.VScroll = True
        self.dialog.setModel(viewport_model)
        self.dialog.createPeer(service(self.ctx, "awt.Toolkit"), parent)
        self.actions = []
        self.control_names = []
        self.return_focus = None
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
            StringItemList=("This document", "This project", "Everywhere"),
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
        self.add(
            "auto",
            "CheckBox",
            8,
            522,
            194,
            24,
            Label="Auto r~echeck",
            State=1,
            HelpText="Recheck one second after document edits",
        )
        self.button("check", "~Check", 208, 522, 84, self.check)
        self.add("status", "FixedText", 8, 552, 284, 40, Label="Ready", MultiLine=True)
        self.resize = Resize(self)
        self.dialog.addWindowListener(self.resize)
        document.addModifyListener(self.modify)
        self.dialog.setPosSize(0, 0, 300, 600, 12)
        self.dialog.setVisible(True)
        app.windows.append(self)
        self.layout(300, 600)
        accessibility.configure(self, sidebar=True)
        layout.connect_viewport(self)
        self.post(self.check)

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
        self.control_names.append(name)
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
        scale = layout.sidebar_scale(self.dialog.getControl("check"))
        self.minimum_width = layout.sidebar_width(self, scale)
        row = max(
            round(28 * scale),
            *(
                self.dialog.getControl(n).getMinimumSize().Height
                for n in ("issues", "suggestions", "scope", "more")
            ),
        )
        margin, gap = round(8 * scale), round(6 * scale)
        bars = getattr(self, "viewport_bars", {})
        scroll = {axis: bar.getCurrentValue() for axis, bar in bars.items()}
        for bar in bars.values():
            bar.setCurrentValue(0)
        bar_width = getattr(self, "viewport_insets", {}).get("x", round(14 * scale))
        available = max(1, width - 2 * margin - bar_width)

        def required(name):
            control = self.dialog.getControl(name)
            label = getattr(control.getModel(), "Label", "").replace("~", "")
            if label:
                return round(
                    layout.font(control).getStringWidth(label) + (28 if name == "auto" else 16) * scale
                )
            return round(90 * scale)

        def pack(names, height):
            lines, current, used = [], [], 0
            for name in names:
                need = min(available, required(name))
                if current and used + gap + need > available:
                    lines.append((current, height))
                    current, used = [], 0
                used += (gap if current else 0) + need
                current.append(name)
            if current:
                lines.append((current, height))
            return lines

        header = [(["issues"], row)] + pack(["previous", "next", "ignore"], round(28 * scale))
        footer = (
            pack(["suggestions", "apply"], row)
            + [(["scope"], row)]
            + pack(["more", "run"], row)
            + pack(["auto", "check"], round(28 * scale))
            + [(["status"], round(40 * scale))]
        )
        fixed = 2 * margin + gap * (len(header) + len(footer)) + sum(h for _, h in header + footer)
        self.minimum_height = fixed + round(182 * scale)
        self.preferred_height = self.minimum_height + round(160 * scale)
        height = height if height is not None else self.dialog.getPosSize().Height
        content_height = max(self.minimum_height, height)
        rows = header + [(["message"], content_height - fixed)] + footer
        y = margin
        for names, h in rows:
            minima = [required(n) for n in names]
            spare = max(0, available - gap * (len(names) - 1) - sum(minima))
            x = margin
            for i, name in enumerate(names):
                w = available if len(names) == 1 else minima[i] + spare // len(names)
                self.dialog.getControl(name).setPosSize(x, y, w, h, 15)
                x += w + gap
            y += h + gap
        logical = self.dialog.getPeer().convertSizeToLogic(
            uno.createUnoStruct("com.sun.star.awt.Size", width, content_height),
            uno.getConstantByName("com.sun.star.util.MeasureUnit.APPFONT"),
        )
        self.dialog.getModel().ScrollHeight = logical.Height
        for axis, value in scroll.items():
            bars[axis].setCurrentValue(min(value, bars[axis].getMaximumValue()))

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
        # XToolPanel requires XAccessible, which the control implements. Its
        # window peer is only XWindowPeer and cannot supply the panel subtree.
        return self.review.dialog

    def getHeightForWidth(self, width):
        self.review.layout(width)
        result = uno.createUnoStruct("com.sun.star.ui.LayoutSize")
        result.Minimum, result.Preferred, result.Maximum = (
            # The panel owns scrolling. A content-sized minimum makes Writer
            # clip the entire panel in an outer viewport that cannot reveal focus.
            0,
            self.review.preferred_height,
            -1,
        )
        return result

    def getMinimalWidth(self):
        return self.review.minimum_width

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
