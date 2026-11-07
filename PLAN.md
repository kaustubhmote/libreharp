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
3. Complete an Orca listening pass, braille and other screen-reader testing, high-contrast checks, live changes between monitor scales, translations, and performance beyond 1,000 paragraphs. Native keyboard and accessibility-tree checks and a GTK3/AT-SPI bridge probe are covered. Version 0.5.0 adds fixed startup font and DPI cases.
4. Package and test Windows/macOS engines and older LibreOffice versions with their actual runtimes. The current filesystem locking uses Linux `fcntl`.
5. Add a release/update UI after defining a trusted distribution channel. Do not silently download or execute engine updates.

## Version 0.4.0 accessibility work

- [x] Explicit accessible names across the sidebar and all six dialogs, including compound selectors.
- [x] Native sidebar tab controller, dialog tab order, static-label exclusion, and button mnemonics.
- [x] Readable status fields, accessible text-change events, F8 status access, and validation-error focus.
- [x] Keyboard exit from dialogs/sidebar, child-dialog focus return, and no focus stealing during rechecks.
- [x] Native keyboard regressions and an independent GTK3/AT-SPI bridge probe.
- [ ] Spoken feedback and braille validation, high-contrast themes, and other operating systems. Fixed font/scaling cases are covered below.

LibreHarp remains a development release. Completed items have automated or recorded visual evidence; the remaining compatibility work is not implied by a passing Linux test suite.

## Version 0.5.0 font and display scaling work

- [x] Measure native controls at normal, enlarged-font, and high-DPI settings in isolated LibreOffice sessions.
- [x] Size sidebar rows and content dimensions from native font/control metrics, retaining room for explanations. Wrap actions to fit the actual panel width.
- [x] Keep large dialogs within the display and make overflow reachable by mouse and keyboard.
- [x] Add scaling regressions and inspect screenshots at the tested sizes.
- [x] Run regression suites, build a reproducible package, commit the release, and upgrade the usual LibreOffice installation.

Automated regression suites use an isolated profile. The authorized shared installation upgrade was verified with the regular profile; its grammar-service selection and preference-file state were preserved. Versioned validation reports are retained under `docs/`; the generated OXT and isolated test files remain ignored by Git.

## Version 0.5.1 dictionary shortcut

- [x] Populate More actions from the selected finding; omit dictionary actions for grammar findings and finding-specific actions when empty.
- [x] Preselect a global dictionary action for spelling findings and expose Add globally as a one-click button, independent of the scope selector.
- [x] Retain explicit document/project word actions and refuse stale spelling findings.
- [x] Verify native actions, persistence, keyboard navigation, and large-font layout; package, install, and commit the patch release.

## Version 0.6.0 context menus

- [x] Replace Writer spelling and grammar popup actions with LibreHarp actions for English findings.
- [x] Offer suggestions, temporary ignore, global words, document/project words, and scoped rule disabling.
- [x] Keep actions bound to their original document and reject stale paragraphs.
- [x] Mirror personal words to Writer without changing its configured checking services.
- [x] Verify installed popup actions, restart persistence, and existing sidebar/scope behavior in isolated profiles.

- [x] Add opt-in exclusive English checking with durable provider backup and restoration.
- [x] Verify that exclusive checking and restoration survive restart and preserve unrelated language providers.

## Version 0.6.1 technical vocabulary

- [x] Apply exact-word exceptions to spelling and word-splitting findings without disabling either rule.
- [x] Expose global and scoped word acceptance for split-word findings in the sidebar, review window, and context menu.
- [x] Add bulk vocabulary entry for personal, document, and project scopes with validated, atomic merging.
- [x] Verify compound acceptance, unrelated errors, stale actions, scope isolation, dialog lifecycle, and restart persistence.

## Version 0.6.2 grouped menu

- [x] Group context actions with Unicode tree branches and direct scope choices.
- [x] Use the existing sidebar for explanations and remove the separate suggestion card.
- [x] Use a common misspelling in the spelling-rule example and check it with Harper.

## Version 0.7.0 Harper update

- [x] Bundle Harper 3.1.0 with its matching rule catalog and verified upstream archive.
- [x] Retain versioned engines and metadata, with verified selection and separately named rollback builds.
- [x] Package exactly one engine per OXT.
- [x] Extend the Unicode-position workaround to the affected 3.1.0 server and test both retained engines.

## Version 0.8 Harper features

- [x] Combine rule search with category, effective state, override, and new-rule filters.
- [x] Add advanced checking controls for recheck delay, text size, exclusions, English isolation, and diagnostic severity.
- [x] Save document-local ignores and restore them individually. Exchange Harper dictionaries in the selected vocabulary scope.
- [x] Count explicit actions by rule when local statistics are enabled.
- [x] Edit, validate, and run personal Weir rules with the Harper 3.1.0 library.
- [x] Test the combined features as 0.8-dev before building 0.8.

## Version 0.8.1 About and compatibility tests

- [x] Show the LibreHarp and bundled Harper versions in the Writer About dialog.
- [x] Add a compatibility test runner for AppImages and conventional LibreOffice installations. Give each target a fresh profile.

## Version 0.8.2 sidebar preview

- [x] Underline flagged text in red and show the selected replacement in green and bold. Update the preview when the selection changes.
- [x] Use theme text colors in high-contrast mode. Inspect the installed sidebar in light and dark themes.
- [x] Pass 51 Python tests and 105 checks on each of the three LibreOffice AppImages in isolated profiles.
- [x] Verify the OXT, install it in regular LibreOffice, and confirm that preferences and English checker settings carry over. See [the release record](WORK_LOG.md#version-082-sidebar-preview-colors).
