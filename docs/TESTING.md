# LibreHarp test zone

Version 0.2.0 is validated on Linux x86-64, LibreOffice 26.8, LibreOffice Python 3.13, and Harper 3.0.0. Development tests also run under Python 3.14.

## Reproduce the automated checks

From the project directory:

```sh
uv sync --locked
uv run python scripts/vendor_engine.py
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv run python scripts/build.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_scopes_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_extended_writer.py
```

Set `LIBREHARP_LO_PROGRAM` to that LibreOffice program directory if it differs from the default in the script. The script installs the OXT only into `test-zone/profile`, selects LibreHarp for English there, exercises the extension, restarts that LibreOffice instance, and records `test-zone/report.json`. It retains the profile so later runs also test extension replacement. The ordinary user profile is not used.

The installed Python UNO component and Writer's proofreading iterator are exercised directly. The installed sidebar factory creates a native panel, and its Apply button is activated through a native accessibility action. Other review/settings controls are instantiated against the real LibreOffice UNO context for inspection. Registered menu dispatch and visible deck activation are separately exercised from the installed OXT. The suite does not simulate every mouse click or claim a complete accessibility audit.

## Inspect visible windows

```sh
uv run --no-project /path/to/libreoffice/program/python scripts/preview_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/preview_sidebar.py
```

This requires an X11 display, `xdotool`, and ImageMagick's `import`. It opens test documents and captures only its own Writer/sidebar and extension windows into `test-zone/`, then closes the test instance.

## Current evidence

- 29 unit/engine tests cover the core, scope precedence, project discovery/isolation and migration parsing.
- 77 real LibreOffice checks passed: 28 baseline, 19 sidebar/scope, and 30 extended checks. See `v0.2.0-validation.json` and the three versioned JSON reports.
- Three real LibreOffice suites cover baseline installation/review, sidebar/document/project behavior, and extended document/editor/migration behavior. Their versioned JSON reports record every check and whether the run passed.
- Review, rule browser, sidebar, scoped-settings and vocabulary screenshots were inspected. Sidebar findings scroll horizontally when their summaries exceed its width; full explanations remain visible in the detail field.
- Permanent suppression survives a complete LibreOffice process restart.
- Review automatically refreshes after edits while the review window is open.
- Replacements preserve surrounding text and formatting, refuse stale paragraphs, and support Undo.
- Identical text in separate documents retains separate scopes. ODT reopening and Save As are covered, as is scope rebinding after a LibreOffice restart.
- Headers, footers, frames, footnotes, endnotes, English runs within mixed-language paragraphs, basic tracked replacements, and a 100-paragraph document are covered.
- Migration tests cover preview, changed-source rejection, backup creation, precedence and preservation of legacy metadata.

## Gaps

No Windows/macOS tests, older LibreOffice compatibility matrix, screen-reader audit, or exhaustive keyboard audit. Complex existing redlines, merged/nested tables, field-heavy text and non-ODT metadata round trips need broader coverage. Inline proofreading is tested through Writer's API, not by pixel recognition of underlines. Mixed-language segmentation is a review/sidebar feature; inline checks follow the language supplied by Writer.
