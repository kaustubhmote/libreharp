"""Native editors bound to the document that opened them."""

from .scopes import PROJECT_FILE, ScopeTarget, local_path, project_path
from .store import fingerprint
from .uno_app import RuleBrowser, Settings, Window


class ScopedSettings(Window):
    def __init__(self, app, document):
        super().__init__(app, "LibreHarp - document and project settings", 430, 330)
        self.document = document
        self.target = ScopeTarget(app, document)
        self.add(
            "context",
            "FixedText",
            8,
            5,
            414,
            26,
            Label="Document > project > personal global > profile. Words are combined; terminology matches override inherited matches.",
        )
        self.add(
            "scope",
            "ListBox",
            8,
            36,
            240,
            15,
            Dropdown=True,
            StringItemList=("This document", "Project containing this document"),
            SelectedItems=(0,),
        )
        self.button("load", "Load selected scope", 260, 36, 162, self.load)
        path = project_path(document.URL)
        local = local_path(document.URL)
        self.add(
            "folder_label",
            "FixedText",
            8,
            57,
            414,
            12,
            Label="Project folder (must contain this saved document)",
        )
        self.add(
            "folder", "Edit", 8, 72, 414, 15, Text=str(path.parent if path else local.parent if local else "")
        )
        self.add("profile_label", "FixedText", 8, 94, 200, 12, Label="Profile override")
        self.add("dialect_label", "FixedText", 220, 94, 200, 12, Label="Dialect override")
        self.add(
            "profile",
            "ComboBox",
            8,
            109,
            200,
            15,
            Dropdown=True,
            StringItemList=("inherit", *app.store.read()["profiles"]),
        )
        self.add(
            "dialect",
            "ComboBox",
            220,
            109,
            202,
            15,
            Dropdown=True,
            StringItemList=("inherit", "auto", "American", "British", "Australian", "Canadian", "Indian"),
        )
        self.add(
            "limit_label",
            "FixedText",
            8,
            131,
            280,
            12,
            Label="Sentence word limit (blank inherits; 0 uses Harper default)",
        )
        self.add("limit", "Edit", 304, 129, 118, 15)
        self.add(
            "rules_label",
            "FixedText",
            8,
            150,
            414,
            12,
            Label="Overrides in this scope: RuleName=true or RuleName=false",
        )
        self.add("rules", "Edit", 8, 165, 414, 65, MultiLine=True, VScroll=True)
        self.button("rules_browser", "Browse rules", 8, 238, 105, self.browse_rules)
        self.button("vocabulary", "Words and terminology", 120, 238, 160, self.vocabulary)
        self.button("reset", "Clear overrides", 287, 238, 135, self.reset)
        self.button("save", "Save selected scope", 8, 262, 160, self.save)
        self.button("personal", "Personal settings", 176, 262, 140, lambda: Settings(app).show())
        self.button("close", "Close", 324, 262, 98, self.close)
        self.add("status", "FixedText", 8, 285, 414, 38, Label="")
        self.fill()

    def value(self, name):
        return self.model.getByName(name).Text

    def fill(self):
        self.data = self.target.read()
        self.loaded_revision = fingerprint(self.data)
        self.model.getByName("profile").Text = self.data.get("profile", "inherit")
        self.model.getByName("dialect").Text = self.data.get("dialect", "inherit")
        self.model.getByName("limit").Text = str(self.data.get("sentence_limit", ""))
        self.model.getByName("rules").Text = Settings.rule_text(self.data.get("rules", {}))
        self.status(
            "Editing "
            + (
                str(self.target.path)
                if self.target.path
                else "this document's embedded settings. Save the document to retain them."
            )
        )

    def load(self):
        kind = "project" if self.dialog.getControl("scope").getSelectedItemPos() == 1 else "document"
        folder = self.value("folder").strip()
        if kind == "project" and not folder:
            raise ValueError("Save the document and choose its project folder first.")
        from pathlib import Path

        self.target = ScopeTarget(
            self.app, self.document, kind, Path(folder) / PROJECT_FILE if kind == "project" else None
        )
        self.fill()

    def save(self):
        from .scopes import validate_scope

        self.ensure_loaded()
        data = dict(self.data)
        data["rules"] = Settings.parse_rules(self.value("rules"))
        for key in ("profile", "dialect"):
            value = self.value(key).strip()
            if value == "inherit":
                data.pop(key, None)
            else:
                data[key] = value
        value = self.value("limit").strip()
        if value:
            data["sentence_limit"] = int(value)
        else:
            data.pop("sentence_limit", None)
        validate_scope(data)
        if "profile" in data and data["profile"] not in self.app.store.read()["profiles"]:
            raise ValueError("Choose an existing personal profile.")

        def change(current):
            if fingerprint(current) != self.loaded_revision:
                raise ValueError("Settings changed in another window. Load this scope again.")
            current.clear()
            current.update(data)

        self.target.update(change)
        self.fill()
        self.status(
            "Project settings saved."
            if self.target.path
            else "Document settings updated. Save the document to keep them after closing."
        )

    def reset(self):
        self.model.getByName("profile").Text = "inherit"
        self.model.getByName("dialect").Text = "inherit"
        self.model.getByName("limit").Text = ""
        self.model.getByName("rules").Text = ""
        self.status(
            "Profile, dialect and rule overrides cleared in this form. Save to apply; personal words remain."
        )

    def vocabulary(self):
        self.ensure_loaded()
        Vocabulary(self.app, self.document, self.target.kind, self.target.path).show()

    def ensure_loaded(self):
        selected = "project" if self.dialog.getControl("scope").getSelectedItemPos() == 1 else "document"
        if selected != self.target.kind:
            raise ValueError("Load the selected scope before editing it.")
        if selected == "project":
            from pathlib import Path

            if (Path(self.value("folder")) / PROJECT_FILE).resolve() != self.target.path:
                raise ValueError("The project folder changed. Load the selected scope first.")

    def browse_rules(self):
        self.ensure_loaded()
        RuleBrowser(self.app, self.document, 3 if self.target.path else 2).show()


class Vocabulary(Window):
    """Dedicated list controls; no JSON or delimiter syntax required."""

    def __init__(self, app, document=None, kind="global", project=None):
        super().__init__(app, "LibreHarp - words and terminology", 430, 290)
        self.target = ScopeTarget(app, document, kind, project) if kind != "global" else None
        self.add(
            "context",
            "FixedText",
            8,
            6,
            414,
            24,
            Label="Editing "
            + (
                str(self.target.path)
                if self.target and self.target.path
                else "this document"
                if self.target
                else "personal vocabulary"
            )
            + (
                ". Save the document to keep its changes."
                if self.target and self.target.kind == "document"
                else ". Changes save immediately."
            ),
        )
        self.add("words_label", "FixedText", 8, 34, 200, 12, Label="Remembered words (case-sensitive)")
        self.add("terms_label", "FixedText", 220, 34, 202, 12, Label="Preferred terminology")
        self.add("words", "ListBox", 8, 49, 200, 125, Dropdown=False)
        self.add("terms", "ListBox", 220, 49, 202, 125, Dropdown=False)
        self.add("word", "Edit", 8, 181, 200, 15)
        self.add("find_label", "FixedText", 220, 183, 48, 12, Label="Find")
        self.add("replace_label", "FixedText", 220, 204, 48, 12, Label="Replace")
        self.add("find", "Edit", 270, 181, 152, 15, HelpText="Text to find")
        self.add("replacement", "Edit", 270, 202, 152, 15, HelpText="Preferred replacement")
        self.button("add_word", "Add word", 8, 202, 96, self.add_word)
        self.button("remove_word", "Remove word", 110, 202, 98, self.remove_word)
        self.button("add_term", "Add or update", 220, 222, 100, self.add_term)
        self.button("remove_term", "Remove term", 326, 222, 96, self.remove_term)
        self.button("close", "Close", 8, 246, 96, self.close)
        self.add(
            "status",
            "FixedText",
            112,
            247,
            310,
            35,
            Label="Use the two terminology fields for text to find and its replacement.",
        )
        self.refresh()

    def read(self):
        return self.target.read() if self.target else self.app.store.read()

    def update(self, change):
        if self.target:
            self.target.update(change)
        else:
            self.app.store.update(change)
            self.app.changed()
        self.refresh()
        self.status("Saved in the selected scope. Inherited entries are edited in their original scope.")

    def refresh(self):
        data = self.read()
        self.words = data.get("words", [])
        self.terms = data.get("terms", [])
        self.model.getByName("words").StringItemList = tuple(self.words)
        self.model.getByName("terms").StringItemList = tuple(
            t["find"] + " → " + t["replace"] for t in self.terms
        )

    def add_word(self):
        word = self.model.getByName("word").Text.strip()
        if not word or "\n" in word:
            raise ValueError("Enter one nonempty word or identifier.")
        self.update(lambda d: d.update(words=sorted(set(d.get("words", [])) | {word})))

    def remove_word(self):
        index = self.dialog.getControl("words").getSelectedItemPos()
        if index < 0:
            raise ValueError("Select a remembered word.")
        word = self.words[index]
        self.update(lambda d: d.update(words=[w for w in d.get("words", []) if w != word]))

    def add_term(self):
        find = self.model.getByName("find").Text.strip()
        replacement = self.model.getByName("replacement").Text
        if not find:
            raise ValueError("Enter terminology text to find.")

        def change(data):
            terms = [t for t in data.get("terms", []) if t["find"] != find]
            terms.append({"find": find, "replace": replacement})
            data["terms"] = terms

        self.update(change)

    def remove_term(self):
        index = self.dialog.getControl("terms").getSelectedItemPos()
        if index < 0:
            raise ValueError("Select a terminology rule.")
        find = self.terms[index]["find"]
        self.update(lambda d: d.update(terms=[t for t in d.get("terms", []) if t["find"] != find]))
