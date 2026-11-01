"""Offline rule metadata from the exact bundled Harper release."""

import json
from pathlib import Path


def load_catalog():
    path = Path(__file__).resolve().parent.parent / "vendor/harper/default_config.json"
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
    return sorted(result, key=lambda r: (r["category"], r["label"]))
