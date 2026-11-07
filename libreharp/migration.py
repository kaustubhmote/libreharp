"""Explicit, conservative migration from LibreHarper/WriterAgent preferences."""

import json

from .catalog import load_catalog
from .vocabulary import load_word_list

LEGACY_PROPERTY = "WriterAgentGrammarCache"


def legacy_rules(raw):
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("ignored_rules", []), list):
        raise ValueError("Invalid legacy grammar metadata.")
    known = {r["name"] for r in load_catalog()}
    rules = []
    skipped = []
    for item in data.get("ignored_rules", []):
        if not isinstance(item, str):
            raise ValueError("Legacy rule identifiers must be text.")
        explicit = item.startswith("harper||")
        name = item.removeprefix("harper||")
        if name in known and (explicit or data.get("model") == "harper"):
            rules.append(name)
        else:
            skipped.append(item)
    return sorted(set(rules)), skipped


def word_list(path):
    return load_word_list(path)
