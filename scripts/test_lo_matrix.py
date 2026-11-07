"""Run the same Writer integration suites against multiple Linux installations."""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from libreharp import __version__

SUITES = (
    ("baseline", "test_libreoffice.py", "report.json"),
    ("harper-features", "test_harper_features.py", "harper-features-report.json"),
    ("scopes", "test_scopes_libreoffice.py", "scopes-report.json"),
    ("context-menu", "test_context_menu.py", "context-menu-report.json"),
)
GUI_SUITE = ("popup", "test_popup_writer.py", "popup-writer-report.json")


def run(command, *, cwd, env, log, timeout=180):
    with log.open("w", encoding="utf-8") as output:
        with subprocess.Popen(
            [str(part) for part in command],
            cwd=cwd,
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        ) as process:
            try:
                return process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise


def find_program(directory):
    if (directory / "soffice").is_file():
        return directory
    programs = sorted(directory.glob("opt/*/program/soffice"))
    if len(programs) == 1:
        return programs[0].parent
    raise ValueError("Specify a LibreOffice program directory or an extracted AppImage root.")


@contextmanager
def installation(target, case, env):
    if target.suffix.lower() == ".appimage":
        with tempfile.TemporaryDirectory(prefix="extraction-", dir=case) as tmp:
            directory = Path(tmp)
            result = run([target, "--appimage-extract"], cwd=directory, env=env, log=case / "extraction.log")
            if result:
                raise RuntimeError(f"AppImage extraction failed with exit code {result}.")
            extracted = directory / "squashfs-root"
            yield find_program(extracted), extracted / "AppRun"
    elif target.is_dir():
        program = find_program(target)
        yield program, target / "AppRun" if (target / "AppRun").is_file() else program / "soffice"
    elif target.is_file():
        yield find_program(target.parent), target
    else:
        raise ValueError(f"Installation does not exist: {target}")


def test_target(target, case, args):
    profile = case / "profile"
    env = {**os.environ, "LIBREHARP_TEST_ZONE": str(case), "LIBREHARP_TEST_PACKAGE": str(args.package)}
    # Also keep startup settings and caches of the launcher inside this run.
    for variable, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
    ):
        path = case / name
        path.mkdir()
        env[variable] = str(path)
    report = {"target": str(target), "profile": str(profile), "suites": [], "passed": False}
    try:
        with installation(target, case, env) as (program, launcher):
            if not launcher.is_file() or not (program / "unopkg").is_file():
                raise ValueError("This installation needs a LibreOffice launcher and unopkg.")
            bundled = program / "python"
            python = bundled if bundled.is_file() else args.uno_python or Path("/usr/bin/python3")
            env.update(LIBREHARP_LO_PROGRAM=str(program), LIBREHARP_LO_LAUNCHER=str(launcher))
            profile_arg = "-env:UserInstallation=" + profile.as_uri()
            version_log = case / "version.log"
            if run([launcher, profile_arg, "--version"], cwd=case, env=env, log=version_log, timeout=30):
                raise RuntimeError("LibreOffice failed to report its version.")
            report["libreoffice"] = version_log.read_text().strip()
            python_log = case / "python.log"
            if run(
                [
                    python,
                    "-c",
                    "import sys, uno; print(sys.version.split()[0]); assert sys.version_info >= (3, 11)",
                ],
                cwd=case,
                env=env,
                log=python_log,
                timeout=30,
            ):
                raise RuntimeError("This target needs Python 3.11 or later with UNO. See python.log.")
            report["python"] = python_log.read_text().strip()
            print(f"{report['libreoffice']} · Python {report['python']}", flush=True)
            for suite, script, report_name in (*SUITES, *((GUI_SUITE,) if args.gui else ())):
                log = case / f"{suite}.log"
                command = [python, ROOT / "scripts" / script]
                suite_env = env
                if suite == "popup":
                    command = [
                        sys.executable,
                        ROOT / "scripts" / "isolated_display.py",
                        *command,
                        "--keyboard-only",
                    ]
                    suite_env = {**env, "SAL_USE_VCLPLUGIN": "gen", "SAL_ACCESSIBILITY_ENABLED": "1"}
                status = run(command, cwd=case, env=suite_env, log=log)
                result_path = case / report_name
                result = json.loads(result_path.read_text()) if result_path.exists() else {}
                passed = status == 0 and result.get("passed", False)
                report["suites"].append(
                    {
                        "name": suite,
                        "passed": passed,
                        "checks": len(result.get("checks", ())),
                        "exit_code": status,
                        "log": log.name,
                        "report": report_name,
                    }
                )
                if skipped := result.get("skipped"):
                    report["suites"][-1]["skipped"] = skipped
                    print(f"  SKIP part of {suite}: {skipped}", flush=True)
                print(
                    f"  {'PASS' if passed else 'FAIL'} {suite} ({len(result.get('checks', ()))} checks)",
                    flush=True,
                )
                if suite == "baseline" and not passed:
                    break
            report["passed"] = all(suite["passed"] for suite in report["suites"])
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        report["error"] = str(exc)
        print(f"  FAIL {target.name}: {exc}", flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets",
        nargs="*",
        type=Path,
        help="AppImages, extracted roots, program directories or soffice executables",
    )
    parser.add_argument(
        "--appimage-root", type=Path, action="append", default=[], help="Discover AppImages recursively"
    )
    parser.add_argument("--uno-python", type=Path, help="Python with UNO for installs without bundled Python")
    parser.add_argument("--package", type=Path, default=ROOT / "build" / f"LibreHarp_v{__version__}.oxt")
    parser.add_argument(
        "--gui", action="store_true", help="Also test the keyboard popup and About on an isolated X11 display"
    )
    args = parser.parse_args()
    args.package = args.package.resolve()
    if args.uno_python:
        args.uno_python = args.uno_python.absolute()
    if not args.package.is_file():
        parser.error(f"Build the extension first: {args.package}")
    targets = list(args.targets)
    for directory in args.appimage_root:
        if not directory.is_dir():
            parser.error(f"AppImage directory does not exist: {directory}")
        images = sorted(
            path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".appimage"
        )
        if not images:
            parser.error(f"No AppImages found in {directory}")
        targets.extend(images)
    if not targets and (soffice := shutil.which("soffice")):
        targets.append(Path(soffice))
    if not targets:
        parser.error("Pass an installation path or --appimage-root.")
    if args.gui:
        missing = [
            tool
            for tool in (
                "Xephyr",
                "mutter",
                "dbus-run-session",
                "xdpyinfo",
                "xprop",
                "xdotool",
                "import",
                "convert",
            )
            if not shutil.which(tool)
        ]
        if missing:
            parser.error("Missing GUI test tools: " + ", ".join(missing))
    output = ROOT / "test-zone" / "matrix"
    output.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=output))
    print(f"Reports: {run_dir}", flush=True)
    reports = []
    for index, target in enumerate(dict.fromkeys(path.resolve() for path in targets), 1):
        case = (
            run_dir
            / f"{index:02d}-{target.parent.name if target.suffix.lower() == '.appimage' else target.name}"
        )
        case.mkdir()
        report = test_target(target, case, args)
        reports.append(report)
        (case / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    (run_dir / "summary.json").write_text(
        json.dumps({"package": str(args.package), "targets": reports}, indent=2) + "\n"
    )
    return 0 if all(report["passed"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
