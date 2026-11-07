"""Shared checking and filtering for inline proofreading and the review panel."""

import copy
import re
import threading
from collections import OrderedDict

from .advanced import excluded_document
from .ignores import without_ignored
from .store import fingerprint
from .vocabulary import is_word_finding
from .weir import RULE_PREFIX, WeirError

DIALECTS = {"US": "American", "GB": "British", "AU": "Australian", "CA": "Canadian", "IN": "Indian"}


class Checker:
    def __init__(self, store, engine, weir=None, capabilities=None):
        self.store, self.engine = store, engine
        self.weir = weir
        self.capabilities = capabilities
        self.cache = OrderedDict()
        self.lock = threading.RLock()
        self.status = "Ready"

    def cached(self, text, country="US", overrides=None):
        """Read completed results without waiting for the engine on the UI thread."""
        prefs = self.store.effective(overrides)
        options = self.store.advanced()
        if self.skip_reason(text, overrides, options):
            return []
        key = fingerprint([text, country, prefs, options, self.engine.version])
        if not self.lock.acquire(blocking=False):
            return None
        try:
            entry = self.cache.get(key)
            return None if entry is None else copy.deepcopy(without_ignored(text, entry[0], overrides))
        finally:
            self.lock.release()

    def check(self, text, country="US", overrides=None, *, warnings=None):
        with self.lock:
            options = self.store.advanced()
            reason = self.skip_reason(text, overrides, options)
            if reason:
                self.status = reason
                return []
            prefs = self.store.effective(overrides)
            key = fingerprint([text, country, prefs, options, self.engine.version])
            if key in self.cache:
                self.cache.move_to_end(key)
                cached, warning = self.cache[key]
                issues = without_ignored(text, cached, overrides)
                if warning and warnings is not None:
                    warnings.add(warning)
                self.status = f"{len(issues)} suggestions"
                return copy.deepcopy(issues)
            dialect = prefs["dialect"] if prefs["dialect"] != "auto" else DIALECTS.get(country, "American")
            rules = {k: v for k, v in prefs["rules"].items() if not k.startswith("LibreHarp.")}
            try:
                self.status = "Checking"
                settings = {
                    "dialect": dialect,
                    "linters": rules,
                    "maxFileLength": options["max_bytes"],
                    "isolateEnglish": options["isolate_english"],
                    "diagnosticSeverity": options["severity"].lower(),
                }
                if self.capabilities is not None:
                    supported = self.capabilities.get("advanced_options", ())
                    settings = {
                        key: value
                        for key, value in settings.items()
                        if key in ("dialect", "linters") or key in supported
                    }
                issues = self.engine.check(text, settings) if text.strip() else []
                # Exact case is intentional for scientific identifiers. Dictionary choices
                # are durable app preferences and do not depend on LSP file identities.
                words = set(prefs["words"])
                issues = [
                    i
                    for i in issues
                    if prefs["rules"].get(i["rule"], True) and not (is_word_finding(i) and i["text"] in words)
                ]
                custom = {
                    RULE_PREFIX + name: rule["source"]
                    for name, rule in prefs["weir"].items()
                    if prefs["rules"].get(RULE_PREFIX + name, True)
                }
                weir_error = None
                if custom and text.strip():
                    if self.weir is None:
                        weir_error = "This Harper build cannot run Weir rules."
                    else:
                        try:
                            issues.extend(
                                self.weir.check(text, custom, sorted(words), options["isolate_english"])
                            )
                        except (WeirError, OSError) as exc:
                            weir_error = str(exc)
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
                if options["severity"] != "Hint":
                    for issue in issues:
                        issue["severity"] = options["severity"]
                # Starting the engine resolves its version on the first check.
                key = fingerprint([text, country, prefs, options, self.engine.version])
                self.cache[key] = (copy.deepcopy(issues), weir_error)
                while len(self.cache) > 256:
                    self.cache.popitem(last=False)
                issues = without_ignored(text, issues, overrides)
                self.status = f"{len(issues)} suggestions"
                if weir_error:
                    self.status += f" · Weir skipped: {weir_error}"
                    if warnings is not None:
                        warnings.add(weir_error)
                return issues
            except Exception as exc:
                self.status = "Check failed: " + str(exc)
                raise

    @staticmethod
    def skip_reason(text, overrides, options):
        if excluded_document((overrides or {}).get("document_url", ""), options["exclude"]):
            return "This document matches a checking exclusion."
        if len(text.encode("utf-8")) > options["max_bytes"]:
            return "This text exceeds the checking size limit."
        return ""


def replacement_is_current(original, current, issue):
    return (
        original == current
        and 0 <= issue["start"] <= issue["end"] <= len(current)
        and current[issue["start"] : issue["end"]] == issue["text"]
    )
