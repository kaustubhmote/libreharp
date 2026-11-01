"""Run a GUI-test command inside Xephyr and a private Mutter/D-Bus session.

Usage: uv run python scripts/isolated_display.py COMMAND [ARGUMENT ...]
The host display and desktop preferences are never reconfigured.
"""

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def ready(command, marker=None):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3)
        if result.returncode == 0 and (marker is None or marker in result.stdout):
            return
        time.sleep(0.1)
    raise RuntimeError("Isolated test display did not become ready: " + str(command))


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Pass a test command and its arguments.")
    number = next(
        n
        for n in range(97, 120)
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(f"/tmp/.X{n}-lock").exists()
    )
    display = f":{number}"
    env = dict(os.environ, DISPLAY=display, GSETTINGS_BACKEND="memory", SESSION_MANAGER="")
    with tempfile.TemporaryDirectory(prefix="libreharp-display-") as directory:
        with open(Path(directory) / "display.log", "w+") as log:
            server = subprocess.Popen(
                [
                    "Xephyr",
                    display,
                    "-screen",
                    "1920x1080",
                    "-ac",
                    "-nolisten",
                    "tcp",
                    "-noreset",
                    "-no-host-grab",
                    "-title",
                    "LibreHarp isolated tests",
                ],
                stdout=log,
                stderr=log,
            )
            manager = None
            try:
                ready(["xdpyinfo", "-display", display])
                manager = subprocess.Popen(
                    ["dbus-run-session", "--", "mutter", "--x11", "--display=" + display, "--sm-disable"],
                    env=env,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                ready(["xprop", "-display", display, "-root", "_NET_SUPPORTING_WM_CHECK"], "window id")
                return subprocess.run(sys.argv[1:], env=env).returncode
            finally:
                if manager:
                    os.killpg(manager.pid, 15)
                    manager.wait(timeout=10)
                server.terminate()
                server.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
