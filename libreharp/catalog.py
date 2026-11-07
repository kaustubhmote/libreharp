"""Offline rule metadata from the exact bundled Harper release."""

import json

from .bundled import engine_directory


def load_catalog(directory=None):
    directory = directory or engine_directory()
    path = directory / "default_config.json"
    new_rules = set(json.loads((directory / "provenance.json").read_text()).get("new_rules", []))
    result = []

    def walk(node, category="", description=""):
        for setting in node["settings"]:
            if "Group" in setting:
                group = setting["Group"]
                walk(group["child"], group["label"], group.get("description", ""))
            elif "Bool" in setting:
                rule = setting["Bool"]
                result.append(
                    {
                        "name": rule["name"],
                        "label": rule.get("label", rule["name"]),
                        "default": rule["state"],
                        "category": category,
                        "description": description,
                        "alternatives": [],
                    }
                )
            elif "OneOfMany" in setting:
                group = setting["OneOfMany"]
                for name, label in zip(group["names"], group["labels"]):
                    result.append(
                        {
                            "name": name,
                            "label": label,
                            "default": group.get("name") == name,
                            "category": category,
                            "description": description,
                            "alternatives": [n for n in group["names"] if n != name],
                        }
                    )
            else:
                raise ValueError("Unrecognized Harper catalog format")

    walk(json.loads(path.read_text()))
    for rule in result:
        rule["new"] = rule["name"] in new_rules
    return sorted(result, key=lambda r: (r["category"], r["label"]))


def filter_rules(catalog, overrides, *, query="", category="", enabled=None, subset="All rules"):
    query = query.casefold().strip()
    return [
        rule
        for rule in catalog
        if (not category or rule["category"] == category)
        and (enabled is None or overrides.get(rule["name"], rule["default"]) == enabled)
        and (subset != "Overrides" or rule["name"] in overrides)
        and (subset != "New in bundled Harper" or rule["new"])
        and query in f"{rule['name']} {rule['label']} {rule['category']}".casefold()
    ]
