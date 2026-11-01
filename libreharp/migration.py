"""Explicit, conservative migration from LibreHarper/WriterAgent preferences."""

import json
from pathlib import Path

from .catalog import load_catalog

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
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Dictionary exceeds the 2 MB import limit.")
    words = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if any(any(c.isspace() for c in word) or "/" in word for word in words):
        raise ValueError("Choose a plain UTF-8 word list with one word per line, without affix flags.")
    return sorted(set(words))
