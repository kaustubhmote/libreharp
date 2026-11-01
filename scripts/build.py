"""Build a versioned, deterministic Linux OXT; no downloads during packaging."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from libreharp import __version__


def build():
    binary = ROOT / "vendor/harper/harper-ls"
    provenance = json.loads((binary.parent / "provenance.json").read_text())
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if digest != provenance["binary_sha256"]:
        raise ValueError("Harper digest mismatch; refusing to bundle an unverified binary.")
    version = (
        ET.parse(ROOT / "extension/description.xml")
        .getroot()
        .find("{http://openoffice.org/extensions/description/2006}version")
    )
    if version.get("value") != __version__:
        raise ValueError("Package and extension versions must match.")
    target = ROOT / "build" / f"LibreHarp_v{__version__}.oxt"
    target.parent.mkdir(exist_ok=True)
    files = {
        p.relative_to(ROOT / "extension").as_posix(): p
        for p in (ROOT / "extension").rglob("*")
        if p.is_file()
    }
    for pattern in (
        "component.py",
        "libreharp/*.py",
        "vendor/harper/*",
        "LICENSE",
        "README.md",
        "THIRD_PARTY.md",
    ):
        for path in ROOT.glob(pattern):
            if path.is_file():
                files[path.relative_to(ROOT).as_posix()] = path
    hashes = {}
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in sorted(files.items()):
            content = path.read_bytes()
            info = zipfile.ZipInfo(name, (2026, 11, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if name.endswith("/harper-ls") else 0o100644) << 16
            archive.writestr(info, content)
            hashes[name] = hashlib.sha256(content).hexdigest()
        info = zipfile.ZipInfo("SHA256SUMS.json", (2026, 11, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, json.dumps(hashes, sort_keys=True, indent=2))
    print(target)
    return target


if __name__ == "__main__":
    build()
