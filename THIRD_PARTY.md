# Third-party components

LibreHarp's original code and artwork use the [Zero-Clause BSD license (0BSD)](LICENSE).

The Harper language server is from Automattic/harper, distributed under Apache-2.0. The default build uses Harper 3.1.0. A build can select the retained 3.0.0 release instead. Each package includes one Harper release, its license, its provenance, and the unmodified `default_config.json` catalog in `vendor/harper/`. The package's `provenance.json` identifies the release and checksums.

LibreHarp's Weir helper is built from the code in `weir-bridge/` and the Apache-2.0 Harper library from the 3.1.0 release commit. `weir-bridge/Cargo.lock` records its Rust dependencies. Builds with the helper include the dependencies' notices and available license texts in `vendor/harper/weir-notices.txt`.

Retained sources: https://github.com/Automattic/harper/tree/v3.1.0 and https://github.com/Automattic/harper/tree/v3.0.0.

The previous LibreHarper/WriterAgent project informed the requirements and integration review. Its Python source is not included in this independent implementation.
