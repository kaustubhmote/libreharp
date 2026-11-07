"""Build a versioned, deterministic Linux OXT; no downloads during packaging."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from libreharp import __version__
from libreharp.bundled import PAYLOAD, WEIR_BINARY, WEIR_NOTICES, engine_directory, verify_engine


def weir_notices(source):
    metadata = json.loads(
        subprocess.check_output(
            [
                "cargo",
                "metadata",
                "--offline",
                "--locked",
                "--manifest-path",
                str(source / "Cargo.toml"),
                "--format-version",
                "1",
                "--filter-platform",
                "x86_64-unknown-linux-gnu",
            ]
        )
    )
    packages = {pkg["id"]: pkg for pkg in metadata["packages"]}
    dependencies = {node["id"]: node["dependencies"] for node in metadata["resolve"]["nodes"]}
    root = metadata["resolve"]["root"]
    pending, seen = [root], {root}
    while pending:
        for dependency in dependencies[pending.pop()]:
            if dependency not in seen:
                pending.append(dependency)
                seen.add(dependency)
    lines = ["LibreHarp Weir bridge dependency notices\n"]
    for package in sorted((packages[key] for key in seen - {root}), key=lambda p: (p["name"], p["version"])):
        directory = Path(package["manifest_path"]).parent
        files = {
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE", "UNLICENSE"))
        }
        if package.get("license_file"):
            files.add(directory / package["license_file"])
        lines.append(
            f"\n{package['name']} {package['version']}\n{package['license'] or 'See included license'}\n"
            f"{package.get('repository') or package.get('homepage') or ''}\n"
        )
        for path in sorted(files, key=lambda path: path.name):
            lines.append(f"\n{path.name}\n{path.read_text(encoding='utf-8', errors='replace')}\n")
    result = ROOT / "build" / WEIR_NOTICES
    result.write_text("".join(lines), encoding="utf-8")
    return result


def build_weir(metadata):
    source = ROOT / "weir-bridge"
    commit = metadata["weir_core_commit"]
    if commit not in (source / "Cargo.lock").read_text():
        raise ValueError("Weir bridge and bundled Harper source versions do not match.")
    target = Path(os.environ.get("LIBREHARP_WEIR_TARGET_DIR", ROOT / "build" / "weir-target")).resolve()
    subprocess.run(
        [
            "cargo",
            "build",
            "--offline",
            "--locked",
            "--release",
            "--manifest-path",
            str(source / "Cargo.toml"),
            "--target-dir",
            str(target),
        ],
        check=True,
    )
    binary = target / "release" / WEIR_BINARY
    version = subprocess.check_output([binary, "--version"], text=True).strip()
    if version != f"{WEIR_BINARY} {metadata['version']}":
        raise ValueError("Weir bridge was built with a different Harper release.")
    result = ROOT / "build" / WEIR_BINARY
    shutil.copy2(binary, result)
    return result, weir_notices(source)


def build(harper_version=None):
    directory = engine_directory(harper_version, ROOT / "vendor/harper")
    metadata = verify_engine(directory)
    version = (
        ET.parse(ROOT / "extension/description.xml")
        .getroot()
        .find("{http://openoffice.org/extensions/description/2006}version")
    )
    if version.get("value") != __version__:
        raise ValueError("Package and extension versions must match.")
    suffix = f"_harper-{harper_version}" if harper_version else ""
    target = ROOT / "build" / f"LibreHarp_v{__version__}{suffix}.oxt"
    target.parent.mkdir(exist_ok=True)
    files = {
        p.relative_to(ROOT / "extension").as_posix(): p
        for p in (ROOT / "extension").rglob("*")
        if p.is_file()
    }
    for pattern in (
        "component.py",
        "libreharp/*.py",
        "LICENSE",
        "README.md",
        "THIRD_PARTY.md",
    ):
        for path in ROOT.glob(pattern):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = path
    for name in (*PAYLOAD, "provenance.json"):
        files[f"vendor/harper/{name}"] = directory / name
    if "weir_core_commit" in metadata:
        binary, notices = build_weir(metadata)
        files[f"vendor/harper/{WEIR_BINARY}"] = binary
        files[f"vendor/harper/{WEIR_NOTICES}"] = notices
    hashes = {}
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in sorted(files.items()):
            content = path.read_bytes()
            info = zipfile.ZipInfo(name, (2026, 11, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            executable = Path(name).name in ("harper-ls", WEIR_BINARY)
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            archive.writestr(info, content)
            hashes[name] = hashlib.sha256(content).hexdigest()
        info = zipfile.ZipInfo("SHA256SUMS.json", (2026, 11, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, json.dumps(hashes, sort_keys=True, indent=2))
    print(target)
    target.with_suffix(".oxt.sha256").write_text(
        f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {target.name}\n"
    )
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--harper-version", help="Build a separately named OXT with a retained Harper release"
    )
    build(parser.parse_args().harper_version)
