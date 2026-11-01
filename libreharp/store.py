"""Durable preferences. Runtime caches and document text never enter this file."""

import contextlib
import copy
import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

DEFAULTS = {
    "schema": 1,
    "profile": "General",
    "profiles": {
        "General": {"rules": {}, "dialect": "auto", "sentence_limit": 0},
        "Scientific": {"rules": {"LongSentences": False}, "dialect": "auto", "sentence_limit": 0},
    },
    "rules": {},
    "words": [],
    "terms": [],
}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "preferences.json"
        self.lock_path = self.directory / "preferences.lock"
        self.lock = threading.RLock()

    @contextlib.contextmanager
    def transaction(self):
        # A separate lock inode survives atomic replacement of the JSON file.
        import fcntl

        with self.lock, self.lock_path.open("a") as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file, fcntl.LOCK_UN)

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise ValueError("Unsupported preference format; no settings were changed.")
        if not isinstance(data.get("profiles"), dict) or data.get("profile") not in data["profiles"]:
            raise ValueError("Choose an existing profile.")
        if any(
            not isinstance(name, str) or not name.strip() or not isinstance(p, dict)
            for name, p in data["profiles"].items()
        ):
            raise ValueError("Profiles must have names and valid settings.")
        for rules in [data.get("rules"), *[p.get("rules") for p in data["profiles"].values()]]:
            if not isinstance(rules, dict) or any(
                not isinstance(k, str) or type(v) is not bool for k, v in rules.items()
            ):
                raise ValueError("Rules must map names to true or false.")
        if not isinstance(data.get("words"), list) or any(
            not isinstance(w, str) or not w.strip() or "\n" in w for w in data["words"]
        ):
            raise ValueError("Dictionary words must be nonempty single lines.")
        if not isinstance(data.get("terms"), list):
            raise ValueError("Terminology rules must be a list.")
        for term in data["terms"]:
            if (
                not isinstance(term, dict)
                or not isinstance(term.get("find"), str)
                or not term["find"].strip()
                or not isinstance(term.get("replace"), str)
                or ("message" in term and not isinstance(term["message"], str))
            ):
                raise ValueError("Each terminology rule needs find and replace text.")
        for profile in data["profiles"].values():
            if profile.get("dialect") not in (
                "auto",
                "American",
                "British",
                "Australian",
                "Canadian",
                "Indian",
            ):
                raise ValueError("Unsupported dialect.")
            limit = profile.get("sentence_limit")
            if type(limit) is not int or not 0 <= limit <= 1000:
                raise ValueError("Sentence limit must be between 0 and 1000; 0 disables it.")
        return data

    def read(self):
        with self.lock:
            if not self.path.exists():
                return copy.deepcopy(DEFAULTS)
            try:
                return self.validate(json.loads(self.path.read_text(encoding="utf-8")))
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                raise ValueError(
                    f"Preferences could not be read. Original file preserved: {self.path}. {exc}"
                ) from exc

    def _write(self, data):
        self.validate(data)
        fd, name = tempfile.mkstemp(prefix=".preferences-", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def update(self, change):
        with self.transaction():
            data = self.read()
            change(data)
            self._write(data)
            return data

    def set_rule(self, rule, enabled, scope="global"):
        def change(data):
            target = data["rules"] if scope == "global" else data["profiles"][data["profile"]]["rules"]
            target[rule] = bool(enabled)

        return self.update(change)

    def add_word(self, word):
        word = word.strip()
        return self.update(lambda data: data.update(words=sorted(set(data["words"]) | {word})))

    def export_to(self, path):
        Path(path).write_text(json.dumps(self.read(), indent=2, ensure_ascii=False), encoding="utf-8")

    def import_from(self, path):
        data = self.validate(json.loads(Path(path).read_text(encoding="utf-8")))
        with self.transaction():
            if self.path.exists():
                (self.directory / "preferences.before-import.json").write_bytes(self.path.read_bytes())
            self._write(data)

    def effective(self, overrides=None):
        data = self.read()
        name = (overrides or {}).get("profile", data["profile"])
        if name not in data["profiles"]:
            raise ValueError(
                f"Profile {name!r} is not available on this computer. Choose an existing profile."
            )
        profile = data["profiles"][name]
        result = {
            "rules": {**profile["rules"], **data["rules"]},
            "words": list(data["words"]),
            "terms": data["terms"],
            "dialect": profile["dialect"],
            "sentence_limit": profile["sentence_limit"],
        }
        if overrides:
            result["rules"].update(overrides.get("rules", {}))
            result["words"] = sorted(set(result["words"]) | set(overrides.get("words", [])))
            terms = {term["find"]: term for term in result["terms"]}
            terms.update({term["find"]: term for term in overrides.get("terms", [])})
            result["terms"] = list(terms.values())
            for key in ("dialect", "sentence_limit"):
                if key in overrides:
                    result[key] = overrides[key]
        return result
