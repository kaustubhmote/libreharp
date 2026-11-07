# LibreHarp changelog

See the [testing guide](docs/TESTING.md) for verification steps and coverage.

## 0.9

- Switched LibreHarp's original code and artwork to the Zero-Clause BSD license (0BSD). Bundled components retain their own licenses and notices.

- Added a LibreHarp icon to the Writer sidebar, Extension Manager, and About dialog.
- Credited Kaustubh R. Mote as maintainer and Codex for AI development assistance in About and the extension description.
- Added a link to the project's GitHub repository in About.

## 0.8.2

- The Writer sidebar underlines flagged text in red and shows the selected replacement in green and bold. The preview updates when you choose a different suggestion.
- The sidebar uses LibreOffice's text colors in high-contrast mode. The preview was checked in light and dark themes.
- Passed 51 Python tests and 105 checks each on LibreOffice 25.8.0.4, 26.2.2.2, and 26.8.1.1 AppImages in isolated profiles.

## 0.8.1

- **LibreHarp → About LibreHarp** shows the extension version and bundled Harper version.
- Added a compatibility test runner for LibreOffice AppImages and conventional Linux installations. It tests each target in a separate profile.

## 0.8

- Filter grammar rules by category, effective state, overrides, or whether they are new in the bundled Harper version.
- Configure automatic recheck delay, text size limits, file exclusions, English isolation, and sidebar diagnostic severity in **Advanced settings**.
- Save individual ignores in a document and restore them later. Import and export word lists for personal, document, or project vocabulary.
- Write, import, and test personal Weir rules. Optionally record local counts of actions by rule.

## 0.7.1

- **Open sidebar** from a Writer context menu selects the clicked finding, including when the sidebar is already open or the same error occurs more than once.

## 0.7.0

- Updated the bundled engine to Harper 3.1.0. The build can also package the retained Harper 3.0.0 engine for rollback.
- Fixed suggestions for findings after emoji with Harper 3.1.0.

## 0.6.2

- Grouped right-click actions under **Replace**, **Remember word**, and **Disable rule**. The actions remain visible and directly clickable.
- Kept explanations in the sidebar and updated the spelling example to use `recieve` and `receive`.

## 0.6.1

- Remembered words also suppress matching split-word findings. Entries match the exact spelling and capitalization.
- Added **Add word list** to merge a list into personal, document, or project vocabulary.

## 0.6.0

- Added LibreHarp corrections, dictionary actions, and scoped rule controls to Writer's context menus.
- Added opt-in exclusive English checking and a command to restore the previous checkers.
- Mirrored personal vocabulary into Writer's in-memory dictionary.

## 0.5.1

- Spelling findings offer **Add globally** directly in the sidebar. The button identifies the word and saves it across profiles and documents.

## 0.5.0

- Adapted sidebar controls and dialogs to large fonts, high DPI, and narrow or short viewports. Keyboard focus scrolls controls into view.

## 0.4.0

- Added accessible control names, keyboard navigation, and focus restoration in the sidebar and dialogs.
- Added **F8** to focus the status field and **Escape** to return focus to Writer or close a dialog.

## 0.3.0

- Made the sidebar more compact and added surrounding text and examples for common findings.
- Preserved input fields and existing tracked changes during tested replacements. Added support for applying suggestions in merged and nested tables.

## 0.2.0

- Added the dockable Writer sidebar, document and project settings, and dedicated vocabulary editors.
- Extended review to headers, footers, notes, frames, and English text in mixed-language paragraphs.
- Added import previews for recognized LibreHarper ignores and word lists.

## 0.1.0

- First Linux release with bundled Harper, a Writer review window, a searchable grammar rule browser, and local preferences for profiles, words, and terminology.
