"""Original explanations and examples, verified against the pinned Harper engine."""

HELP = {
    "AnA": (
        "Choose 'a' or 'an' by the next word's sound. Use 'an' before a vowel sound, "
        "as in 'an hour', and 'a' before a consonant sound, as in 'a university'.",
        "This is a example.",
        "This is an example.",
    ),
    "RepeatedWords": (
        "A word appears twice in a row. Remove an accidental repetition. Some repetitions "
        "are intentional, so read the sentence before accepting the suggestion.",
        "This is is incorrect.",
        "This is incorrect.",
    ),
    "SentenceCapitalization": (
        "A sentence normally starts with a capital letter. Names and deliberately styled "
        "text can be exceptions. Harper skips some short, label-like sentences.",
        "this sentence starts with a lowercase letter.",
        "This sentence starts with a lowercase letter.",
    ),
    "ThenThan": (
        "Use 'than' for a comparison and 'then' for time or the next step.",
        "The new sample is colder then the old sample.",
        "The new sample is colder than the old sample.",
    ),
    "ItsContraction": (
        "Use 'it's' when you mean 'it is' or 'it has'. The possessive 'its' has no apostrophe.",
        "Its a sunny day.",
        "It's a sunny day.",
    ),
    "SpellCheck": (
        "Harper does not recognize this spelling in the selected dialect. Check the replacement, "
        "or use More actions > Remember word for a valid name or technical term. "
        "Remembered words are case-sensitive.",
        "You will recieve a confirmation email.",
        "You will receive a confirmation email.",
    ),
    "OxfordComma": (
        "This style uses a comma before the final 'and' or 'or' in a list of three or more items. "
        "Choose the convention your document requires; it is a style preference.",
        "We bought apples, oranges and bananas.",
        "We bought apples, oranges, and bananas.",
    ),
    "LongSentences": (
        "A long sentence may be hard to follow, but length alone does not make it incorrect. "
        "Consider separating distinct ideas. Disable this rule in your preferred scope if "
        "long sentences are appropriate for your writing. A custom sentence limit is available "
        "in Document / project settings.",
        "The researchers collected samples from several different locations across the region and "
        "carefully recorded the temperature and pressure at each site before returning to the "
        "laboratory where they prepared the materials for analysis and compared the results with "
        "previous experiments that had been conducted under similar conditions during the previous year.",
        "The researchers collected samples across the region and recorded conditions at each site. "
        "They returned to the laboratory to prepare the samples. They then compared their results "
        "with experiments from the previous year.",
    ),
}


def explanation(rule):
    if rule in HELP:
        why, before, after = HELP[rule]
        return f"{why}\n\nExample\nBefore: {before}\nAfter: {after}"
    if rule.startswith("LibreHarp.Term."):
        return "This phrase matches your saved terminology. The replacement follows the most specific scope."
    if rule == "LibreHarp.SentenceLength":
        return (
            "This sentence exceeds your custom word limit. Length is a style preference, not a grammar error. "
            "Change the limit in settings, or disable this rule in the selected scope."
        )
    return ""


def finding_text(original, issue, number, total):
    start, end = issue["start"], issue["end"]
    left, right = max(0, start - 140), min(len(original), end + 140)
    context = (
        ("..." if left else "")
        + original[left:start]
        + "["
        + original[start:end]
        + "]"
        + original[end:right]
        + ("..." if right < len(original) else "")
    )
    parts = [f"Finding {number} of {total}", issue["message"], "In your text\n" + context]
    help_text = explanation(issue["rule"])
    if help_text:
        parts.append(help_text)
    if not issue["suggestions"]:
        parts.append("No automatic replacement. Edit the document, ignore this finding, or disable its rule.")
    parts.append("Rule: " + issue["rule"])
    return "\n\n".join(parts)
