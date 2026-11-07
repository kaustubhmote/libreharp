"""Locate a selected source engine or the single engine in an installed OXT."""

import hashlib
import json
import re
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "vendor/harper"
WEIR_BINARY = "libreharp-weir"
WEIR_NOTICES = "weir-notices.txt"
PAYLOAD = {
    "harper-ls": "binary_sha256",
    "default_config.json": "catalog_sha256",
    "LICENSE": "license_sha256",
}


def engine_directory(version=None, vendor=None):
    vendor = Path(vendor) if vendor is not None else VENDOR
    selection = vendor / "selected.json"
    if version is None and not selection.exists():
        return vendor  # Installed packages contain exactly one flattened release.
    if version is None:
        version = json.loads(selection.read_text())["version"]
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Harper version must have the form X.Y.Z")
    directory = vendor / "releases" / version
    metadata = json.loads((directory / "provenance.json").read_text())
    if metadata["version"] != version:
        raise ValueError("Harper directory and provenance versions do not match")
    return directory


def verify_engine(directory):
    directory = Path(directory)
    metadata = json.loads((directory / "provenance.json").read_text())
    for name, key in PAYLOAD.items():
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != metadata[key]:
            raise ValueError(f"Harper {name} checksum mismatch in {directory}")
    return metadata


def engine_metadata(directory):
    return json.loads((directory / "provenance.json").read_text())


def select_engine(version, vendor=None):
    vendor = Path(vendor) if vendor is not None else VENDOR
    directory = engine_directory(version, vendor)
    verify_engine(directory)
    temporary = vendor / "selected.json.tmp"
    temporary.write_text(json.dumps({"version": version}) + "\n")
    temporary.replace(vendor / "selected.json")
