# Use LibreHarp with a keyboard or screen reader

Version 0.4.0 uses LibreOffice's native controls. The sidebar and dialogs expose explicit names for editable fields, lists, explanations, and status messages.

## Navigate the extension

| Key | Behavior inside LibreHarp |
| --- | --- |
| Tab / Shift+Tab | Move forward or backward through controls. Static labels and disabled controls are skipped. |
| Arrow keys | Select items in a focused list or dropdown. |
| Alt+Down | Open a native dropdown. |
| Space | Activate a focused button or checkbox. |
| Alt plus an underlined letter | Activate a button's mnemonic. |
| F8 | Focus the read-only Status field. Its text can be read and selected. |
| Escape | Close a dialog, or return from the sidebar to Writer while leaving the sidebar open. A native popup may handle Escape first. |

Choose **LibreHarp → Open sidebar** to open the panel and focus its Findings selector. Tab reaches navigation, the explanation, replacements, scope, secondary actions, checking controls, and Status. The vocabulary editor keeps word entry and its buttons together before the terminology controls.

Closing a child dialog returns focus to the control that opened it. Background checking preserves your focus. The F8 shortcut applies only inside LibreHarp; Writer retains its own F8 behavior when the document has focus.

Escape does not save unsaved settings fields. Word and terminology actions save immediately, as their editor states.

## Read feedback

The explanation and Status controls are read-only text fields, not images or labels inferred from nearby controls. Validation errors move focus to Status. Status updates emit native accessibility text-change events. Press F8 to read the current message without waiting for a screen reader to announce a background update.

Accessible names distinguish the English dialect, personal words, terminology, project folder, and import/export path. For example, the dialect selector is named **English dialect**, rather than inheriting the nearby profile label.

## Verification and limits

The native test suite inspects names, keyboard focus, and text-change events in the sidebar and all six dialogs. It sends real X11 key events for Tab, Shift+Tab, button activation, mnemonics, F8, and Escape. Separate installation tests exercise the registered extension.

An independent AT-SPI client reads the Settings dialog and the installed sidebar through LibreOffice's GTK3 accessibility bridge in a private D-Bus session. Its 13 checks verify field names, status text, status focus, and focus on Findings after the Open sidebar command. These are the controls and values Linux screen readers can obtain. The test does not listen to Orca speech or validate braille output. Neither test changes the ordinary LibreOffice profile or desktop accessibility preferences.

A full Orca listening pass, other screen readers, high-contrast themes, enlarged system fonts, high-DPI layouts, translations, Windows/macOS, and older LibreOffice versions remain open. This release is not an accessibility certification.

Implementation references: LibreOffice's [native window properties](https://raw.githubusercontent.com/LibreOffice/core/master/toolkit/source/awt/vclxwindow.cxx) provide `AccessibleName`; its [key-handler interface](https://api.libreoffice.org/docs/idl/ref/interfacecom_1_1sun_1_1star_1_1awt_1_1XKeyHandler.html) supports consuming handled events.
