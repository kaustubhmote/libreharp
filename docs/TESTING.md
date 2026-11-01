# LibreHarp test zone

Version 0.5.0 targets Linux x86-64, LibreOffice 26.8, LibreOffice Python 3.13, and Harper 3.0.0. Development tests also run under Python 3.14.

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
uv run --no-project /path/to/libreoffice/program/python scripts/test_complex_writer.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_accessibility.py
```

Set `LIBREHARP_LO_PROGRAM` to that LibreOffice program directory if it differs from the default in the script. The script installs the OXT only into `test-zone/profile`, selects LibreHarp for English there, exercises the extension, restarts that LibreOffice instance, and records `test-zone/report.json`. It retains the profile so later runs also test extension replacement. The ordinary user profile is not used.

The installed Python UNO component and Writer's proofreading iterator are exercised directly. The installed sidebar factory creates a native panel, and its Apply button is activated through a native accessibility action. Other review/settings controls are instantiated against the real LibreOffice UNO context for inspection. Registered menu dispatch and visible deck activation are separately exercised from the installed OXT. The suite does not simulate every mouse click or claim a complete accessibility audit.

The keyboard suite requires an X11 display and `xdotool`. It sends actual key events to its own test windows. For an independent Linux accessibility bridge check, install the system Python `pyatspi` bindings and run:

```sh
dbus-run-session -- env SAL_USE_VCLPLUGIN=gtk3 GIO_USE_VFS=local GTK_USE_PORTAL=0 \
  uv run --no-project /path/to/libreoffice/program/python scripts/test_atspi.py
```

This uses a private D-Bus session and `/usr/bin/python3` for the external AT-SPI client. It inspects only named test windows. The report includes the Settings controls and the installed sidebar controls, with their names, roles, text, and focus state. It does not change desktop accessibility preferences. See [accessibility behavior and limits](ACCESSIBILITY.md).

## Test font and display scaling

Install Xephyr and Mutter to run GUI tests in a nested X display. This prevents other desktop windows from taking the test's keyboard focus. The wrapper uses temporary window-manager configuration and closes only its own processes.

```sh
uv run python scripts/isolated_display.py uv run python scripts/scaling_matrix.py
uv run python scripts/isolated_display.py \
  uv run --no-project /path/to/libreoffice/program/python scripts/test_accessibility.py
uv run python scripts/isolated_display.py dbus-run-session -- \
  env SAL_USE_VCLPLUGIN=gtk3 GIO_USE_VFS=local GTK_USE_PORTAL=0 \
  uv run --no-project /path/to/libreoffice/program/python scripts/test_atspi.py
```

The matrix starts a separate LibreOffice process for each of six cases: default, GTK fonts at 150% and 200%, generic VCL at 144 and 192 DPI, and GTK display scaling at 200%. Environment overrides apply only to the child process. Each report records the actual logical work area and native control dimensions. Do not run suites concurrently against the same test profile.

The scaling checks cover all six dialogs, full Settings tab traversal, F8 and Escape, action-label fit, sidebar row wrapping, non-overlap, explanation growth, and scrolling in a 300-by-400 panel. X11 client dimensions must match each dialog's UNO viewport. Generic VCL checks the installed panel against every ancestor clipping boundary and verifies Status focus. The tests also capture the installed sidebar before and after F8. Reports and screenshots use `test-zone/scaling-<case>-*` filenames. The external AT-SPI test additionally verifies that F8 focuses the installed sidebar's Status within the Writer window bounds. Set `GDK_DPI_SCALE=2 LIBREHARP_SCALE_CASE=font200` before the AT-SPI command for the larger-font bridge check.

## Inspect visible windows

```sh
uv run --no-project /path/to/libreoffice/program/python scripts/preview_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/preview_sidebar.py
```

This requires an X11 display, `xdotool`, and ImageMagick's `import`. It opens test documents and captures only its own Writer/sidebar and extension windows into `test-zone/`, then closes the test instance.

## Current evidence

- 32 unit/engine tests cover the core, scope precedence, project discovery/isolation, migration parsing, and rule help. All eight before/after examples are checked against the pinned engine.
- 135 native LibreOffice regression checks: 28 baseline, 28 sidebar/scope, 30 extended, 17 complex-document, and 32 accessibility/keyboard checks.
- Six font and DPI cases cover 262 checks. The installed extension also has 14 external GTK3/AT-SPI checks at normal fonts and 14 at 200% fonts. See `v0.5.0-validation.json` and the thirteen versioned JSON reports for the release results.
- Keyboard checks cover explicit field names in all six dialogs and the sidebar, Tab and Shift+Tab, mnemonics, Space, F8, Escape, status text-change events, validation-error focus, child-dialog focus return, and background rechecks that preserve focus.
- Review, rule browser, sidebar, scoped-settings and vocabulary screenshots were inspected. The compact findings dropdown leaves most of the panel for context and explanations. Native tests cover the minimum panel size, vertical growth, navigation, Apply/Undo, scope actions, and empty state.
- Permanent suppression survives a complete LibreOffice process restart.
- Review automatically refreshes after edits while the review window is open.
- Replacements preserve surrounding text and formatting, refuse stale paragraphs, and support Undo.
- Identical text in separate documents retains separate scopes. ODT reopening and Save As are covered, as is scope rebinding after a LibreOffice restart.
- Headers, footers, frames, footnotes, endnotes, English runs within mixed-language paragraphs, and tracked replacements are covered.
- Input-field contents are excluded from review; edits after the field and Undo retain its content. Direct attempts to replace field text are rejected.
- Merged/nested table edits, preservation of existing tracked changes, and DOCX metadata export/reopen are covered. These fixtures do not prove compatibility with every Word-produced document or field type.
- A fixture with 1,000 explicitly inserted Writer paragraphs completed review in 15.596 seconds on this machine. The report records the measured time. The historical 100-line fixture remains as a refresh regression test; it does not establish an actual paragraph count.
- Migration tests cover preview, changed-source rejection, backup creation, precedence and preservation of legacy metadata.

## Gaps

No Windows/macOS tests, older LibreOffice compatibility matrix, Orca listening or braille pass, exhaustive keyboard audit, high-contrast theme checks, or live changes between monitors with different scales. Dialog fitting uses the primary work area. Fixed startup font/DPI cases exercise the default, generic, and GTK3 backends; they do not repeat every accessibility action at every scale. Overlapping redlines, protected sections, more field types, and files created by other applications need broader coverage. Inline proofreading is tested through Writer's API, not by pixel recognition of underlines. Field exclusion and mixed-language segmentation are review/sidebar features; inline checks follow Writer's text and language.
