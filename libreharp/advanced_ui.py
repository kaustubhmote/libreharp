"""Native dialog for personal checking options."""

import uno

from .advanced import DEFAULT_ADVANCED, SEVERITIES, advanced_options
from .statistics import ACTIONS
from .store import fingerprint
from .uno_app import Window, service


class AdvancedSettings(Window):
    def __init__(self, app, parent=None):
        super().__init__(app, "LibreHarp — advanced settings", 390, 275)
        self.parent = parent
        self.loaded = app.store.advanced()
        self.add("delay_label", "FixedText", 8, 10, 260, 13, Label="Sidebar recheck delay (milliseconds)")
        self.add("delay_ms", "Edit", 280, 8, 102, 16, HelpText="Sidebar recheck delay in milliseconds")
        self.add("limit_label", "FixedText", 8, 32, 260, 13, Label="Maximum bytes per English text run")
        self.add("max_bytes", "Edit", 280, 30, 102, 16, HelpText="Maximum UTF-8 bytes per English text run")
        self.add("severity_label", "FixedText", 8, 54, 260, 13, Label="Sidebar diagnostic severity label")
        self.add(
            "severity",
            "ListBox",
            280,
            52,
            102,
            16,
            Dropdown=True,
            StringItemList=SEVERITIES,
            HelpText="Diagnostic severity",
        )
        self.add(
            "isolate_english",
            "CheckBox",
            8,
            76,
            374,
            16,
            Label="Ask Harper to isolate English in mixed-language text (experimental)",
        )
        self.add(
            "exclude_label", "FixedText", 8, 98, 374, 14, Label="Exclude saved documents by name or path"
        )
        self.add(
            "exclude",
            "Edit",
            8,
            115,
            374,
            57,
            MultiLine=True,
            VScroll=True,
            HelpText="One pattern per line, for example *.draft.odt or */Archive/*",
        )
        self.add("record_statistics", "CheckBox", 8, 180, 230, 16, Label="Record local counts by rule")
        self.button("statistics", "View local statistics…", 245, 180, 137, self.show_statistics)
        self.button("save", "Save", 8, 208, 92, self.save)
        self.button("defaults", "Restore defaults", 108, 208, 130, lambda: self.fill(DEFAULT_ADVANCED))
        self.button("close", "Close", 290, 208, 92, self.close)
        self.add(
            "status",
            "FixedText",
            8,
            232,
            374,
            33,
            Label="Exclusions use wildcards, for example *.draft.odt or */Archive/*. A delay of 0 rechecks immediately.",
        )
        self.fill(self.loaded)

    def fill(self, options):
        for name in ("delay_ms", "max_bytes"):
            self.model.getByName(name).Text = str(options[name])
        self.model.getByName("severity").SelectedItems = (SEVERITIES.index(options["severity"]),)
        for name in ("isolate_english", "record_statistics"):
            self.model.getByName(name).State = int(options[name])
        self.model.getByName("exclude").Text = "\n".join(options["exclude"])

    def save(self):
        saved = advanced_options(
            {
                **self.loaded,
                "delay_ms": int(self.model.getByName("delay_ms").Text),
                "max_bytes": int(self.model.getByName("max_bytes").Text),
                "severity": self.dialog.getControl("severity").getSelectedItem(),
                "isolate_english": bool(self.model.getByName("isolate_english").State),
                "record_statistics": bool(self.model.getByName("record_statistics").State),
                "exclude": [
                    line.strip() for line in self.model.getByName("exclude").Text.splitlines() if line.strip()
                ],
            }
        )

        parent_current = False

        def change(data):
            nonlocal parent_current
            if advanced_options(data.get("advanced", {})) != self.loaded:
                raise ValueError(
                    "Advanced settings changed in another window. Reopen this dialog before saving."
                )
            parent_current = self.parent and self.parent.loaded_revision == fingerprint(data)
            data["advanced"] = saved

        updated = self.app.store.update(change)
        self.loaded = saved
        if parent_current:
            self.parent.loaded_revision = fingerprint(updated)
        self.app.changed()
        self.status("Saved. LibreHarp will recheck open documents with these settings.")

    def show_statistics(self):
        StatisticsWindow(self.app).show()


class StatisticsWindow(Window):
    def __init__(self, app):
        super().__init__(app, "LibreHarp — local statistics", 390, 230)
        self.add(
            "counts",
            "Edit",
            8,
            8,
            374,
            147,
            MultiLine=True,
            ReadOnly=True,
            VScroll=True,
            HelpText="Action counts by rule",
        )
        self.button("refresh", "Refresh", 8, 163, 90, self.refresh)
        self.button("clear", "Clear counts…", 106, 163, 120, self.clear)
        self.button("close", "Close", 290, 163, 92, self.close)
        self.add("status", "FixedText", 8, 187, 374, 33, Label="")
        self.refresh()

    def refresh(self):
        data = self.app.statistics.read()
        sections = []
        for action in ACTIONS:
            counts = data.get(action, {})
            if counts:
                lines = [
                    f"{count}  {rule}"
                    for rule, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
                ]
                sections.append(f"{action} ({sum(counts.values())})\n" + "\n".join(lines))
        self.model.getByName("counts").Text = "\n\n".join(sections) or "No actions recorded yet."
        self.model.getByName("clear").Enabled = bool(sections)
        recording = "on" if self.app.store.advanced()["record_statistics"] else "off"
        self.status(f"Recording is {recording}. Counts stay on this computer and contain no document text.")

    def clear(self):
        confirm = service(self.ctx, "awt.Toolkit").createMessageBox(
            self.dialog.getPeer(),
            uno.Enum("com.sun.star.awt.MessageBoxType", "QUERYBOX"),
            uno.getConstantByName("com.sun.star.awt.MessageBoxButtons.BUTTONS_YES_NO"),
            "LibreHarp",
            "Clear all local action counts?",
        )
        try:
            if confirm.execute() != uno.getConstantByName("com.sun.star.awt.MessageBoxResults.YES"):
                return
        finally:
            confirm.dispose()
        self.app.statistics.clear()
        self.refresh()
