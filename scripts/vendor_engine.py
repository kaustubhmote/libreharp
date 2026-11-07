"""Restore the pinned official engine with archive and executable verification."""

import argparse
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from libreharp.bundled import engine_directory, select_engine, verify_engine


def restore(version=None):
    directory = engine_directory(version)
    provenance = json.loads((directory / "provenance.json").read_text())
    binary = directory / "harper-ls"
    if binary.exists() and hashlib.sha256(binary.read_bytes()).hexdigest() == provenance["binary_sha256"]:
        verify_engine(directory)
        print(f"Harper {provenance['version']} already verified.")
        return
    url = f"https://github.com/Automattic/harper/releases/download/v{provenance['version']}/{provenance['asset']}"
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
    if hashlib.sha256(content).hexdigest() != provenance["archive_sha256"]:
        raise ValueError("Archive checksum mismatch. No files were replaced.")
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
        candidates = [m for m in archive.getmembers() if m.isfile() and Path(m.name).name == "harper-ls"]
        if len(candidates) != 1:
            raise ValueError("Archive must contain exactly one harper-ls executable.")
        executable = archive.extractfile(candidates[0]).read()
    if hashlib.sha256(executable).hexdigest() != provenance["binary_sha256"]:
        raise ValueError("Executable checksum mismatch. No files were replaced.")
    temporary = binary.with_suffix(".download")
    temporary.write_bytes(executable)
    temporary.chmod(0o755)
    temporary.replace(binary)
    verify_engine(directory)
    print(f"Verified Harper {provenance['version']}: {binary}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Restore a retained version without selecting it")
    parser.add_argument("--select", metavar="VERSION", help="Restore, verify, and select a retained version")
    args = parser.parse_args()
    if args.version and args.select:
        parser.error("Use either --version or --select")
    restore(args.select or args.version)
    if args.select:
        select_engine(args.select)
        print(f"Selected Harper {args.select}")
