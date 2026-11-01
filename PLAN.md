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

## Remaining work, in order

1. Add rule-specific explanations and examples beyond the upstream category descriptions.
2. Test complex existing tracked changes, merged/nested tables, fields, and DOCX metadata round trips. Improve unsupported field handling.
3. Audit screen-reader/keyboard use, translations, high-DPI layouts, and performance on much larger documents.
4. Package and test Windows/macOS engines and older LibreOffice versions with their actual runtimes. The current filesystem locking uses Linux `fcntl`.
5. Add a release/update UI after defining a trusted distribution channel. Do not silently download or execute engine updates.

Version 0.2.0 remains a development release. Completed items have automated or recorded visual evidence; the remaining compatibility work is not implied by a passing Linux test suite.
