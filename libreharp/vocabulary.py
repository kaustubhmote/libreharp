"""Word-specific exceptions shared by checking, review actions, and word lists."""

WORD_RULES = frozenset({"SpellCheck", "SplitWords"})
MAX_WORD_LIST_BYTES = 2_000_000


def is_word_finding(issue):
    return issue is not None and issue["rule"] in WORD_RULES


def parse_words(text):
    """Read an exact-case plain word list before changing any saved vocabulary."""
    if len(text.encode("utf-8")) > MAX_WORD_LIST_BYTES:
        raise ValueError("Word list exceeds the 2 MB limit.")
    words = sorted({line.strip() for line in text.removeprefix("\ufeff").splitlines() if line.strip()})
    if any(any(c.isspace() for c in word) or "/" in word for word in words):
        raise ValueError("Use one word or identifier per line, without spaces or dictionary affix flags.")
    return words
