# LibreHarp delivery plan

Build a native LibreOffice Writer extension with a bundled Harper engine, a review interface, durable preferences, editable dictionaries, and isolated installation tests.

## Work sequence

- [x] Establish an independent package, build scripts, provenance, and work log.
- [x] Implement atomic preference storage, profiles, dictionaries, and custom terminology rules.
- [x] Implement and unit-test explicit document overrides in the core.
- [x] Connect document overrides to a reliable Writer document identity and expose scope controls. No active-window guessing.
- [x] Implement a managed Harper process and preference-sensitive checking cache.
- [x] Implement the UNO proofreader and native review/settings windows.
- [x] Add a searchable, offline browser for all 936 rules in Harper 3.0.0's catalog.
- [x] Build a versioned OXT with the pinned Linux Harper binary.
- [x] Run unit and real-engine tests.
- [x] Install into an isolated LibreOffice profile and test registration, checks, persistent settings, and document edits.
- [x] Inspect screenshots of the visible review, rule and settings windows.
- [x] Document verified behavior, known limitations, and subsequent milestones.

## Release gates

Permanent rule suppression must survive a new process. Dictionary changes must invalidate cached results. Document overrides must not leak between documents. Suggestions must not replace changed text and must be undoable. An engine failure must be visible. Tests must not modify the user's regular LibreOffice profile or documents.

## Version 0.2.0 milestones

- [x] Dockable native Writer sidebar, resizing, document-bound controls, and actual Apply-button testing.
- [x] Embedded document settings and directory project settings, explicit identity binding, precedence indicators, Save As and restart tests.
- [x] Dedicated word and terminology editors. Retain advanced personal fields for existing workflows.
- [x] Review headers, footers, notes, frames and English portions of mixed-language paragraphs.
- [x] Test basic tracked replacements, Undo, and a 100-paragraph document.
- [x] Preview and migrate recognized legacy Harper document ignores and plain word lists, preserving old data and newer preferences.
- [x] Document a pinned, manually reviewed engine-update procedure.

## Version 0.3.0 milestones

- [x] Compact the sidebar and give its explanation the available height. Keep primary navigation and Apply visible; group secondary actions.
- [x] Show surrounding text and preserve the nearest selection after applying or ignoring a finding.
- [x] Add explanations and engine-verified examples for eight common rules, with fallback to Harper's message for other rules.
- [x] Exclude field contents and anchor replacements to native text portions. Test edits and Undo around input fields.
- [x] Test merged/nested tables, DOCX settings round trips, and edits alongside existing tracked changes.
- [x] Measure review of 1,000 actual Writer paragraphs and validate compact/native sidebar interactions.

## Remaining work, in order

1. Expand the eight rule-specific explanations to more of Harper's 936 rules. Keep examples tested against the pinned engine.
2. Test overlapping tracked changes, more field types, protected sections, and documents produced by other Word processors. The current DOCX evidence is a LibreOffice export/reopen round trip.
3. Complete an Orca listening pass, braille and other screen-reader testing, high-contrast/enlarged-font/high-DPI checks, translations, and performance beyond 1,000 paragraphs. Native keyboard and accessibility-tree checks and a GTK3/AT-SPI bridge probe are covered in 0.4.0.
4. Package and test Windows/macOS engines and older LibreOffice versions with their actual runtimes. The current filesystem locking uses Linux `fcntl`.
5. Add a release/update UI after defining a trusted distribution channel. Do not silently download or execute engine updates.

## Version 0.4.0 accessibility work

- [x] Explicit accessible names across the sidebar and all six dialogs, including compound selectors.
- [x] Native sidebar tab controller, dialog tab order, static-label exclusion, and button mnemonics.
- [x] Readable status fields, accessible text-change events, F8 status access, and validation-error focus.
- [x] Keyboard exit from dialogs/sidebar, child-dialog focus return, and no focus stealing during rechecks.
- [x] Native keyboard regressions and an independent GTK3/AT-SPI bridge probe.
- [ ] Spoken feedback and braille validation, theme/font/scaling matrix, and other operating systems.

Version 0.4.0 remains a development release. Completed items have automated or recorded visual evidence; the remaining compatibility work is not implied by a passing Linux test suite.

## Version 0.5.0 font and display scaling work

- [ ] Measure native controls at normal, enlarged-font, and high-DPI settings in isolated LibreOffice sessions.
- [ ] Size sidebar rows and minimum dimensions from native font/control metrics, retaining room for explanations.
- [ ] Keep large dialogs within the display and make overflow reachable by mouse and keyboard.
- [ ] Add scaling regressions and inspect screenshots at the tested sizes.
- [ ] Run regression suites, build a reproducible package, commit the release, and upgrade the usual LibreOffice installation.
