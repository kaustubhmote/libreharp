"""A native, resizable Writer sidebar. Shares review behavior with the window."""

import threading

import uno
import unohelper
from com.sun.star.awt import XAdjustmentListener, XWindowListener
from com.sun.star.awt.FontUnderline import SINGLE
from com.sun.star.awt.FontWeight import BOLD
from com.sun.star.awt.PosSize import HEIGHT
from com.sun.star.lang import XComponent, XServiceInfo
from com.sun.star.ui import XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory

from . import accessibility, layout
from .checker import replacement_is_current
from .rule_help import finding_text
from .scopes import ScopeTarget
from .uno_app import Action, Callback, Modify, Review, RuleBrowser, Selection, runtime, service, units
from .vocabulary import is_word_finding

FACTORY = "org.libreharp.SidebarFactory"
RESOURCE = "private:resource/toolpanel/LibreHarpPanel"


def luminance(rgb):
    red, green, blue = ((rgb >> shift & 255) / 255 for shift in (16, 8, 0))

    def linear(channel):
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    return 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)


def preview_color(style, dark, light):
    if style.HighContrastMode:
        return style.FieldTextColor
    background = luminance(style.FieldColor) + 0.05
    for color in (dark, light):
        foreground = luminance(color) + 0.05
        if max(background, foreground) / min(background, foreground) >= 4.5:
            return color
    return style.FieldTextColor


def advance(cursor, length, select):
    # UNO's XTextCursor accepts a signed 16-bit count in UTF-16 code units.
    while length > 32767:
        cursor.goRight(32767, select)
        length -= 32767
    if length:
        cursor.goRight(length, select)


def open_sidebar(app, frame, *, target=None, attempt=0):
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
            service(app.ctx, "awt.AsyncCallback").addCallback(
                Callback(lambda: focus_panel(app, frame, target)), None
            )
            return
        if attempt >= 30:
            raise RuntimeError(
                "LibreHarp's sidebar deck did not become available. Restart Writer after installation."
            )

        def post():
            service(app.ctx, "awt.AsyncCallback").addCallback(
                Callback(lambda: open_sidebar(app, frame, target=target, attempt=attempt + 1)), None
            )

        timer = threading.Timer(0.1, post)
        timer.daemon = True
        timer.start()
    except Exception:
        app.log_error()


def focus_panel(app, frame, target):
    for window in app.windows:
        if isinstance(window, SidebarReview) and not window.closed and window.frame == frame:
            if target is not None:
                window.focus_finding(target)
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
        if not getattr(self.owner, "fitting", False):
            # Resize events can arrive after a newer host allocation. Replaying
            # their old dimensions can cause a resize/scroll feedback loop.
            rect = self.owner.dialog.getPosSize()
            self.owner.layout(rect.Width, rect.Height)

    def windowMoved(self, event):
        pass

    def windowShown(self, event):
        pass

    def windowHidden(self, event):
        pass

    def disposing(self, event):
        self.owner.close()


class Scroll(unohelper.Base, XAdjustmentListener):
    def __init__(self, owner):
        self.owner = owner

    def adjustmentValueChanged(self, event):
        if not self.owner.closed:
            self.owner.scroll_to(event.Value)

    def disposing(self, event):
        pass


class ScrollValue:
    """The same pixel offset for native scrollbar events and keyboard reveal."""

    def __init__(self, owner):
        self.owner = owner

    def getCurrentValue(self):
        return self.owner.scroll_position

    def getMaximumValue(self):
        return max(0, self.owner.content_height - self.owner.dialog.getPosSize().Height)

    def setCurrentValue(self, value):
        self.owner.scroll_to(value)


class SidebarReview(Review):
    def __init__(self, app, document, parent, *, frame=None):
        self.app, self.ctx, self.document = app, app.ctx, document
        self.frame = frame if frame is not None else document.CurrentController.Frame
        self.finding_target = None
        self.model = Models()
        self.dialog = service(self.ctx, "awt.UnoControlContainer")
        self.dialog.setModel(service(self.ctx, "awt.UnoControlContainerModel"))
        self.dialog.createPeer(service(self.ctx, "awt.Toolkit"), parent)
        self.actions = []
        self.control_names = []
        self.return_focus = None
        self.closed = False
        self.rows, self.generation, self.timer = [], 0, None
        self.pending = False
        self.geometry = {}
        self.positions = {}
        self.scroll_position, self.content_height = 0, 0
        self.updating_suggestions = False
        self.scrollbar = service(self.ctx, "awt.UnoControlScrollBar")
        scroll_model = service(self.ctx, "awt.UnoControlScrollBarModel")
        scroll_model.Orientation = 1
        if scroll_model.getPropertySetInfo().hasPropertyByName("Tabstop"):
            scroll_model.Tabstop = False
        self.scrollbar.setModel(scroll_model)
        self.dialog.addControl("viewport_scrollbar", self.scrollbar)
        self.scroll_listener = Scroll(self)
        self.scrollbar.addAdjustmentListener(self.scroll_listener)
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
            "RichText",
            8,
            74,
            284,
            342,
            RichText=True,
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
        self.suggestion_selection = Selection(self, self.show_finding)
        self.dialog.getControl("suggestions").addItemListener(self.suggestion_selection)
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
            LineCount=12,
            StringItemList=("More actions...",),
            SelectedItems=(0,),
            HelpText="Choose an action, then press Go",
        )
        self.button("run", "~Go", 218, 488, 74, self.run_action)
        self.more_actions = []
        self.action_selection = Selection(self, self.action_changed)
        self.dialog.getControl("more").addItemListener(self.action_selection)
        self.add(
            "auto",
            "CheckBox",
            8,
            522,
            194,
            24,
            Label="Auto r~echeck",
            State=1,
            HelpText="Recheck after document edits using the delay in Advanced settings",
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
        self.viewport_bars = {"y": ScrollValue(self)}
        self.scrollbar.getPeer().setProperty("AccessibleName", "Sidebar scrollbar")
        self.refresh_actions()
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
        model_service, control_service = (
            ("form.component.TextField", "form.control.TextField")
            if kind == "RichText"
            else ("awt.UnoControl" + kind + "Model", "awt.UnoControl" + kind)
        )
        model = service(self.ctx, model_service)
        if model.getPropertySetInfo().hasPropertyByName("TabIndex"):
            model.TabIndex = len(self.model.controls)
        for key, value in props.items():
            setattr(model, key, value)
        control = service(self.ctx, control_service)
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

    def layout(self, width, height=None, measure=False):
        if self.closed:
            return
        if not measure:
            rect = self.dialog.getPosSize()
            height = rect.Height if height is None else height
            width, height = layout.visible_size(self.dialog, width, height)
            if (rect.Width, rect.Height) != (width, height):
                self.fitting = True
                try:
                    self.dialog.setPosSize(0, 0, width, height, 12)
                finally:
                    self.fitting = False
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
        bar_width = round(14 * scale)
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
        minimum_height = fixed + round(182 * scale)
        preferred_height = minimum_height + round(160 * scale)
        if measure:
            return minimum_height, preferred_height
        self.minimum_height, self.preferred_height = minimum_height, preferred_height
        scroll = self.scroll_position
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
                self.positions[name] = (x, y, w, h)
                x += w + gap
            y += h + gap
        self.content_height = content_height
        self.viewport_insets = {"x": bar_width, "y": 0}
        self.scrollbar.setPosSize(width - bar_width, 0, bar_width, height, 15)
        model = self.scrollbar.getModel()
        model.ScrollValueMax, model.VisibleSize = content_height, height
        model.LineIncrement, model.BlockIncrement = row, max(row, height - row)
        self.scrollbar.setVisible(True)
        self.scroll_to(scroll, force=True)

    def scroll_to(self, value, force=False):
        value = max(0, min(round(value), self.content_height - self.dialog.getPosSize().Height))
        if not force and value == self.scroll_position:
            return
        self.scroll_position = value
        for name, (x, y, width, height) in self.positions.items():
            self.dialog.getControl(name).setPosSize(x, y - value, width, height, 15)
        self.scrollbar.setValue(value)

    def details(self):
        index, (_, _, issue) = self.selected()
        self.updating_suggestions = True
        try:
            self.set_suggestions(issue)
        finally:
            self.updating_suggestions = False
        self.show_finding()
        self.model.getByName("apply").Enabled = bool(issue["suggestions"])
        self.model.getByName("previous").Enabled = index > 0
        self.model.getByName("next").Enabled = index + 1 < len(self.rows)
        self.refresh_actions(issue)

    def show_finding(self):
        if self.updating_suggestions:
            return
        index, (_, original, issue) = self.selected()
        choice = self.dialog.getControl("suggestions").getSelectedItemPos()
        suggestions = issue["suggestions"]
        replacement = suggestions[choice] if 0 <= choice < len(suggestions) else None
        text, flagged, suggested = finding_text(original, issue, index + 1, len(self.rows), replacement)
        control = self.dialog.getControl("message")
        peer = control.getPeer()
        model = control.getModel()
        model.String = text
        style = peer.StyleSettings
        font = style.FieldFont
        cursor = model.createTextCursor()
        cursor.gotoStart(False)
        cursor.gotoEnd(True)
        cursor.CharColor = style.FieldTextColor
        if font.Name and font.Height > 0:
            cursor.CharFontName = font.Name
            cursor.CharHeight = font.Height

        def select(span):
            start, end = span
            cursor = model.createTextCursor()
            cursor.gotoStart(False)
            advance(cursor, units(text[:start]), False)
            advance(cursor, units(text[start:end]), True)
            return cursor

        cursor = select(flagged)
        cursor.CharColor = preview_color(style, 0xB3261E, 0xFF9A94)
        cursor.CharUnderline = SINGLE
        if suggested is not None:
            cursor = select(suggested)
            cursor.CharColor = preview_color(style, 0x176B38, 0x8DDEA1)
            cursor.CharWeight = BOLD
        # Formatting can scroll the native rich-text peer to the bottom.
        # A size change restores the top without moving keyboard focus.
        rect = control.getPosSize()
        control.setPosSize(0, 0, 0, rect.Height + 1, HEIGHT)
        control.setPosSize(0, 0, 0, rect.Height, HEIGHT)
        # The rich-text peer exposes a named panel in the accessibility tree.
        start, end = flagged
        peer.setProperty("AccessibleName", text[:start] + " [flagged: " + text[start:end] + "] " + text[end:])

    def finding_index(self, target):
        return next((index for index, row in enumerate(self.rows) if target.matches(row)), None)

    def focus_finding(self, target):
        index = self.finding_index(target)
        # Keep the target until any in-flight check delivers its fresh rows.
        self.finding_target = target if self.pending or index is None else None
        if index is not None:
            self.dialog.getControl("issues").selectItemPos(index, True)
            self.details()
        elif not self.pending:
            self.check()

    def display(self):
        index = self.dialog.getControl("issues").getSelectedItemPos()
        if self.finding_target is not None:
            match = self.finding_index(self.finding_target)
            if match is not None:
                index = match
            if not self.pending:
                self.finding_target = None
        super().display(max(0, min(index, len(self.rows) - 1)))
        if self.rows:
            self.model.getByName("ignore").Enabled = True
        else:
            message = "No findings to display. Use Check to review the document."
            self.model.getByName("message").Text = message
            self.dialog.getControl("message").getPeer().setProperty("AccessibleName", message)
            self.model.getByName("apply").Enabled = False
            for name in ("previous", "next", "ignore"):
                self.model.getByName(name).Enabled = False
            self.refresh_actions()

    def refresh_actions(self, issue=None):
        actions = []
        spelling = is_word_finding(issue)
        if spelling:
            actions.append(("Add word globally", self.global_word))
        if issue is not None:
            actions.extend((("Show in document", self.locate), ("Disable rule", self.disable)))
            if not self.document.isReadonly():
                actions.append(("Remember this ignore", self.remember_ignore))
        if spelling:
            actions.append(("Remember word in selected scope", self.word))
        actions.extend(
            (
                ("Grammar rules", self.browse_rules),
                ("Document / project settings", self.settings),
                ("Words and terminology", self.vocabulary),
                ("Manage saved ignores", self.manage_ignores),
            )
        )
        self.updating_actions = True
        try:
            self.more_actions = actions
            self.model.getByName("more").StringItemList = ("More actions...",) + tuple(
                label for label, _ in actions
            )
            self.dialog.getControl("more").selectItemPos(1 if spelling else 0, True)
        finally:
            self.updating_actions = False
        self.action_changed()

    def action_changed(self):
        if getattr(self, "updating_actions", False):
            return
        index = self.dialog.getControl("more").getSelectedItemPos()
        action = self.more_actions[index - 1][1] if 0 < index <= len(self.more_actions) else None
        global_word = action == self.global_word
        button = self.model.getByName("run")
        button.Label = "Add ~globally" if global_word else "~Go"
        button.Enabled = action is not None
        help_text = "Run the selected action"
        if global_word:
            _, (_, _, issue) = self.selected()
            help_text = f'Add "{issue["text"]}" to your global dictionary for all documents and profiles.'
        button.HelpText = help_text
        self.dialog.getControl("run").getPeer().setProperty(
            "AccessibleName", help_text if global_word else "Go"
        )
        self.model.getByName("more").HelpText = (
            help_text if global_word else "Choose an action, then press Go"
        )
        rect = self.dialog.getPosSize()
        self.layout(rect.Width, rect.Height)

    def run_action(self):
        index = self.dialog.getControl("more").getSelectedItemPos()
        if 0 < index <= len(self.more_actions):
            self.more_actions[index - 1][1]()

    def spelling_word(self):
        _, (paragraph, original, issue) = self.selected()
        if not is_word_finding(issue):
            raise ValueError("Select a spelling or word-splitting finding to remember a word.")
        if not replacement_is_current(original, paragraph.String, issue):
            self.check()
            raise ValueError("This paragraph changed. Check again before remembering its word.")
        return issue["text"]

    def global_word(self):
        word = self.spelling_word()
        self.app.store.add_word(word)
        self.app.record("Remembered word", self.selected()[1][2])
        self.app.changed()

    def ignore(self):
        index, (_, _, issue) = self.selected()
        self.rows.pop(index)
        self.app.record("Ignored", issue)
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
        word = self.spelling_word()
        _, (_, _, issue) = self.selected()
        target = self.target()
        if target:
            target.update(lambda d: d.update(words=sorted(set(d.get("words", [])) | {word})))
        else:
            self.app.store.add_word(word)
            self.app.changed()
        self.app.record("Remembered word", issue)

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
        self.review = SidebarReview(app, frame.Controller.Model, parent, frame=frame)
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
        # Writer probes hypothetical widths. Measuring must not rearrange the
        # currently visible panel, whose assigned width may be smaller.
        _, preferred = self.review.layout(width, measure=True)
        result = uno.createUnoStruct("com.sun.star.ui.LayoutSize")
        result.Minimum, result.Preferred, result.Maximum = (
            # The panel owns scrolling. A content-sized minimum makes Writer
            # clip the entire panel in an outer viewport that cannot reveal focus.
            0,
            preferred,
            -1,
        )
        return result

    def getMinimalWidth(self):
        # Generic VCL otherwise puts the panel in an outer horizontal viewport.
        # The internal layout wraps to the actual assigned width instead.
        return 0

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
