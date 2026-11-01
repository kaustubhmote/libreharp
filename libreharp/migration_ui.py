"""Preview legacy choices before merging; retain all legacy metadata and files."""

import time

from .migration import LEGACY_PROPERTY, legacy_rules, word_list
from .scopes import ScopeTarget
from .store import fingerprint
from .uno_app import Window


class Migration(Window):
    def __init__(self, app, document):
        super().__init__(app, "LibreHarp - import from LibreHarper", 420, 270)
        self.document = document
        self.rules = []
        self.words = []
        self.preview_source = None
        self.add(
            "intro",
            "FixedText",
            8,
            8,
            404,
            30,
            Label="Preview old document ignores and an optional Harper word list. Existing LibreHarp choices take precedence. Original data stays unchanged.",
        )
        self.add(
            "path_label",
            "FixedText",
            8,
            44,
            404,
            12,
            Label="Optional UTF-8 dictionary file, one word per line",
        )
        self.add("path", "Edit", 8, 60, 404, 15)
        self.button("preview", "Preview import", 8, 84, 120, self.preview)
        self.add("preview_text", "Edit", 8, 108, 404, 96, MultiLine=True, ReadOnly=True, VScroll=True)
        self.button("words", "Import personal words", 8, 212, 155, self.import_words)
        self.button("rules", "Import document ignores", 170, 212, 155, self.import_rules)
        self.button("close", "Close", 332, 212, 80, self.close)
        self.add(
            "status",
            "FixedText",
            8,
            235,
            404,
            28,
            Label="Nothing is imported until you select an import button.",
        )

    def raw(self):
        props = self.document.DocumentProperties.UserDefinedProperties
        return (
            props.getPropertyValue(LEGACY_PROPERTY)
            if props.PropertySetInfo.hasPropertyByName(LEGACY_PROPERTY)
            else "{}"
        )

    def preview(self):
        raw = self.raw()
        self.rules, skipped = legacy_rules(raw)
        path = self.model.getByName("path").Text.strip()
        self.words = word_list(path) if path else []
        self.preview_source = fingerprint([raw, path, self.words])
        self.model.getByName("preview_text").Text = (
            f"{len(self.rules)} recognized document ignores; {len(skipped)} unknown or non-Harper entries skipped.\n"
            + "\n".join(self.rules)
            + f"\n\n{len(self.words)} personal words:\n"
            + "\n".join(self.words[:100])
        )
        self.status("Preview ready. Import words and document ignores separately.")

    def verify(self):
        if self.preview_source is None:
            raise ValueError("Preview the import first.")
        path = self.model.getByName("path").Text.strip()
        words = word_list(path) if path else []
        if fingerprint([self.raw(), path, words]) != self.preview_source:
            raise ValueError("Source changed. Preview again before importing.")

    def import_words(self):
        self.verify()
        if not self.words:
            raise ValueError("No words to import. Select a dictionary file and preview it.")
        backup = self.app.store.directory / f"preferences.before-migration-{time.time_ns()}.json"
        self.app.store.export_to(backup)
        self.app.store.update(lambda d: d.update(words=sorted(set(d["words"]) | set(self.words))))
        self.app.changed()
        self.status(
            f"Imported {len(self.words)} words. Personal preferences backed up in the LibreHarp profile folder."
        )

    def import_rules(self):
        self.verify()
        if not self.rules:
            raise ValueError("No recognized Harper ignores in this document.")

        def change(data):
            for rule in self.rules:
                data.setdefault("rules", {}).setdefault(rule, False)

        ScopeTarget(self.app, self.document).update(change)
        self.status(
            "Document ignores imported. Save the document to retain them; legacy metadata remains intact."
        )
