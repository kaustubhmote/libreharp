# Build and test LibreHarp

The [changelog](../CHANGELOG.md) records release results. See [engine updates](ENGINE_UPDATES.md) for instructions on selecting a Harper release.

## Release checks

- Verify that permanent rule suppression survives a LibreOffice restart and dictionary edits invalidate cached results.
- Verify that document overrides stay within their document.
- Reject suggestions for text that has changed. Verify that accepted suggestions support Undo.
- Report engine failures to the user.
- Run tests with disposable profiles and documents.

## Build and run the Python tests

Use Python 3.11 or later, uv, and Rust with Cargo. From the project directory, run the following commands.

```sh
uv sync --locked
uv run python scripts/vendor_engine.py
cargo fetch --locked --manifest-path weir-bridge/Cargo.toml
uv run ruff check libreharp scripts tests
uv run ruff format --check libreharp scripts tests
uv run pytest -q
uv run python scripts/build.py
uv run python scripts/check_package.py
```

The build writes a versioned OXT and its SHA-256 checksum under `build/`.

## Test LibreOffice installations

```sh
uv run python scripts/test_lo_matrix.py --appimage-root /path/to/libreoffice/images --gui
uv run python scripts/test_lo_matrix.py /usr/lib/libreoffice/program --uno-python /usr/bin/python3
```

Pass individual AppImages, extracted roots, program directories, or `soffice` paths to select specific targets. For a distro install, point `--uno-python` to Python 3.11 or later with that distribution's UNO bindings. Each target gets a fresh profile. The runner writes its summary, logs, and suite reports under `test-zone/matrix/`. The optional `--gui` checks use Xephyr, Mutter, X11 tools, and ImageMagick.

Run individual suites with LibreOffice's bundled Python or another Python with UNO support.

```sh
uv run --no-project /path/to/libreoffice/program/python scripts/test_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_harper_features.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_scopes_libreoffice.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_context_actions.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_context_menu.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_english_checking.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_extended_writer.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_complex_writer.py
uv run --no-project /path/to/libreoffice/program/python scripts/test_accessibility.py
uv run python scripts/isolated_display.py /path/to/libreoffice/program/python scripts/test_popup_writer.py
```

Set `LIBREHARP_LO_PROGRAM` if a standalone script cannot find the LibreOffice program directory. Set `LIBREHARP_TEST_ZONE` to choose a separate directory for its disposable profile and reports. The installation suite defaults to `test-zone/profile` and writes `test-zone/report.json`. It retains that test profile between runs to exercise extension replacement.

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

## Version 0.5.1 dictionary shortcut

The context-action suite exercises the installed sidebar's native controls. It verifies one-click global additions, refresh of two open documents, cross-profile vocabulary, persistence after restart, refusal of stale findings, document-scope isolation, and action changes when moving between grammar and spelling findings. The keyboard suite also checks action selection with arrow keys, Tab to the dictionary button, and Space to add the word. Scaling checks exercise the longer button label and focus reveal in a narrow panel.

Version 0.5.1 passes 32 unit/engine tests and 202 LibreOffice checks: 28 baseline, 28 scope, 16 context-action, 36 keyboard, 46 at 200% fonts, and 48 at 192 DPI. The six reports and package checksum are retained in `v0.5.1-*.json`. The other 0.5.0 scaling cases and unrelated document-format suites were not repeated for this patch.

## Version 0.5.0 baseline evidence

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

Expand compatibility testing to distro-installed and older LibreOffice versions, Windows, and macOS. Test Orca speech and braille, high-contrast themes, and live changes between monitors with different scales. Fixed startup scaling tests cover the default, generic, and GTK3 backends and use the primary work area for dialog fitting.

Expand document coverage to overlapping tracked changes, protected sections, more field types, and DOCX files created by other word processors. Measure review performance beyond 1,000 paragraphs.
