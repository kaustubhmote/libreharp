"""Run with the GTK3 backend and a private D-Bus session; no user settings are changed."""

import json
import os
import subprocess
import time
import traceback

import test_libreoffice as test
import uno

from libreharp.uno_app import Runtime, Settings


def main():
    ctx = test.start(visible=True)
    app = Runtime(ctx)
    doc = test.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    window = Settings(app)
    try:
        window.show()
        window.status("Accessible bridge test completed.")
        window.dialog.getControl("status").setFocus()
        client_env = {
            k: v for k, v in os.environ.items() if k not in {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"}
        }
        output = subprocess.check_output(
            [
                "uv",
                "run",
                "--no-project",
                "--offline",
                "/usr/bin/python3",
                str(test.ROOT / "scripts/atspi_probe.py"),
                window.model.Title,
            ],
            text=True,
            timeout=25,
            env=client_env,
        )
        nodes = json.loads(output)
        test.REPORT["tree"] = nodes
        for name in (
            "Profile name",
            "English dialect",
            "Personal words",
            "Preferences import or export file",
            "Status",
        ):
            test.record("AT-SPI exposes " + name, any(n["name"] == name for n in nodes))
        test.record(
            "AT-SPI reads the status message",
            any(n.get("text") == "Accessible bridge test completed." for n in nodes),
        )
        test.record("AT-SPI exposes status focus", any(n["name"] == "Status" and n["focused"] for n in nodes))
        window.close()
        doc.Text.String = "This is a example."
        doc.CharLocale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
        doc.storeAsURL(
            (test.ZONE / "LibreHarp-AT-SPI.odt").as_uri(),
            (test.prop("FilterName", "writer8"), test.prop("Overwrite", True)),
        )
        xid = (
            subprocess.check_output(
                ["xdotool", "search", "--onlyvisible", "--name", "LibreHarp-AT-SPI.odt"], text=True
            )
            .strip()
            .splitlines()[-1]
        )
        subprocess.run(["xdotool", "windowactivate", "--sync", xid], check=True)
        time.sleep(0.3)
        frame = doc.CurrentController.Frame
        url = uno.createUnoStruct("com.sun.star.util.URL")
        url.Complete, url.Protocol, url.Path = "org.libreharp:sidebar", "org.libreharp:", "sidebar"
        frame.queryDispatch(url, "_self", 0).dispatch(url, ())
        time.sleep(3)
        title = subprocess.check_output(["xdotool", "getwindowname", xid], text=True).strip()
        nodes = json.loads(
            subprocess.check_output(
                [
                    "uv",
                    "run",
                    "--no-project",
                    "--offline",
                    "/usr/bin/python3",
                    str(test.ROOT / "scripts/atspi_probe.py"),
                    title,
                ],
                text=True,
                timeout=30,
                env=client_env,
            )
        )
        names = (
            "Findings",
            "Finding explanation and context",
            "Suggested replacement",
            "More actions",
            "Status",
        )
        test.REPORT["sidebar_controls"] = [n for n in nodes if n["name"] in names]
        for name in names:
            test.record(
                "Installed sidebar exposes " + name + " through AT-SPI", any(n["name"] == name for n in nodes)
            )
        test.record(
            "Installed Open sidebar focuses Findings",
            any(n["name"] == "Findings" and n["focus_within"] for n in nodes),
        )
    finally:
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
        (test.ZONE / "atspi-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
