"""Document-local exceptions for exact checked text and finding ranges."""

import hashlib
import json
import re

MAX_IGNORES = 2000
PROPERTY = "LibreHarp.IgnoredFindings"


def ignore_key(text, issue):
    parts = (text, issue["rule"], issue["start"], issue["end"])
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def validate_ignores(values):
    if not isinstance(values, dict) or len(values) > MAX_IGNORES:
        raise ValueError(f"A document can store up to {MAX_IGNORES} saved ignores.")
    if any(
        not isinstance(key, str)
        or not re.fullmatch(r"[a-f0-9]{64}", key)
        or not isinstance(label, str)
        or not 0 < len(label) <= 240
        for key, label in values.items()
    ):
        raise ValueError("Invalid saved ignore.")


def without_ignored(text, issues, overrides):
    ignored = (overrides or {}).get("ignored", {})
    if not ignored:
        return issues
    return [issue for issue in issues if ignore_key(text, issue) not in ignored]


def read_ignores(document):
    props = document.DocumentProperties.UserDefinedProperties
    if not props.PropertySetInfo.hasPropertyByName(PROPERTY):
        return {}
    try:
        values = json.loads(props.getPropertyValue(PROPERTY))
        validate_ignores(values)
        return values
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "Saved ignores could not be read. The original document metadata was preserved."
        ) from exc


def update_ignores(app, document, change):
    if document.isReadonly():
        raise ValueError("This document is read-only.")
    values = read_ignores(document)
    change(values)
    validate_ignores(values)
    props = document.DocumentProperties.UserDefinedProperties
    exists = props.PropertySetInfo.hasPropertyByName(PROPERTY)
    if values:
        value = json.dumps(values, ensure_ascii=False, sort_keys=True)
        if exists:
            props.setPropertyValue(PROPERTY, value)
        else:
            props.addProperty(PROPERTY, 128, value)  # REMOVABLE custom document property
    elif exists:
        props.removeProperty(PROPERTY)
    document.setModified(True)
    app.bindings.refresh()
    app.changed()
