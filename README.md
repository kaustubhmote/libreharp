# LibreHarp

An independent LibreOffice Writer extension with bundled Harper, a dockable review sidebar, persistent grammar preferences, personal words, and terminology rules.

Version 0.6.2 is a Linux x86-64 development release. See PLAN.md for completed milestones and remaining work, and WORK_LOG.md for decisions and test evidence.

## Use

Install `build/LibreHarp_v0.6.2.oxt` through LibreOffice's Extension Manager and restart LibreOffice. Choose LibreHarp → Use LibreHarp for English checking to use LibreHarp for both spelling and grammar. This enables automatic checking and disables competing providers for US, British, Australian, Canadian, and Indian English. Other languages and unsupported English dialects keep their existing providers.

Checker choices apply to the whole LibreOffice profile. This mode also disables native spelling for those English dialects in Calc and Impress, where LibreHarp does not run. Choose LibreHarp → Restore previous English checkers to recover the saved provider selections and automatic-check settings. Repeating the takeover action preserves the original restore point. Installation alone does not change checker choices.

To keep native spelling alongside LibreHarp, select LibreHarp as the English grammar checker in Tools → Options → Languages and Locales → Writing Aids, and leave Hunspell enabled. Enable automatic spell and grammar checking for inline feedback.

Set the text language to English and choose LibreHarp → Open sidebar. Select a finding from the top dropdown, read its context and explanation, then choose a replacement and Apply. Previous and Next move through findings. The explanation grows with the panel's height. The sidebar keeps the nearest finding selected after edits and ignores. It rechecks one second after document edits while open. Replacements support Writer's Undo and track-changes mode. The separate Review document window remains available.

Right-click an English spelling or grammar underline to open the LibreHarp menu. **Replace**, **Remember word**, and **Disable rule** group the actions with Unicode tree branches. All branches stay visible and run in one click. Group headings have no action. **Ignore once** applies until the next check. **Open sidebar** shows the finding's explanation in the existing sidebar. Ordinary text menus keep their commands and gain a LibreHarp submenu when the selection overlaps a finding. Tracked-change commands remain available.

Add globally saves the exact word across documents and profiles. LibreHarp also mirrors personal words into an in-memory Writer dictionary and rebuilds it at startup. Removing a personal word removes it from this mirror. Other Writer dictionaries remain unchanged. Document and project words and rule choices affect LibreHarp. In exclusive English mode, no separate native English provider remains to add duplicate findings. If native spelling remains enabled, it can still flag words accepted only in a LibreHarp document or project.

Ignore once dismisses the clicked occurrence until the next check. Disable rule saves a lasting choice in the selected scope. Document choices require saving the document. Project branches appear for locally saved documents. Read-only documents omit replacement and document-scope actions. Actions refuse to edit or save a finding if its paragraph has changed. Unsupported languages retain Writer's original menu. If no completed LibreHarp result is cached, the popup offers the sidebar to check the text without blocking the menu on the engine.

For a spelling or word-splitting finding, click Add globally to save the exact spelling to your personal dictionary for all documents and profiles. More actions selects this choice automatically. Its button tooltip and accessible name include the word. No scope change or settings window is needed.

More actions offers only actions that apply to the selected finding. Dictionary actions appear for spelling findings; locating text and disabling a rule require a finding. Grammar rules, settings, and vocabulary remain available when there are no findings. Select another action and click Go to run it. Eight common rules include original explanations and before/after examples checked against bundled Harper. Other findings retain Harper's explanation. The rule browser also shows these examples.

Use Tab and Shift+Tab to navigate controls, Space to activate a focused button, and underlined button mnemonics with Alt. F8 focuses the readable Status field. Escape closes a dialog or returns from the sidebar to Writer. Validation errors focus Status, and closing a child dialog restores its launching control. See [keyboard and accessibility details](docs/ACCESSIBILITY.md) for verification and remaining limits.

Sidebar controls follow native font sizes and wrap into extra rows in narrow panels. Short panels scroll, and keyboard focus reveals the selected control. Dialogs keep large text readable, fit their viewport to the primary display, and provide native scrollbars for overflow.

Choose the sidebar's scope before using More actions → Disable rule or Remember word in selected scope: this document, this project, or everywhere. Document choices are stored inside the document and require saving the document to persist after closing it. Project choices are stored in `.libreharp.json`. Personal choices are stored in the LibreOffice profile.

Grammar rules searches 936 rules from the bundled Harper version. It shows the effective state and the scope responsible for it. Enable, Disable, and Use inherited default affect only the selected scope. Use inherited default removes that scope's explicit choice; a higher-precedence choice can still apply.

Disable rule everywhere saves a global preference. Ignore once hides the current review finding until the next check. Writer's own Ignore All callback is session-only; use LibreHarp's settings for permanent choices.

Settings supports named profiles, English dialects, personal words, `RuleName=false` overrides, a custom sentence word limit, and literal `find => replacement` terminology rules. Set `LongSentences=false` to permanently disable Harper's long-sentence warning. Global overrides take precedence over profiles. Remove a rule line to restore Harper's default. Personal words are case-sensitive. Custom terminology is literal, case-sensitive, and word-boundary matched, not executable code or arbitrary regular expressions.

Accepted words suppress only exact `SpellCheck` and `SplitWords` findings. For example, accepting `homonuclear` and `radiofrequency` keeps those forms while leaving `SplitWords` active for other text such as `inthe`. Other grammar and terminology checks remain active. Matching is case-sensitive; add `Homonuclear` separately if you use that capitalization. Existing saved words gain this behavior automatically.

To add many personal words, open LibreHarp → Personal words and terminology → Add word list. Paste one word per line and click Add words. Blank lines and duplicate entries are ignored. The list merges with your saved words. Invalid entries reject the whole list without changing the saved vocabulary. For a document or project list, choose that scope in the sidebar, then open More actions → Words and terminology → Add word list. Save the document to keep document-scoped words.

Use Words and terminology for dedicated add/remove controls. The sidebar opens that editor in its selected scope; the menu's Personal words and terminology edits personal vocabulary. The advanced text fields remain available in personal settings.

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
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
uv run python scripts/build.py
uv run python scripts/check_package.py
```

The build verifies the pinned engine checksum and produces a versioned OXT. `vendor_engine.py` can restore the ignored executable from the pinned official release after a fresh checkout. The rule catalog and licenses are retained as source files.

Run the real LibreOffice test zone with its own Python runtime:

```sh
uv run --no-project /path/to/libreoffice/program/python scripts/test_libreoffice.py
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

Set `LIBREHARP_LO_PROGRAM` if the LibreOffice program directory differs from the local default in the test script. The installation test writes `test-zone/report.json`; the visual test captures only its own extension windows and needs an X11 display, `xdotool`, and ImageMagick. Neither test installs into your regular LibreOffice profile.

Validated on LibreOffice 26.8 with its Python 3.13 runtime, using the bundled Harper 3.0.0 Linux x86-64 binary. Other LibreOffice versions have not been tested. The extension requires Python 3.11 or later.

## Current scope

English grammar and spelling only. No remote service is used. Harper 3.0.0 is bundled; updates are explicit extension rebuilds. Windows/macOS packages and older LibreOffice versions remain untested.

Review covers body text, tables, frames, footnotes, endnotes, and headers/footers of used page styles. It checks contiguous English text portions and preserves their paragraph offsets. Field contents are excluded. Text on either side can be checked when Writer exposes matching text ranges; replacements use those native ranges and cannot overwrite fields. Unsupported paragraph representations and wholly non-English paragraphs are skipped and counted in the status. Inline proofreading follows Writer's language selection. Personal words suppress exact spelling findings; they do not teach Harper grammatical word classes. Paragraphs exceeding Harper's 120 KB limit produce an error instead of a clean result.

ODT and DOCX document-setting round trips, merged and nested table edits, footnote replacements, input-field preservation, and replacement alongside existing tracked changes are tested. A 1,000-paragraph review completed in about 15 seconds on the development machine; this is one local measurement, not a performance guarantee. Native keyboard and accessibility-tree checks are covered, along with a GTK3/AT-SPI bridge probe. Spoken screen-reader output, live changes between monitor scales, overlapping redlines, other field types, and other file formats need broader coverage. Manual edits to a project file are picked up on the next check; use Check after changing one externally.
