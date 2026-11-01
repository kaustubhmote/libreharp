# Update the bundled engine

LibreHarp has no automatic updater. An engine update is a reviewed source change and a new versioned OXT.

1. Select an official Automattic/harper release and inspect its release notes and license. Record the exact platform asset and publisher-provided archive digest.
2. Download the asset into a temporary directory. Verify its archive digest before extracting the single `harper-ls` executable. Record the executable digest in `vendor/harper/provenance.json`.
3. Update the bundled license and `default_config.json` from the same tagged release. Check the catalog format, rule names, defaults and renamed/removed rules. The catalog parser rejects unknown setting variants.
4. Review the LSP adapter against that engine. The Unicode code-action workaround in `engine.py` applies only to Harper 3.0.0. Do not extend it to another version without reproducing its behavior.
5. Run core tests, real-engine tests, the three isolated LibreOffice suites, and the visible sidebar preview. Include long-sentence suppression, dictionary invalidation, document/project isolation, Unicode replacements, migration and Undo.
6. Bump the application version in `libreharp/__init__.py`, `pyproject.toml`, and `extension/description.xml`. Refresh `uv.lock` if project metadata changes.
7. Build and verify the OXT, rebuild it to confirm its digest is deterministic, and preserve its checksum, test reports and release notes.

Do not substitute a binary found on PATH or run Cargo during extension installation. `scripts/vendor_engine.py` restores only the release already pinned in provenance. It is not a mechanism for selecting an update.
