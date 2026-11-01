"""Run process-local font and DPI cases inside scripts/isolated_display.py."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = os.environ.get(
    "LIBREHARP_LO_PROGRAM", "/opt/software/libreoffice/lib/v26.8/extracted/opt/libreoffice26.8/program"
)
CASES = {
    "default": {},
    "font150": {"SAL_USE_VCLPLUGIN": "gtk3", "GDK_DPI_SCALE": "1.5"},
    "font200": {"SAL_USE_VCLPLUGIN": "gtk3", "GDK_DPI_SCALE": "2"},
    "dpi150": {"SAL_USE_VCLPLUGIN": "gen", "SAL_FORCEDPI": "144"},
    "dpi200": {"SAL_USE_VCLPLUGIN": "gen", "SAL_FORCEDPI": "192"},
    "gtk200": {"SAL_USE_VCLPLUGIN": "gtk3", "GDK_SCALE": "2"},
}

for name, settings in CASES.items():
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"SAL_USE_VCLPLUGIN", "SAL_FORCEDPI", "GDK_SCALE", "GDK_DPI_SCALE"}
    }
    env.update(settings, LIBREHARP_SCALE_CASE=name)
    print("Scaling case:", name, flush=True)
    subprocess.run(
        [
            "uv",
            "run",
            "--no-project",
            "--offline",
            str(Path(PROGRAM) / "python"),
            str(ROOT / "scripts/test_scaling.py"),
        ],
        env=env,
        check=True,
    )
