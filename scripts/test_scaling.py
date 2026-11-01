"""Native font/DPI regressions. Run each scale in a separate LibreOffice process."""

import json
import os
import subprocess
import traceback

import test_libreoffice as test
import uno
from test_accessibility import wait_for, window_id

from libreharp import layout
from libreharp.accessibility import focused
from libreharp.migration_ui import Migration
from libreharp.scope_ui import ScopedSettings, Vocabulary
from libreharp.sidebar import SidebarReview
from libreharp.uno_app import Review, RuleBrowser, Runtime, Settings, service

CASE = os.environ.get("LIBREHARP_SCALE_CASE", "default")


def press(window, sequence):
    xid = window_id(window.model.Title)
    subprocess.run(["xdotool", "windowactivate", "--sync", xid], check=True, timeout=5)
    active = wait_for(
        lambda: subprocess.check_output(["xdotool", "getactivewindow"], text=True).strip() == xid
    )
    if not active:
        actual = subprocess.check_output(["xdotool", "getactivewindow"], text=True).strip()
        print(
            "Activation",
            xid,
            actual,
            subprocess.check_output(["xdotool", "getwindowname", actual], text=True),
            "closed",
            window.closed,
            flush=True,
        )
    assert active
    subprocess.run(["xdotool", "key", "--clearmodifiers", sequence], check=True, timeout=5)


def capture(xid, name):
    subprocess.run(
        ["import", "-window", xid, str(test.ZONE / f"scaling-{CASE}-{name}.png")],
        check=True,
        timeout=15,
    )


def inside(window, name):
    control = window.dialog.getControl(name)
    bounds = control.getPosSize()
    viewport = window.dialog.getPosSize()
    return (
        bounds.X >= 0
        and bounds.Y >= 0
        and bounds.X + bounds.Width <= viewport.Width
        and bounds.Y + bounds.Height <= viewport.Height
    )


def check_text(window):
    failures = []
    for name in window.control_names:
        control = window.dialog.getControl(name)
        model = control.getModel()
        if not model.supportsService("com.sun.star.awt.UnoControlButtonModel"):
            continue
        metrics = layout.font(control).getFontMetric()
        rect = control.getPosSize()
        text_width = layout.font(control).getStringWidth(model.Label.replace("~", ""))
        if rect.Height < metrics.Ascent + metrics.Descent or rect.Width < text_width + 8:
            failures.append(name)
    test.record(type(window).__name__ + " button labels fit at this scale", not failures)


def main():
    ctx = test.start(visible=True)
    app = Runtime(ctx)
    doc = test.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    doc.Text.String = "This is a example. This is is incorrect."
    doc.CharLocale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    doc.storeAsURL(
        (test.ZONE / "LibreHarp-scaling-test.odt").as_uri(),
        (test.prop("FilterName", "writer8"), test.prop("Overwrite", True)),
    )
    area = service(ctx, "awt.Toolkit").getWorkArea()
    test.REPORT["case"] = CASE
    test.REPORT["environment"] = {
        k: os.environ.get(k) for k in ("SAL_USE_VCLPLUGIN", "SAL_FORCEDPI", "GDK_SCALE", "GDK_DPI_SCALE")
    }
    test.REPORT["dialogs"] = {}
    try:
        for cls in (Settings, RuleBrowser, ScopedSettings, Vocabulary, Migration, Review):
            window = cls(app) if cls is Settings else cls(app, doc)
            window.show()
            assert wait_for(lambda: hasattr(window, "viewport_listeners"))
            xid = window_id(window.model.Title)
            press(window, "Tab")
            rect = window.dialog.getPosSize()
            test.REPORT["dialogs"][cls.__name__] = dict(
                width=rect.Width,
                height=rect.Height,
                horizontal_scroll=window.model.HScroll,
                vertical_scroll=window.model.VScroll,
            )
            test.record(
                cls.__name__ + " fits the display",
                rect.Width <= area.Width * 0.95 and rect.Height <= area.Height * 0.9,
            )
            check_text(window)
            press(window, "F8")
            test.record(
                cls.__name__ + " F8 reveals Status",
                wait_for(lambda: focused(window.dialog.getControl("status")) and inside(window, "status")),
            )
            if cls is Settings:
                capture(xid, "settings-status")
                window.dialog.getControl("profile").setFocus()
                test.record(
                    "Returning to the first field scrolls back to the top",
                    wait_for(lambda: inside(window, "profile") and window.model.ScrollTop == 0),
                )
                capture(xid, "settings-top")
                visited = {"profile"}
                expected = {
                    n for n in window.control_names if getattr(window.model.getByName(n), "Tabstop", False)
                }
                for _ in range(len(expected) + 4):
                    previous = {n for n in expected if focused(window.dialog.getControl(n))}
                    press(window, "Tab")
                    assert wait_for(
                        lambda: any(focused(window.dialog.getControl(n)) for n in expected - previous)
                    ), previous
                    selected = next(n for n in expected if focused(window.dialog.getControl(n)))
                    assert wait_for(lambda: inside(window, selected)), selected
                    visited.add(selected)
                test.record("Tab reveals every Settings field and action", expected <= visited)
            press(window, "Escape")
            test.record(cls.__name__ + " remains keyboard dismissible", wait_for(lambda: window.closed))
        panel = SidebarReview(app, doc, doc.CurrentController.Frame.ContainerWindow)
        scale = layout.sidebar_scale(panel.dialog.getControl("check"))
        test.REPORT["sidebar"] = dict(
            scale=scale, minimum_width=panel.minimum_width, minimum_height=panel.minimum_height
        )
        panel.dialog.setPosSize(0, 0, panel.minimum_width, panel.minimum_height, 15)
        panel.layout(panel.minimum_width, panel.minimum_height)
        test.record(
            "Sidebar rows grow with native font and DPI",
            panel.dialog.getControl("check").getPosSize().Height >= round(28 * scale),
        )
        check_text(panel)
        rectangles = [panel.dialog.getControl(n).getPosSize() for n in panel.control_names]
        test.record(
            "Sidebar controls fit its advertised minimum size",
            all(
                r.X >= 0
                and r.Y >= 0
                and r.X + r.Width <= panel.minimum_width
                and r.Y + r.Height <= panel.minimum_height
                for r in rectangles
            ),
        )
        test.record(
            "Sidebar controls do not overlap",
            all(
                a.X + a.Width <= b.X or b.X + b.Width <= a.X or a.Y + a.Height <= b.Y or b.Y + b.Height <= a.Y
                for i, a in enumerate(rectangles)
                for b in rectangles[i + 1 :]
            ),
        )
        before = panel.dialog.getControl("message").getPosSize().Height
        panel.layout(panel.minimum_width, panel.minimum_height + 200)
        test.record(
            "Extra sidebar height still goes to the explanation",
            panel.dialog.getControl("message").getPosSize().Height == before + 200,
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
        (test.ZONE / f"scaling-{CASE}-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
