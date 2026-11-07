"""Word-specific exceptions shared by checking, review actions, and word lists."""

from pathlib import Path

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


def load_word_list(path):
    path = Path(path)
    with path.open("rb") as stream:
        data = stream.read(MAX_WORD_LIST_BYTES + 1)
    if len(data) > MAX_WORD_LIST_BYTES:
        raise ValueError("Dictionary exceeds the 2 MB import limit.")
    return parse_words(data.decode("utf-8-sig"))


def export_word_list(path, words):
    words = parse_words("\n".join(words))
    try:
        with Path(path).open("x", encoding="utf-8") as stream:
            stream.writelines(word + "\n" for word in words)
    except FileExistsError as exc:
        raise ValueError("A file already exists at that location. Choose a new name.") from exc
