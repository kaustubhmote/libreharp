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

## 2026-11-01 — version 0.3.0 continuation

- Replaced the tall sidebar findings list with a dropdown. The explanation now receives extra panel height, while navigation, replacement, and secondary actions occupy compact rows. At the tested minimum height, the explanation is 182 pixels instead of 70. The visible 920-pixel Writer window gives it roughly 490 pixels.
- Added full flagged text, surrounding context, position within the finding list, and examples for eight common rules. Verified that each example triggers its named rule and its corrected version does not. Harper deliberately skips some short capitalization examples; adjusted the help and fixtures to match the pinned implementation.
- Kept the nearest finding selected after a refresh or ignore. Disabled unavailable navigation and Apply actions. Added keyboard mnemonics, explicit tab order, and control help text. These are usability improvements, not a completed accessibility audit.
- Enlarged the rule browser explanation area and included the same rule examples there.
- Field testing exposed that displayed field text can look like ordinary text. Review now excludes field contents. Replacements resolve actual text-portion ranges, which permits edits after a multi-character field without relying on paragraph-wide cursor counts. Direct field overwrites are rejected.
- Added real Writer tests for input fields, merged/nested tables, DOCX scope metadata, and edits alongside existing redlines. Undo can recreate field objects; tests reacquire the field and verify its retained content.
- Corrected a test-fixture assumption: assigning newline-separated text through UNO can create line breaks within a paragraph. The old 100-line test is now named accurately. The new 1,000-paragraph fixture inserts explicit paragraph breaks and asserts the paragraph count before measuring review.
- The 1,000-paragraph review completed in 15.310 seconds on this machine. This measurement includes the review snapshot and checking, but excludes document creation. It is not a cross-machine performance promise.
- The regular LibreOffice profile remains untouched. Versioned validation reports are retained under `docs/`; the generated OXT and isolated test files remain ignored by Git.

### Version 0.3.0 validation

- 32 unit/engine tests and 101 actual LibreOffice checks passed: 28 baseline, 26 sidebar/scope, 30 extended, and 17 complex-document checks.
- Native accessibility actions exercised the relocated scope action, navigation boundaries, selection after ignore, and Apply/Undo. Tests wait for asynchronous actions before reading the resulting UI state.
- Inspected the expanded sidebar and rule-browser explanation areas. Captured the sidebar at both standard and smaller Writer window sizes.
- Verified the 28-file OXT payload and a deterministic rebuild. The release checksum and suite counts are saved in `docs/v0.3.0-validation.json`.

## 2026-11-01, version 0.4.0 accessibility continuation

- Added explicit accessible names to the sidebar and all six dialogs. Native inspection caught incorrect automatic label associations for the dialect selector, personal words, and import/export path. The peer property is `AccessibleName`; setting help text alone does not supply these names.
- Added a native tab controller to the sidebar. A plain UNO control container does not establish traversal from `TabIndex` alone. Dialogs now exclude static labels from tab stops, and the vocabulary editor keeps each entry beside its actions. Buttons receive unique mnemonics within each dialog.
- Changed status labels to read-only text controls. Messages retain their full text and emit native text-change events. F8 focuses Status, and action validation failures move focus there automatically. Expected validation failures no longer appear as component exceptions in the diagnostic log.
- Scoped keyboard handlers to their own dialog or focused sidebar controls. Escape closes a dialog or returns to Writer while keeping the sidebar open. Child dialogs restore their launching control. Background review does not take focus. F8 in Writer retains Writer's normal behavior.
- Native keyboard testing exposed focus timing problems. Status and Escape actions now run through a UI callback after key release. The event source identifies the receiving window when the active-window query changes during dispatch. Native combo boxes can consume Escape presses, so the handler also handles their release path.
- The installed sidebar's `createAccessible` method now returns its accessible control container. Added a factory regression check. An initial inspection through Writer's generic UNO tree stopped at embedded GTK widgets. The independent AT-SPI probe reaches the actual installed sidebar and confirms its control names and initial Findings focus.
- Tested in the isolated LibreOffice profile and a private D-Bus session. No ordinary profile, user document, or desktop accessibility preference was changed. Orca speech and braille output were not evaluated.
- Updated the keyboard guide, test commands, and remaining plan. Theme/font/scaling coverage, spoken feedback, and platform compatibility remain open.

### Version 0.4.0 validation

- 32 unit/engine tests passed, plus 134 native LibreOffice checks: 28 baseline, 27 sidebar/scope, 30 extended, 17 complex-document, and 32 keyboard/accessibility checks.
- 13 additional checks passed through the external GTK3/AT-SPI bridge. They cover Settings names and status text/focus, installed sidebar controls, and Findings focus after the menu command.
- Inspected the installed sidebar at 1280 by 920 and 1000 by 720, plus Review, rule browser, personal settings, scoped settings, and vocabulary windows. The explanation retains the sidebar's available height; controls and status text fit at the tested scale.
- The 1,000-paragraph fixture completed review in 15.392 seconds. This is a local measurement, not a performance guarantee.
- The versioned reports and package checksum are retained under `docs/`. The final package contains 29 verified payload files and reproduces byte for byte. The generated package, screenshots, and test profile remain ignored by Git.

## Font and display scaling continuation

- Measured real LibreOffice controls with enlarged GTK fonts and forced DPI. The fixed sidebar rows did not follow the font metrics, and the Settings dialog extended below a 1080-pixel display.
- Sidebar row heights, minimum width, and minimum/preferred panel heights now follow native font and DPI measurements. Extra height still goes to the explanation. Button widths include measured label text.
- Dialogs retain native text size, fit the rendered viewport to the primary display, and expose native scrollbars. Wide multiline fields reflow to the visible width. Keyboard focus reveals a field through the same scrollbar used by the mouse.
- LibreOffice's `ScrollTop` and `ScrollLeft` setters apply relative movement. The implementation uses the native scrollbar's absolute accessible value instead. Compound selectors require accessibility focus events in addition to ordinary control focus events. Stale events cannot override a newer focused control.
- Created a nested Xephyr test display with its own Mutter window manager and private D-Bus session. This avoids false failures when another desktop window becomes active while the test sends keys. Test display settings and font scaling are process-local.
- Added real-display tests for all six dialogs, full Settings tab traversal, status reveal, button text fit, sidebar minimum-size bounds, overlap, and explanation growth. Release validation and installation follow after the full matrix and regressions.
- Visual inspection of the installed panel found clipping that the source-control tests had missed: Writer can assign less than the requested width, and a large minimum height can put the whole panel inside Writer's outer scrolling area. The panel now packs buttons into the assigned width and uses a native scrolling child dialog with a zero host minimum height. Its own content retains the measured minimum height.
- Native scrollbars are classified by their accessibility orientation, not their early pixel bounds. Initial zero-sized sidebar bounds had incorrectly classified a vertical scrollbar as horizontal. The tests now shrink the source panel to 300 by 400 and verify scrolling to Status and back to Findings.
- Extended the independent AT-SPI probe to record native screen bounds and verify F8 on the actual installed panel at large fonts. Passing source geometry checks alone is not sufficient release evidence.
- The installed GTK sidebar exposed a keyboard ownership bug that source panels attached directly to Writer did not reproduce. GTK's intermediary window differs from both the frame and the panel peer. Sidebar shortcuts now require focus within that panel's own controls; ordinary dialogs retain their top-window check. Writer's F8 remains outside the sidebar handler when its document has focus.
- Generic VCL honored the requested minimum sidebar width by adding its own horizontal viewport. The host minimum width is now zero, so the panel receives the real available width and wraps its controls. Added installed-panel checks against ancestor clipping boundaries.
- A full-desktop screenshot at GTK 200% revealed that UNO's fitted rectangle could differ from the actual outer window. Dialogs now map at a safe initial size with native resizing enabled, then fit from the mapped font metrics. X11 client dimensions are checked against each dialog's UNO viewport at every scale. This also removes stale painting outside the smaller viewport.
- Generic VCL can allocate a panel wider than the visible host viewport even when the extension requests no minimum width. The panel now intersects ancestor bounds and sizes its own viewport to the visible area. Its native scrollbar remains reachable. Size probes calculate preferred dimensions without rearranging controls or moving the current scroll position.
