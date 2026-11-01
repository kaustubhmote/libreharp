"""Font-aware sidebar metrics and a keyboard-reachable dialog viewport."""

import math

import uno
import unohelper
from com.sun.star.accessibility import XAccessibleEventListener
from com.sun.star.awt import XCallback, XFocusListener


def font(control):
    peer = control.getPeer()
    return peer.getFont(peer.getProperty("FontDescriptor"))


def sidebar_scale(control):
    metric = font(control).getFontMetric()
    pixels = control.getPeer().convertSizeToPixel(
        uno.createUnoStruct("com.sun.star.awt.Size", 2540, 2540),
        uno.getConstantByName("com.sun.star.util.MeasureUnit.MM_100TH"),
    )
    return max(1.0, pixels.Height / 96, (metric.Ascent + metric.Descent + metric.Leading) / 19)


def sidebar_width(owner, scale):
    width = 300 * scale
    for name in ("previous", "next", "ignore", "apply", "run", "check", "auto"):
        control = owner.dialog.getControl(name)
        label = control.getModel().Label.replace("~", "")
        padding = (28 if name == "auto" else 16) * scale
        required = font(control).getStringWidth(label) + padding
        width = max(width, required * 300 / owner.geometry[name][2])
    scope = owner.dialog.getControl("scope")
    width = max(width, scope.getPreferredSize().Width + 16 * scale)
    return math.ceil(width)


def visible_size(control, width, height):
    """Account for a host viewport that clips its larger panel allocation."""
    context = control.getAccessibleContext()
    origin = context.getLocationOnScreen()
    right, bottom = origin.X + width, origin.Y + height
    parent = context.getAccessibleParent()
    for _ in range(24):
        if parent is None:
            break
        context = parent.getAccessibleContext()
        point, size = context.getLocationOnScreen(), context.getSize()
        if size.Width > 0 and size.Height > 0:
            right, bottom = min(right, point.X + size.Width), min(bottom, point.Y + size.Height)
        parent = context.getAccessibleParent()
    return max(1, right - origin.X), max(1, bottom - origin.Y)


class Refocus(unohelper.Base, XCallback):
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def notify(self, data):
        if not self.owner.closed:
            from .accessibility import focused

            if any(
                focused(self.owner.dialog.getControl(n)) for n in self.owner.control_names if n != self.name
            ):
                return
            self.owner.dialog.getControl(self.name).setFocus()


class Reveal(unohelper.Base, XFocusListener):
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def focusGained(self, event):
        if not self.owner.closed:
            reveal(self.owner, self.name)

    def focusLost(self, event):
        pass

    def disposing(self, event):
        pass


class AccessibleReveal(unohelper.Base, XAccessibleEventListener):
    def __init__(self, owner, name):
        self.owner, self.name = owner, name

    def notifyEvent(self, event):
        from .accessibility import focused

        if (
            not self.owner.closed
            and event.EventId
            == uno.getConstantByName("com.sun.star.accessibility.AccessibleEventId.STATE_CHANGED")
            and event.NewValue
            == uno.getConstantByName("com.sun.star.accessibility.AccessibleStateType.FOCUSED")
            and focused(self.owner.dialog.getControl(self.name))
        ):
            reveal(self.owner, self.name)

    def disposing(self, event):
        pass


def reveal(owner, name):
    rect = owner.dialog.getControl(name).getPosSize()
    viewport = owner.dialog.getPosSize()
    changed = False
    for axis, bar in owner.viewport_bars.items():
        current = bar.getCurrentValue()
        position = rect.X if axis == "x" else rect.Y
        length = rect.Width if axis == "x" else rect.Height
        available = viewport.Width if axis == "x" else viewport.Height
        # Reserve space for the perpendicular scrollbar and focus margin.
        available -= owner.viewport_insets[axis] + 6
        target = current
        if position < 4:
            target += position - 4
        elif position + length > available:
            target += min(position - 4, position + length - available)
        if name == owner.focus_name:
            target = 0
        target = max(0, min(target, bar.getMaximumValue()))
        if target != current:
            bar.setCurrentValue(target)
            changed = True
    if changed:
        owner.ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.awt.AsyncCallback", owner.ctx
        ).addCallback(Refocus(owner, name), None)


def focus_control(owner, name):
    if hasattr(owner, "viewport_bars"):
        reveal(owner, name)
    owner.dialog.getControl(name).setFocus()


def prepare_dialog(owner):
    """Create native scrollbars before the peer; font metrics settle when mapped."""
    if hasattr(owner, "viewport_size"):
        return
    model = owner.model
    model.Sizeable = True
    model.ScrollWidth, model.ScrollHeight = model.Width, model.Height + 8
    model.HScroll, model.VScroll = True, True
    owner.viewport_size = (model.Width, model.Height)
    # GTK can retain an oversized outer frame if the first mapped dialog is
    # larger than the display. Start small, then fit using the mapped font.
    model.Width, model.Height = min(model.Width, 200), min(model.Height, 120)


def fit_dialog(owner):
    """Connect keyboard reveal to the same absolute scrollbar used by the mouse."""
    if owner.closed or hasattr(owner, "viewport_listeners"):
        return
    dialog = owner.dialog
    area = dialog.getPeer().getToolkit().getWorkArea()
    desired = dialog.getPeer().convertSizeToPixel(
        uno.createUnoStruct("com.sun.star.awt.Size", owner.viewport_size[0], owner.viewport_size[1] + 8),
        uno.getConstantByName("com.sun.star.util.MeasureUnit.APPFONT"),
    )
    width = min(desired.Width, math.floor(area.Width * 0.94))
    height = min(desired.Height, math.floor(area.Height * 0.88))
    dialog.setPosSize(
        area.X + (area.Width - width) // 2, area.Y + (area.Height - height) // 2, width, height, 15
    )
    connect_viewport(owner)
    for name in owner.control_names:
        control = dialog.getControl(name)
        model = control.getModel()
        bounds = control.getPosSize()
        available = width - owner.viewport_insets["x"] - bounds.X - 6
        if (
            (
                getattr(model, "MultiLine", False)
                or model.supportsService("com.sun.star.awt.UnoControlListBoxModel")
            )
            and not model.supportsService("com.sun.star.awt.UnoControlFixedTextModel")
            and bounds.Width > available > 0
        ):
            model.Width = max(1, math.floor(model.Width * available / bounds.Width))


def connect_viewport(owner):
    dialog = owner.dialog
    owner.viewport_bars, owner.viewport_insets = {}, {"x": 0, "y": 0}
    context = dialog.getAccessibleContext()
    for index in range(context.getAccessibleChildCount()):
        child = context.getAccessibleChild(index).getAccessibleContext()
        if child.getAccessibleRole() == uno.getConstantByName(
            "com.sun.star.accessibility.AccessibleRole.SCROLL_BAR"
        ):
            bounds = child.getBounds()
            horizontal = uno.getConstantByName("com.sun.star.accessibility.AccessibleStateType.HORIZONTAL")
            states = child.getAccessibleStateSet()
            is_horizontal = (
                bool(states & horizontal) if isinstance(states, int) else states.contains(horizontal)
            )
            axis = "x" if is_horizontal else "y"
            owner.viewport_bars[axis] = child
            owner.viewport_insets["y" if axis == "x" else "x"] = min(bounds.Width, bounds.Height)
    owner.viewport_listeners = []
    for name in owner.control_names:
        listener = Reveal(owner, name)
        dialog.getControl(name).addFocusListener(listener)
        owner.viewport_listeners.append(listener)
        accessible_listener = AccessibleReveal(owner, name)
        owner.viewport_listeners.append(accessible_listener)

        def watch(context, depth=0):
            context.addAccessibleEventListener(accessible_listener)
            if depth < 3:
                for index in range(min(32, context.getAccessibleChildCount())):
                    watch(context.getAccessibleChild(index).getAccessibleContext(), depth + 1)

        watch(dialog.getControl(name).getAccessibleContext())
    owner.viewport_ready = True
