"""Restore the pinned official engine with archive and executable verification."""

import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "vendor/harper"


def main():
    provenance = json.loads((DEST / "provenance.json").read_text())
    binary = DEST / "harper-ls"
    if binary.exists() and hashlib.sha256(binary.read_bytes()).hexdigest() == provenance["binary_sha256"]:
        print("Pinned Harper engine already verified.")
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
    print(f"Verified Harper {provenance['version']}: {binary}")


if __name__ == "__main__":
    main()
