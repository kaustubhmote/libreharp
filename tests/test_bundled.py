"""Check release selection, rollback, and Unicode fixes against both engines."""

import json
import shutil

import pytest

from libreharp.bundled import VENDOR, engine_directory, select_engine, verify_engine
from libreharp.engine import Engine


@pytest.mark.parametrize("version", ["3.0.0", "3.1.0"])
def test_retained_engine_replacements(version):
    directory = engine_directory(version)
    assert verify_engine(directory)["version"] == version
    engine = Engine(directory / "harper-ls")
    try:
        for text in ("😀 This is a example.", "First line.\n😀 This is a example."):
            issue = next(i for i in engine.check(text, {}) if i["rule"] == "AnA")
            assert text[issue["start"] : issue["end"]] == "a"
            assert "an" in issue["suggestions"]
        assert engine.version.split()[-1] == version
    finally:
        engine.close()


def test_selection_and_rollback_keep_matching_catalog(tmp_path):
    for version in ("3.0.0", "3.1.0"):
        shutil.copytree(VENDOR / "releases" / version, tmp_path / "releases" / version)
    for version in ("3.1.0", "3.0.0", "3.1.0"):
        select_engine(version, tmp_path)
        directory = engine_directory(vendor=tmp_path)
        assert directory.name == version
        assert verify_engine(directory)["version"] == version


@pytest.mark.parametrize("corrupt", ["harper-ls", "default_config.json", "LICENSE"])
def test_failed_verification_does_not_change_selection(tmp_path, corrupt):
    shutil.copytree(VENDOR / "releases/3.0.0", tmp_path / "releases/3.0.0")
    selected = tmp_path / "selected.json"
    selected.write_text(json.dumps({"version": "3.1.0"}))
    before = selected.read_bytes()
    (tmp_path / "releases/3.0.0" / corrupt).write_bytes(b"damaged")
    with pytest.raises(ValueError, match="checksum mismatch"):
        select_engine("3.0.0", tmp_path)
    assert selected.read_bytes() == before


def test_invalid_version_and_mismatched_provenance_rejected(tmp_path):
    with pytest.raises(ValueError, match="X.Y.Z"):
        engine_directory("../3.0.0", tmp_path)
    directory = tmp_path / "releases/3.1.0"
    directory.mkdir(parents=True)
    (directory / "provenance.json").write_text('{"version":"3.0.0"}')
    with pytest.raises(ValueError, match="versions do not match"):
        engine_directory("3.1.0", tmp_path)


def test_installed_layout_uses_flat_bundle(tmp_path):
    assert engine_directory(vendor=tmp_path) == tmp_path
