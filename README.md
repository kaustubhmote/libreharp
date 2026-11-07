# LibreHarp

An independent LibreOffice Writer extension with bundled Harper, a dockable review sidebar, persistent grammar preferences, personal words, and terminology rules.

Version 0.9 is a Linux x86-64 build. See the [changelog](CHANGELOG.md) for release history.

## Contributors

- **Kaustubh R. Mote** leads and maintains LibreHarp.
- **Codex** provided AI assistance with implementation, tests, and documentation.

LibreHarp's original code and artwork use the [Zero-Clause BSD license (0BSD)](LICENSE). See [third-party notices](THIRD_PARTY.md) for Harper and its dependencies.

## Use

Install `build/LibreHarp_v0.9.oxt` through LibreOffice's Extension Manager and restart LibreOffice. In Writer, choose LibreHarp → About LibreHarp to see the installed extension and Harper versions. Choose LibreHarp → Use LibreHarp for English checking to use LibreHarp for both spelling and grammar. This enables automatic checking and disables competing providers for US, British, Australian, Canadian, and Indian English. Other languages and unsupported English dialects keep their existing providers.

Checker choices apply to the whole LibreOffice profile. This mode also disables native spelling for those English dialects in Calc and Impress, where LibreHarp does not run. Choose LibreHarp → Restore previous English checkers to recover the saved provider selections and automatic-check settings. Repeating the takeover action preserves the original restore point. Installation alone does not change checker choices.

To keep native spelling alongside LibreHarp, select LibreHarp as the English grammar checker in Tools → Options → Languages and Locales → Writing Aids, and leave Hunspell enabled. Enable automatic spell and grammar checking for inline feedback.

Set the text language to English and choose LibreHarp → Open sidebar. Select a finding from the top dropdown, read its context and explanation, then choose a replacement and Apply. Previous and Next move through findings. The explanation grows with the panel's height. The sidebar keeps the nearest finding selected after edits and ignores. The default automatic recheck delay is one second. Replacements support Writer's Undo and track-changes mode. The separate Review document window remains available.

In the sidebar preview, LibreHarp underlines the flagged text in red. The selected suggestion appears in green and bold under **Suggested replacement**. High-contrast themes keep their own text colors.

Right-click an English spelling or grammar underline to open the LibreHarp menu. **Replace**, **Remember word**, and **Disable rule** group the actions with Unicode tree branches. All branches stay visible and run in one click. Group headings have no action. **Ignore once** applies until the next check. **Open sidebar** selects the clicked finding and shows its explanation, even if the sidebar is already open. Ordinary text menus keep their commands and gain a LibreHarp submenu when the selection overlaps a finding. Tracked-change commands remain available.

Add globally saves the exact word across documents and profiles. LibreHarp also mirrors personal words into an in-memory Writer dictionary and rebuilds it at startup. Removing a personal word removes it from this mirror. Other Writer dictionaries remain unchanged. Document and project words and rule choices affect LibreHarp. In exclusive English mode, no separate native English provider remains to add duplicate findings. If native spelling remains enabled, it can still flag words accepted only in a LibreHarp document or project.

Ignore once dismisses the clicked occurrence until the next check. Disable rule saves a lasting choice in the selected scope. Document choices require saving the document. Project branches appear for locally saved documents. Read-only documents omit replacement and document-scope actions. Actions refuse to edit or save a finding if its paragraph has changed. Unsupported languages retain Writer's original menu. If no completed LibreHarp result is cached, the popup offers the sidebar to check the text without blocking the menu on the engine.

For a spelling or word-splitting finding, click Add globally to save the exact spelling to your personal dictionary for all documents and profiles. More actions selects this choice automatically. Its button tooltip and accessible name include the word. No scope change or settings window is needed.

More actions offers only actions that apply to the selected finding. Dictionary actions appear for spelling findings; locating text and disabling a rule require a finding. Grammar rules, settings, and vocabulary remain available when there are no findings. Select another action and click Go to run it. Eight common rules include original explanations and before/after examples checked against bundled Harper. Other findings retain Harper's explanation. The rule browser also shows these examples.

Use Tab and Shift+Tab to navigate controls, Space to activate a focused button, and underlined button mnemonics with Alt. F8 focuses the readable Status field. Escape closes a dialog or returns from the sidebar to Writer. Validation errors focus Status, and closing a child dialog restores its launching control. See [keyboard and accessibility details](docs/ACCESSIBILITY.md) for verification and remaining limits.

Sidebar controls follow native font sizes and wrap into extra rows in narrow panels. Short panels scroll, and keyboard focus reveals the selected control. Dialogs keep large text readable, fit their viewport to the primary display, and provide native scrollbars for overflow.

Choose the sidebar's scope before using More actions → Disable rule or Remember word in selected scope: this document, this project, or everywhere. Document choices are stored inside the document and require saving the document to persist after closing it. Project choices are stored in `.libreharp.json`. Personal choices are stored in the LibreOffice profile.

Grammar rules searches the bundled Harper rule catalog, which contains 961 rules in Harper 3.1.0. It shows the effective state and the scope responsible for it. Enable, Disable, and Use inherited default affect only the selected scope. Use inherited default removes that scope's explicit choice; a higher-precedence choice can still apply.

Combine search with a category, enabled or disabled state, and the Overrides or New in bundled Harper filter. The new-rule filter in Harper 3.1.0 shows the 25 rule identifiers added since 3.0.0.

Disable rule everywhere saves a global preference. Ignore once hides the current review finding until the next check. Writer's own Ignore All callback is session-only; use LibreHarp's settings for permanent choices.

In the sidebar, choose More actions → Remember this ignore to save an exception for the selected finding. Save the document to keep it after closing. Manage saved ignores lets you restore individual exceptions. An exception matches the checked English text and the finding's range within it. Editing that text can invalidate the exception. Writer treats identical checked passages in the same document as the same match.

Settings supports named profiles, English dialects, personal words, `RuleName=false` overrides, a custom sentence word limit, and literal `find => replacement` terminology rules. Set `LongSentences=false` to permanently disable Harper's long-sentence warning. Global overrides take precedence over profiles. Remove a rule line to restore Harper's default. Personal words are case-sensitive. Custom terminology is literal, case-sensitive, and word-boundary matched, not executable code or arbitrary regular expressions.

Open Settings → Advanced settings to set the sidebar recheck delay, the maximum UTF-8 bytes per English text run, and filename or path exclusions. Use a pattern like `*.draft.odt` or `*/Archive/*`. Harper's experimental English isolation applies within text Writer marks as English. The diagnostic severity appears in the sidebar. To count accepted replacements, ignores, and words remembered from findings, enable Record local counts by rule and save. View local statistics shows those counts and offers a reset. LibreHarp stores counts by rule on this computer.

Accepted words suppress only exact `SpellCheck` and `SplitWords` findings. For example, accepting `homonuclear` and `radiofrequency` keeps those forms while leaving `SplitWords` active for other text such as `inthe`. Other grammar and terminology checks remain active. Matching is case-sensitive; add `Homonuclear` separately if you use that capitalization. Existing saved words gain this behavior automatically.

To add many personal words, open LibreHarp → Personal words and terminology → Add word list. Paste one word per line and click Add words. Blank lines and duplicate entries are ignored. The list merges with your saved words. Invalid entries reject the whole list without changing the saved vocabulary. For a document or project list, choose that scope in the sidebar, then open More actions → Words and terminology → Add word list. Save the document to keep document-scoped words.

Use Words and terminology for dedicated add/remove controls. The sidebar opens that editor in its selected scope; the menu's Personal words and terminology edits personal vocabulary. The advanced text fields remain available in personal settings.

Use Import list or Export list to exchange a Harper dictionary for the scope shown at the top of the window. The file format is UTF-8 with one word per line. Import opens a preview. Choose Add words to merge the list with existing entries.

In Grammar rules, choose Weir rules to write a personal custom rule or open a `.weir` file. Load example fills in a rule with two tests. Validate and test runs the tests with Harper. Save rule enables a validated rule, and the Personal Weir rules category gives it the same scope controls as other rules. The editor is available in the Harper 3.1.0 build. [Weir syntax and tests](https://writewithharper.com/docs/weir)

Preferences live in the current LibreOffice user profile under `user/LibreHarp/preferences.json`. Export saved preferences before experimenting; imports preserve a backup of the previous preferences. Do not edit the JSON file while a settings window is open.

## Document and project settings

Open LibreHarp → Document and project settings. Select a scope, then Load selected scope. Set its profile, dialect, sentence limit or rules, then Save selected scope. A blank sentence limit and the `inherit` choices leave the lower scope in control. Save the document after changing embedded settings.

Precedence is document, then project, then personal global rules, then the selected profile, then Harper defaults. Personal words combine across scopes. Terminology entries with the same find text are replaced by the more specific scope's entry. A profile override refers to a personal profile by name; a missing profile produces an error rather than silently changing behavior.

To create a project, save the document locally and choose a containing folder in the project settings form. Saving that scope creates `.libreharp.json` there. Other documents beneath that folder use it automatically. The nearest project file wins if projects are nested. Save As outside the folder drops the previous project's settings. Embedded document settings travel with the document. Remote and unsaved files can use document settings, but cannot create a directory project.

Writer's opaque proofreading ID is bound through its document-specific proofreading API. No active-window fallback is used. First inline checks wait for this binding. Review and sidebar checks use their own document object directly.

## Import old choices

Open a document previously used with LibreHarper, then choose LibreHarp → Import from LibreHarper. Optionally enter the path to its Harper dictionary, a UTF-8 file with one word per line. Choose Preview import. Import personal words and Import document ignores are separate actions.

Only recognized Harper rule identifiers are migrated. Existing LibreHarp document choices take precedence; original metadata and dictionary files remain unchanged. Word import creates a personal-preference backup. Save the document to retain imported ignores. Historical cached grammar results and unrecognized rule identifiers are not imported.

## Development

The Python source has no runtime third-party dependencies. Use Python 3.11 or later; UNO integration requires LibreOffice's Python runtime.

```sh
uv sync --locked
uv run python scripts/vendor_engine.py
uv run python scripts/vendor_engine.py --version 3.0.0
cargo fetch --locked --manifest-path weir-bridge/Cargo.toml
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python scripts/build.py
uv run python scripts/check_package.py
```

The build verifies the engine, rule catalog, and license checksums and produces a versioned OXT and SHA-256 file. It packages one Harper release. The Harper 3.1.0 package also builds a persistent Weir helper against the same pinned Harper commit. Install Rust and Cargo for that build. `vendor_engine.py` restores the language server from the pinned official release after a fresh checkout.

### Select or roll back Harper

The repository retains each engine under `vendor/harper/releases/<version>/`, alongside its matching catalog, license, and provenance. Binary files are ignored by Git. The metadata and checksums remain tracked so that missing binaries can be downloaded and verified again. `vendor/harper/selected.json` chooses the default engine for source tests and builds.

To build a rollback package without changing the default selection, run:

```sh
uv run python scripts/vendor_engine.py --version 3.0.0
uv run python scripts/build.py --harper-version 3.0.0
uv run python scripts/check_package.py build/LibreHarp_v0.9_harper-3.0.0.oxt
```

The separate filename preserves the normal `LibreHarp_v0.9.oxt` package. Install the chosen OXT through Extension Manager and restart LibreOffice. Changing the repository selection alone does not change an installed extension.

To change the default engine, run `uv run python scripts/vendor_engine.py --select 3.0.0`. The command verifies the complete release before changing the selection. Use `--select 3.1.0` to return to the current engine. Run the tests and rebuild after changing the selection.

An installed OXT includes the selected `harper-ls`, catalog, license, and provenance in `vendor/harper/`. Packages with Weir support also include `libreharp-weir` and its dependency notices.

For a new Harper release, create a new version directory and retain the existing directories. Copy the matching upstream catalog and license, then record the release URL, asset name, and SHA-256 values in `provenance.json`. Verify the downloaded archive against the digest published with the official GitHub release before recording the executable hash. Restore and test the new version before selecting it for a release.

Build the OXT, then run the same Writer checks across installations.

```sh
# Find and test every AppImage in a directory, including subdirectories.
uv run python scripts/test_lo_matrix.py --appimage-root /path/to/libreoffice/images --gui

# Test an installed Linux LibreOffice with a system Python that has UNO.
uv run python scripts/test_lo_matrix.py /usr/lib/libreoffice/program --uno-python /usr/bin/python3
```

The matrix also accepts individual AppImages, extracted AppImage roots, or `soffice` paths. It uses bundled Python when present. For a distro install, use the system Python with that distribution's LibreOffice Python bindings. LibreHarp requires Python 3.11 or later. Each run creates a fresh profile per installation and writes a summary, logs, and suite reports under `test-zone/matrix/`. AppImages run from temporary extractions. Add `--gui` for the keyboard popup and visible About checks. Those checks use Xephyr, Mutter, X11 tools, and ImageMagick. Run the standalone popup suite for the additional mouse checks on builds that expose the accessibility tree.

To run individual suites, use LibreOffice's bundled Python or another Python with UNO support.

```sh
uv run --no-project /path/to/libreoffice/program/python scripts/test_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_harper_features.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_scopes_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_extended_writer.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_complex_writer.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_english_checking.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_context_menu.py
uv run python scripts/isolated_display.py /path/to/libreoffice/program/python scripts/test_popup_writer.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_accessibility.py
uv run --no-project /path/to/libreoffice/program/python scripts/preview_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/preview_sidebar.py
```

Set `LIBREHARP_LO_PROGRAM` if the standalone scripts cannot find `soffice` and `unopkg`. Set `LIBREHARP_TEST_ZONE` to put the standalone scripts' test profile and reports in a separate directory. The installation test writes `report.json` there.

See the [testing guide](docs/TESTING.md) for release checks and coverage.

## Current scope

English grammar and spelling only. No remote service is used. Harper 3.1.0 is bundled; updates are explicit extension rebuilds. Windows/macOS packages and older LibreOffice versions remain untested.

Review covers body text, tables, frames, footnotes, endnotes, and headers/footers of used page styles. It checks contiguous English text portions and preserves their paragraph offsets. Field contents are excluded. Text on either side can be checked when Writer exposes matching text ranges; replacements use those native ranges and cannot overwrite fields. Unsupported paragraph representations and wholly non-English paragraphs are skipped and counted in the status. Inline proofreading follows Writer's language selection. Personal words suppress exact spelling findings; they do not teach Harper grammatical word classes. Paragraphs exceeding Harper's 120 KB limit produce an error instead of a clean result.

ODT and DOCX document-setting round trips, merged and nested table edits, footnote replacements, input-field preservation, and replacement alongside existing tracked changes are tested. A 1,000-paragraph review completed in about 15 seconds on the development machine; this is one local measurement, not a performance guarantee. Native keyboard and accessibility-tree checks are covered, along with a GTK3/AT-SPI bridge probe. Spoken screen-reader output, live changes between monitor scales, overlapping redlines, other field types, and other file formats need broader coverage. Manual edits to a project file are picked up on the next check; use Check after changing one externally.

Planned improvements include more rule explanations and translations. An update UI depends on a trusted distribution channel and explicit user approval before downloading or running an engine update.
