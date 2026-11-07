"""Shared checking and filtering for inline proofreading and the review panel."""

import copy
import re
import threading
from collections import OrderedDict

from .store import fingerprint
from .vocabulary import is_word_finding

DIALECTS = {"US": "American", "GB": "British", "AU": "Australian", "CA": "Canadian", "IN": "Indian"}


class Checker:
    def __init__(self, store, engine):
        self.store, self.engine = store, engine
        self.cache = OrderedDict()
        self.lock = threading.RLock()
        self.status = "Ready"

    def cached(self, text, country="US", overrides=None):
        """Read completed results without waiting for the engine on the UI thread."""
        prefs = self.store.effective(overrides)
        key = fingerprint([text, country, prefs, self.engine.version])
        if not self.lock.acquire(blocking=False):
            return None
        try:
            return copy.deepcopy(self.cache.get(key))
        finally:
            self.lock.release()

    def check(self, text, country="US", overrides=None):
        with self.lock:
            prefs = self.store.effective(overrides)
            key = fingerprint([text, country, prefs, self.engine.version])
            if key in self.cache:
                self.cache.move_to_end(key)
                self.status = f"{len(self.cache[key])} suggestions"
                return copy.deepcopy(self.cache[key])
            dialect = prefs["dialect"] if prefs["dialect"] != "auto" else DIALECTS.get(country, "American")
            rules = {k: v for k, v in prefs["rules"].items() if not k.startswith("LibreHarp.")}
            if prefs["sentence_limit"]:
                rules["LongSentences"] = False
            try:
                self.status = "Checking"
                issues = (
                    self.engine.check(text, {"dialect": dialect, "linters": rules}) if text.strip() else []
                )
                # Exact case is intentional for scientific identifiers. Dictionary choices
                # are durable app preferences and do not depend on LSP file identities.
                words = set(prefs["words"])
                issues = [
                    i
                    for i in issues
                    if prefs["rules"].get(i["rule"], True) and not (is_word_finding(i) and i["text"] in words)
                ]
                for term in prefs["terms"]:
                    rule = "LibreHarp.Term." + fingerprint(term)[:12]
                    if prefs["rules"].get(rule, True):
                        for match in re.finditer(r"(?<!\w)" + re.escape(term["find"]) + r"(?!\w)", text):
                            issues.append(
                                {
                                    "start": match.start(),
                                    "end": match.end(),
                                    "text": match.group(),
                                    "rule": rule,
                                    "message": term.get("message") or "Preferred terminology",
                                    "suggestions": [term["replace"]],
                                }
                            )
                limit = prefs["sentence_limit"]
                if limit and prefs["rules"].get("LibreHarp.SentenceLength", True):
                    for match in re.finditer(r"[^.!?]+[.!?]?", text):
                        count = len(re.findall(r"\b\w+\b", match.group()))
                        if count > limit:
                            issues.append(
                                {
                                    "start": match.start(),
                                    "end": match.end(),
                                    "text": match.group(),
                                    "rule": "LibreHarp.SentenceLength",
                                    "message": f"{count} words; profile limit is {limit}.",
                                    "suggestions": [],
                                }
                            )
                issues.sort(key=lambda i: (i["start"], i["end"], i["rule"]))
                # Starting the engine resolves its version on the first check.
                key = fingerprint([text, country, prefs, self.engine.version])
                self.cache[key] = copy.deepcopy(issues)
                while len(self.cache) > 256:
                    self.cache.popitem(last=False)
                self.status = f"{len(issues)} suggestions"
                return issues
            except Exception as exc:
                self.status = "Check failed: " + str(exc)
                raise


def replacement_is_current(original, current, issue):
    return (
        original == current
        and 0 <= issue["start"] <= issue["end"] <= len(current)
        and current[issue["start"] : issue["end"]] == issue["text"]
    )
