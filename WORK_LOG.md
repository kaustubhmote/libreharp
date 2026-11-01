# LibreHarp work log

This log records decisions, changes, evidence, and open issues. It is not a transcript of private reasoning.

## 2026-11-01 — independent implementation

- Created `/opt/software/libreharp` as requested. The previous LibreHarper snapshot remains a reference.
- Chose a small standard-library Python UNO extension and a bundled, pinned Harper 3.0.0 executable. No server installation, Cargo toolchain, Python package installation, or network access is required at runtime.
- Implemented atomic, locked JSON preferences with named profiles, global overrides, personal words, literal terminology rules, import/export, and validation. Corrupt files are preserved instead of silently resetting user choices.
- Added a serialized LSP client, versioned document notifications, timeouts, and a preference-sensitive bounded cache. Engine failures have a separate status from clean checks.
- Implemented an independent UNO proofreader and a modeless review/settings interface. Checks run on a background worker; document access and replacements run on LibreOffice's UI callback thread. Replacement checks compare the full original paragraph and the selected text, and use Writer's undo manager.
- Chose explicit permanent controls instead of inferring document identity from Writer's current window. The native Ignore callback has no document ID, so it remains session-only; permanent suppression is exposed in LibreHarp.
- First testable release uses a review window. A dockable sidebar, rich rule browser, and project/document preference UI remain subsequent milestones. The core accepts explicit document overrides, but the UNO adapter does not guess document ownership.
- Installation tests will use a separate `test-zone/profile`, never the normal LibreOffice profile.

## Integration findings and fixes

- Real-engine tests exposed stale diagnostics after configuration changes: Harper can omit diagnostic versions. Every check now opens a unique URI and closes its predecessor; results from prior requests cannot be accepted for the current paragraph.
- Unicode tests exposed a Harper 3.0.0 mismatch: diagnostics use UTF-16 positions, but code-action input positions are interpreted as Unicode scalar indices. Confirmed against the pinned `harper-ls/src/pos_conv.rs`. Requests adapt only for version 3.0.0, and returned edit ranges must still match the diagnostic exactly. This restores suggestions after emoji without relaxing replacement safety.
- Real Writer tests showed that cursor movement counts characters while proofreading offsets count UTF-16 units. These conversions are now separate, with a final selected-text comparison before replacement.
- A rule-browser test caught list selection before native peer creation. Initial selections now live in the control model and survive window creation.
- Isolated Harper's configuration/data directories and working directory from the user's other Harper installations. Oversize paragraphs fail visibly instead of inheriting Harper's silent skip behavior.
- Added the official Harper 3.0.0 catalog: 936 rules, categories, defaults, and mutually exclusive alternatives. The browser searches rules and saves profile/global overrides immediately.
- Added selection-driven explanations, previous/next navigation, document location, native close handling, stale-settings conflict detection, and cancellation of superseded review work.
- Created a dependency lockfile and formatter/linter configuration. Runtime remains standard-library-only apart from LibreOffice's own UNO bridge.

## Validation — 2026-11-01

- 21 unit and real-engine tests passed. Coverage includes durable LongSentences suppression, dictionary cache invalidation, concurrent atomic updates, corrupt-file preservation, import backups, document-override isolation, custom terminology, Unicode actions, engine restart, stalled-engine termination, and oversized/missing-engine errors.
- 28 checks passed in actual LibreOffice 26.8 with bundled Python 3.13. The OXT was installed, replaced, and loaded in `test-zone/profile`. Tests covered the Writing Aids registration, Writer's proofreading pipeline, process-restart persistence, native settings and rule-browser controls, asynchronous review, automatic refresh after edits, exact replacements, undo, formatting preservation, stale-text rejection, Unicode offsets, table traversal and cell edits, and menu protocol dispatch.
- Captured and visually inspected `test-zone/review-window.png`, `rule-browser.png`, and `settings-window.png`. Labels and controls fit without clipping at the tested display scale.
- The regular LibreOffice profile was not used for installation tests. Test processes and windows were shut down after testing.
- Detailed machine-readable results: `test-zone/report.json`. Reproduction commands are in README.md.
- The package verifier checks all 19 payload hashes, XML registrations, duplicate/path safety, and executable permissions. Builds use fixed ZIP metadata. The engine restoration script verifies both the official archive digest and the executable digest before replacing a missing binary.
- Rebuilt the final package twice and confirmed identical SHA-256 digests. The checksum is beside the OXT. Preserved the passing reports as `docs/integration-results.json` and `docs/unit-tests.xml`; initialized an independent local Git repository for subsequent development.

## Open product work

The shipped UI is a modeless review window, not a dockable sidebar. Document/project scope controls are not exposed until inline proofreading can bind them reliably to document identity. The current native settings fields are functional but need dedicated dictionary/terminology editors. Headers, footnotes, text frames, tracked changes, mixed-language review, wider platform support, and old-profile migration remain unverified or unimplemented. See PLAN.md for the ordered backlog.

## 2026-11-01 — version 0.2.0 continuation

The earlier open-work paragraph records the 0.1.0 state. This continuation implements the sidebar, scoped settings and much of that backlog.

- Added a native Writer sidebar deck and Python UI-element factory. Controls resize with the panel and reuse the tested review/replacement code. Captured the installed deck in a real Writer window and tested its Apply button through native accessibility actions.
- Established exact ID binding through Writer's `checkSentenceAtPosition(document, flatParagraph, ...)` API. Confirmed the opaque ID behavior against LibreOffice's `linguistic/source/gciterator.cxx`. Workers use snapshots; metadata reads and handshakes run through UI callbacks. No active-window fallback exists. First checks defer findings until their document identity is bound.
- Added embedded `LibreHarp.Settings` document metadata and nearest-directory `.libreharp.json` project files. Rules use document > project > personal global > selected profile precedence. Words combine; terminology with the same find text is overridden. Project writes are locked and atomic. Save As changes the project association; closed document identities are discarded.
- Added scope controls, precedence explanations, profile/dialect overrides, dedicated word/terminology editors, stale-editor detection, and guards against writing to a scope or project folder that has not been loaded or no longer contains the document.
- Added traversal for frames, footnotes, endnotes, and headers/footers of used page styles. Review checks contiguous English portions, preserving original offsets; unsupported representations are skipped explicitly. Tested a basic tracked replacement and Undo, plus 100 paragraphs and subsequent refresh.
- Added preview-first legacy migration for recognized Harper ignores and plain UTF-8 word lists. Imports retain old metadata, preserve newer LibreHarp rules, validate sources again before applying, and back up personal preferences.
- Native tests caught a UNO integration detail: Python implementations must expose IDL attributes (`Window`, `Frame`, `ResourceURL`, `Type`) as attributes, not only getter methods. Fixed before declaring the sidebar functional.
- Permission review occasionally timed out on large updates. Retried the timed-out actions once or split the file updates; completed the work without asking the user to approve unfinished results.
- The normal LibreOffice profile and user documents remain outside the test installation. All test documents, settings, and migration fixtures are in `test-zone/`.

Validation reports and final counts are retained in the versioned report files under `docs/`. The earlier 0.1.0 reports remain available. Current remaining work is listed in PLAN.md; platform and complex-document coverage are still limited.

### Final 0.2.0 validation

- 29 unit/real-engine tests passed.
- 77 actual LibreOffice checks passed: 28 baseline installation/review checks, 19 sidebar/scope checks, and 30 extended document/editor/migration checks.
- Document and project scopes survived a full LibreOffice restart. The installed sidebar Apply button changed only its bound document and supported Undo.
- The visible sidebar, scoped settings, and vocabulary editor were captured and inspected in the isolated test profile.
- Verified all 27 OXT payload files and deterministic rebuilds. The final digest is recorded beside the package and in `docs/v0.2.0-validation.json`.
- Final visible testing caught two sidebar startup details: the deck list can arrive after menu dispatch, and activating a deck does not expand a collapsed sidebar. Opening now waits through UI callbacks and explicitly expands the deck. The installed menu action passed its activation assertion, and the final screenshot shows populated review controls.
- Test runs compare component errors against their starting log, so retained historical diagnostics remain available while newly logged exceptions fail the run. Re-ran all 28 baseline checks and the visible sidebar/editor checks after the startup fix.
