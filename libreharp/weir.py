"""Persist and run personal Weir rules using the matching Harper library."""

import atexit
import json
import queue
import re
import subprocess
import threading
from pathlib import Path

RULE_PREFIX = "LibreHarp.Weir."
MAX_SOURCE_BYTES = 32_000
MAX_RULES = 64
EXAMPLE = """expr main [(very unique), (extremely unique)]

let description "Use unique on its own."
let message "Consider using unique without an intensifier."
let becomes "unique"

test "This is very unique." "This is unique."
test "This is extremely unique." "This is unique."
"""


def validate_rule(name, source):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,47}", name):
        raise ValueError(
            "Use a rule name of up to 48 letters, digits, or underscores, starting with a letter."
        )
    if not isinstance(source, str) or not source.strip() or len(source.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Enter a nonempty Weir rule of up to 32 KB.")


def validate_rules(rules):
    if not isinstance(rules, dict) or len(rules) > MAX_RULES:
        raise ValueError(f"Store up to {MAX_RULES} personal Weir rules.")
    for name, rule in rules.items():
        if not isinstance(rule, dict):
            raise ValueError("A Weir rule needs source and a description.")
        validate_rule(name, rule.get("source"))
        description = rule.get("description")
        if not isinstance(description, str) or len(description) > MAX_SOURCE_BYTES:
            raise ValueError("Invalid Weir rule description.")


class WeirError(ValueError):
    pass


class WeirEngine:
    def __init__(self, binary):
        self.binary = Path(binary)
        self.lock = threading.RLock()
        self.process = None
        self.configuration = None
        atexit.register(self.close)

    def close(self):
        with self.lock:
            self.configuration = None
            process, self.process = self.process, None
            if process is None:
                return
            if process.poll() is None:
                process.kill()
            process.wait(timeout=3)
            process.stdin.close()
            process.stdout.close()

    @staticmethod
    def _read(process, replies):
        try:
            while line := process.stdout.readline(16_000_001):
                if len(line) > 16_000_000:
                    raise WeirError("Weir returned too many findings for one text run.")
                replies.put(json.loads(line))
        except (ValueError, OSError):
            pass
        finally:
            replies.put(None)

    def _start(self):
        if self.process is not None and self.process.poll() is None:
            return
        self.close()
        if not self.binary.is_file():
            raise WeirError("The Weir checker is missing from this LibreHarp installation.")
        if not self.binary.stat().st_mode & 0o100:
            self.binary.chmod(self.binary.stat().st_mode | 0o100)
        self.process = subprocess.Popen(
            [str(self.binary)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        self.replies = queue.Queue()
        threading.Thread(target=self._read, args=(self.process, self.replies), daemon=True).start()

    def _request(self, method, **params):
        try:
            self.process.stdin.write(
                json.dumps({"method": method, **params}, ensure_ascii=False).encode() + b"\n"
            )
            self.process.stdin.flush()
            response = self.replies.get(timeout=10)
        except (OSError, queue.Empty) as exc:
            self.close()
            raise WeirError("The Weir checker stopped or timed out.") from exc
        if response is None:
            self.close()
            raise WeirError("The Weir checker stopped before returning a result.")
        if "error" in response:
            raise WeirError(response["error"])
        return response["result"]

    def validate(self, name, source):
        validate_rule(name, source)
        with self.lock:
            self._start()
            return self._request("validate", source=source)

    def check(self, text, rules, words, isolate_english):
        if not rules:
            return []
        with self.lock:
            self._start()
            config = (dict(rules), tuple(words))
            if self.configuration != config:
                self._request("configure", rules=config[0], words=config[1])
                self.configuration = config
            issues = self._request("check", text=text, isolate_english=isolate_english)
            return [
                issue
                for issue in issues
                if issue["rule"] in rules
                and 0 <= issue["start"] < issue["end"] <= len(text)
                and text[issue["start"] : issue["end"]] == issue["text"]
            ]
