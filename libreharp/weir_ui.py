"""Edit and test personal Harper Weir rules in Writer."""

from pathlib import Path

from .scope_ui import pick_file
from .uno_app import Window
from .weir import EXAMPLE, MAX_SOURCE_BYTES, validate_rule


class WeirRules(Window):
    def __init__(self, browser):
        super().__init__(browser.app, "LibreHarp — Weir rules", 460, 350)
        self.browser = browser
        self.add("saved", "ListBox", 8, 8, 320, 16, Dropdown=True, HelpText="Saved Weir rules")
        self.button("load", "Load", 336, 8, 116, self.load)
        self.add("name_label", "FixedText", 8, 34, 84, 14, Label="Rule name")
        self.add("rule_name", "Edit", 94, 32, 234, 16, HelpText="Weir rule name")
        self.button("example", "Load example", 336, 32, 116, self.example)
        self.add(
            "source",
            "Edit",
            8,
            54,
            444,
            170,
            MultiLine=True,
            VScroll=True,
            HelpText="Weir source code, including optional tests",
        )
        self.button("import", "Open .weir file…", 8, 232, 115, self.import_file)
        self.button("test", "Validate and test", 131, 232, 125, self.test)
        self.button("save", "Save rule", 264, 232, 92, self.save)
        self.button("remove", "Delete rule", 364, 232, 88, self.remove)
        self.button("close", "Close", 360, 257, 92, self.close)
        self.add(
            "status",
            "FixedText",
            8,
            280,
            444,
            60,
            Label="Load a saved rule, open a .weir file, or try the example. Saving enables the rule for your personal profiles unless a rule override disables it.",
        )
        self.refresh()

    def refresh(self, name=""):
        items = tuple(sorted(self.app.store.read().get("weir", {})))
        model = self.model.getByName("saved")
        model.StringItemList = items
        model.SelectedItems = (items.index(name),) if name in items else ()
        self.model.getByName("load").Enabled = bool(items)
        if not self.browser.closed:
            self.browser.refresh()

    def editor(self):
        return self.model.getByName("rule_name").Text.strip(), self.model.getByName("source").Text

    def fill(self, name, source):
        self.model.getByName("rule_name").Text = name
        self.model.getByName("source").Text = source

    def load(self):
        name = self.dialog.getControl("saved").getSelectedItem()
        rule = self.app.store.read().get("weir", {}).get(name)
        if rule is None:
            raise ValueError("Choose a saved Weir rule.")
        self.fill(name, rule["source"])
        self.status(f"Loaded {name}.")

    def example(self):
        self.fill("UniqueWithoutIntensifier", EXAMPLE)
        self.status("Choose Validate and test to run the two examples before saving.")

    def import_file(self):
        path = pick_file(self.ctx, title="Open a Weir rule", pattern="*.weir")
        if path:
            path = Path(path)
            with path.open("rb") as stream:
                data = stream.read(MAX_SOURCE_BYTES + 1)
            if len(data) > MAX_SOURCE_BYTES:
                raise ValueError("The Weir rule exceeds 32 KB.")
            source = data.decode("utf-8-sig")
            self.fill(path.stem, source)
            self.status("Rule opened for editing. Choose Validate and test before saving.")

    def test(self):
        name, source = self.editor()
        result = self.app.weir.validate(name, source)
        if result["failures"]:
            failure = result["failures"][0]
            raise ValueError(
                f"{len(result['failures'])} of {result['tests']} tests failed.\n"
                f"Expected: {failure['expected']}\nGot: {failure['got']}"
            )
        self.status(f"Weir syntax is valid. {result['tests']} embedded tests passed.")
        return result

    def save(self):
        name, source = self.editor()
        result = self.test()
        entry = {"source": source, "description": result["description"]}
        self.app.store.update(lambda data: data.setdefault("weir", {}).update({name: entry}))
        self.app.changed()
        self.refresh(name)
        self.status(f"Saved {name}. Use the grammar rule browser to change where it applies.")

    def remove(self):
        name, source = self.editor()
        validate_rule(name, source)

        def change(data):
            rules = data.get("weir", {})
            if name not in rules:
                raise ValueError("Load the saved rule you want to delete first.")
            del rules[name]

        self.app.store.update(change)
        self.app.changed()
        self.fill("", "")
        self.refresh()
        self.status(f"Deleted {name}.")
