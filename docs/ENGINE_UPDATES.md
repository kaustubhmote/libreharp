# Manage the bundled Harper engine

Each OXT includes one Harper release. The directories under `vendor/harper/releases/` retain its catalog, license, and provenance. The executable is restored from the pinned upstream release and checked against the recorded digest.

## Build with a retained engine

Use `--harper-version` to build an alternate OXT while keeping the default selection.

```sh
uv run python scripts/vendor_engine.py --version 3.0.0
uv run python scripts/build.py --harper-version 3.0.0
uv run python scripts/check_package.py build/LibreHarp_v0.9_harper-3.0.0.oxt
```

Use `uv run python scripts/vendor_engine.py --select VERSION` to verify and change the default in `vendor/harper/selected.json`. Rebuild the OXT and install it to use the new selection in Writer. The Harper 3.1.0 build includes a Weir helper compiled against the matching pinned Harper commit and ships its dependency notices.

## Add a Harper release

1. Choose an official Automattic/harper release. Record its Linux x86-64 asset, release URL, and published archive checksum.
2. Verify the archive before extracting `harper-ls`. Record the executable checksum in the new release directory's `provenance.json`.
3. Copy the tagged release's license and `default_config.json` into the new directory. Record their checksums and compare rule identifiers and defaults with the previous release.
4. Review Unicode code actions and check that replacements after emoji target the correct range. If the build supports Weir, pin the helper to the matching source commit.
5. Select the release, run the [build and test checks](TESTING.md), and verify the OXT and checksum before distribution.
