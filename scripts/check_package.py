"""Verify OXT payload hashes, registration resources and executable permissions."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from libreharp import __version__
from libreharp.bundled import PAYLOAD, WEIR_BINARY, WEIR_NOTICES

target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build" / f"LibreHarp_v{__version__}.oxt"
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    assert len(archive.namelist()) == len(set(archive.namelist())), "Duplicate archive entries"
    hashes = json.loads(archive.read("SHA256SUMS.json"))
    assert set(archive.namelist()) == set(hashes) | {"SHA256SUMS.json"}
    for name, expected in hashes.items():
        assert not name.startswith("/") and ".." not in Path(name).parts
        assert hashlib.sha256(archive.read(name)).hexdigest() == expected, name
    provenance = json.loads(archive.read("vendor/harper/provenance.json"))
    engine_files = {name for name in hashes if name.startswith("vendor/harper/")}
    expected_files = {*PAYLOAD, "provenance.json"}
    if "weir_core_commit" in provenance:
        expected_files.update((WEIR_BINARY, WEIR_NOTICES))
        assert archive.getinfo(f"vendor/harper/{WEIR_BINARY}").external_attr >> 16 & 0o111
    assert engine_files == {f"vendor/harper/{name}" for name in expected_files}
    for name, key in PAYLOAD.items():
        assert hashes[f"vendor/harper/{name}"] == provenance[key], name
    manifest = ET.fromstring(archive.read("META-INF/manifest.xml"))
    for entry in manifest:
        path = entry.attrib["{http://openoffice.org/2001/manifest}full-path"]
        assert path in hashes, path
    for name in ("description.xml", "Addons.xcu", "Linguistic.xcu", "ProtocolHandler.xcu"):
        ET.fromstring(archive.read(name))
    assert archive.getinfo("vendor/harper/harper-ls").external_attr >> 16 & 0o111
    for name in (
        "component.py",
        "libreharp/uno_app.py",
        "vendor/harper/LICENSE",
        "vendor/harper/default_config.json",
    ):
        assert name in hashes, name
print(f"Verified {len(hashes)} payload files: {target}")
