"""Personal checking options shared by Writer's three proofreading entry points."""

from fnmatch import fnmatchcase
from urllib.parse import unquote, urlsplit

MAX_BYTES = 120_000
SEVERITIES = ("Hint", "Information", "Warning", "Error")
DEFAULT_ADVANCED = {
    "delay_ms": 1000,
    "max_bytes": MAX_BYTES,
    "exclude": [],
    "isolate_english": False,
    "severity": "Hint",
    "record_statistics": False,
}


def advanced_options(values):
    if not isinstance(values, dict):
        raise ValueError("Advanced settings must be an object.")
    options = {**DEFAULT_ADVANCED, **values}
    for name, low, high, label in (
        ("delay_ms", 0, 10000, "Sidebar recheck delay"),
        ("max_bytes", 1, 2_000_000, "Maximum text size"),
    ):
        if type(options[name]) is not int or not low <= options[name] <= high:
            raise ValueError(f"{label} must be between {low:,} and {high:,}.")
    if any(type(options[name]) is not bool for name in ("isolate_english", "record_statistics")):
        raise ValueError("English isolation and statistics settings must be on or off.")
    if options["severity"] not in SEVERITIES:
        raise ValueError("Choose a diagnostic severity.")
    patterns = options["exclude"]
    if not isinstance(patterns, list) or any(
        not isinstance(pattern, str) or not pattern.strip() or "\n" in pattern for pattern in patterns
    ):
        raise ValueError("Enter one nonempty exclusion pattern per line.")
    return options


def excluded_document(url, patterns):
    if not url:
        return False
    path = unquote(urlsplit(url).path)
    name = path.rsplit("/", 1)[-1]
    return any(fnmatchcase(path if "/" in pattern else name, pattern) for pattern in patterns)
