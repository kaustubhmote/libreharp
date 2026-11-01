# LibreHarp

An independent LibreOffice Writer extension with bundled Harper, a dockable review sidebar, persistent grammar preferences, personal words, and terminology rules.

Version 0.2.0 is a Linux x86-64 development release. See PLAN.md for completed milestones and remaining work, and WORK_LOG.md for decisions and test evidence.

## Use

Install `build/LibreHarp_v0.2.0.oxt` through LibreOffice's Extension Manager and restart LibreOffice. In Tools → Options → Languages and Locales → Writing Aids, enable LibreHarp as the English grammar checker. Deselect competing English grammar checkers if they hide its results. Hunspell spelling can remain enabled. Enable automatic spell and grammar checking for inline feedback.

Set the text language to English and choose LibreHarp → Open sidebar. Select a finding, review its explanation and replacement, then choose Apply. Previous and Next move through the findings. Show in document selects the containing paragraph. The sidebar rechecks one second after edits while open. Replacements support Writer's Undo and track-changes mode. The separate Review document window remains available.

Choose the sidebar's scope before using Disable rule or Remember word: this document, this project, or everywhere. Document choices are stored inside the document and require saving the document to persist after closing it. Project choices are stored in `.libreharp.json`. Personal choices are stored in the LibreOffice profile.

Grammar rules searches 936 rules from the bundled Harper version. It shows the effective state and the scope responsible for it. Enable, Disable, and Use inherited default affect only the selected scope. Use inherited default removes that scope's explicit choice; a higher-precedence choice can still apply.

Disable rule everywhere saves a global preference. Ignore once hides the current review finding until the next check. Writer's own Ignore All callback is session-only; use LibreHarp's settings for permanent choices.

Settings supports named profiles, English dialects, personal words, `RuleName=false` overrides, a custom sentence word limit, and literal `find => replacement` terminology rules. Set `LongSentences=false` to permanently disable Harper's long-sentence warning. Global overrides take precedence over profiles. Remove a rule line to restore Harper's default. Personal words are case-sensitive. Custom terminology is literal, case-sensitive, and word-boundary matched, not executable code or arbitrary regular expressions.

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
uv run --no-project /path/to/libreoffice/program/python scripts/preview_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/preview_sidebar.py
```

Set `LIBREHARP_LO_PROGRAM` if the LibreOffice program directory differs from the local default in the test script. The installation test writes `test-zone/report.json`; the visual test captures only its own extension windows and needs an X11 display, `xdotool`, and ImageMagick. Neither test installs into your regular LibreOffice profile.

Validated on LibreOffice 26.8 with its Python 3.13 runtime, using the bundled Harper 3.0.0 Linux x86-64 binary. Other LibreOffice versions have not been tested. The extension requires Python 3.11 or later.

## Current scope

English grammar and spelling only. No remote service is used. Harper 3.0.0 is bundled; updates are explicit extension rebuilds. Windows/macOS packages and older LibreOffice versions remain untested.

Review covers body text, tables, frames, footnotes, endnotes, and headers/footers of used page styles. It checks contiguous English text portions and preserves their paragraph offsets. Unsupported field representations and wholly non-English paragraphs are skipped and counted in the status. Inline proofreading follows Writer's language selection. Personal words suppress exact spelling findings; they do not teach Harper grammatical word classes. Paragraphs exceeding Harper's 120 KB limit produce an error instead of a clean result.

ODT document-setting persistence, simple table/footnote replacements, basic tracked replacements, mixed-language review, and a 100-paragraph document are tested. Complex existing redlines, merged/nested tables, field-heavy documents, other file formats, accessibility and high-DPI behavior need broader coverage. Manual edits to a project file are picked up on the next check; use Check document after changing one externally.
