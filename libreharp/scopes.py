"""Explicit, portable document overrides and directory project configuration."""

import copy
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from .store import Store

PROPERTY = "LibreHarp.Settings"
PROJECT_FILE = ".libreharp.json"


def empty_scope():
    return {"schema": 1, "rules": {}, "words": [], "terms": []}


def validate_scope(data):
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("Unsupported scoped settings format.")
    allowed = {"schema", "rules", "words", "terms", "profile", "dialect", "sentence_limit"}
    if set(data) - allowed:
        raise ValueError("Unrecognized scoped setting: " + ", ".join(sorted(set(data) - allowed)))
    from .store import DEFAULTS

    probe = copy.deepcopy(DEFAULTS)
    probe.update(rules=data.get("rules", {}), words=data.get("words", []), terms=data.get("terms", []))
    for key in ("dialect", "sentence_limit"):
        if key in data:
            probe["profiles"]["General"][key] = data[key]
    Store.validate(probe)
    if "profile" in data and (not isinstance(data["profile"], str) or not data["profile"].strip()):
        raise ValueError("Profile must be a nonempty name.")
    return data


def merge_scopes(*layers):
    result = empty_scope()
    terms = {}
    for layer in layers:
        if not layer:
            continue
        validate_scope(layer)
        result["rules"].update(layer.get("rules", {}))
        result["words"] = sorted(set(result["words"]) | set(layer.get("words", [])))
        terms.update({term["find"]: copy.deepcopy(term) for term in layer.get("terms", [])})
        for key in ("profile", "dialect", "sentence_limit"):
            if key in layer:
                result[key] = layer[key]
    result["terms"] = list(terms.values())
    return result


def local_path(url):
    parsed = urlparse(url)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    return Path(unquote(parsed.path)).resolve()


def project_path(url):
    path = local_path(url)
    if path is None:
        return None
    for parent in path.parents:
        candidate = parent / PROJECT_FILE
        if candidate.is_file():
            return candidate
    return None


class ProjectStore(Store):
    """Same atomic/locked writes as personal preferences, separate schema."""

    def __init__(self, path):
        super().__init__(Path(path).parent)
        self.path = Path(path)
        self.lock_path = self.path.with_suffix(".lock")

    validate = staticmethod(validate_scope)

    def read(self):
        if not self.path.exists():
            return empty_scope()
        if self.path.stat().st_size > 2_000_000:
            raise ValueError("Project settings exceed the 2 MB size limit.")
        return super().read()


def resolve(url, document):
    path = project_path(url)
    project = ProjectStore(path).read() if path else empty_scope()
    return merge_scopes(project, document), path


def read_document(document):
    props = document.DocumentProperties.UserDefinedProperties
    if not props.PropertySetInfo.hasPropertyByName(PROPERTY):
        return empty_scope()
    try:
        return validate_scope(json.loads(props.getPropertyValue(PROPERTY)))
    except (TypeError, ValueError) as exc:
        raise ValueError("Document settings are invalid; original metadata was preserved.") from exc


def write_document(document, data):
    validate_scope(data)
    if document.isReadonly():
        raise ValueError("This document is read-only.")
    props = document.DocumentProperties.UserDefinedProperties
    value = json.dumps(data, ensure_ascii=False, sort_keys=True)
    if props.PropertySetInfo.hasPropertyByName(PROPERTY):
        props.setPropertyValue(PROPERTY, value)
    else:
        props.addProperty(PROPERTY, 128, value)  # REMOVABLE custom document property
    document.setModified(True)


class ScopeTarget:
    """A fixed document and scope. Never resolves through the active window."""

    def __init__(self, app, document, kind="document", project=None):
        self.app, self.document, self.kind = app, document, kind
        if kind == "project":
            doc_path = local_path(document.URL)
            if doc_path is None:
                raise ValueError("Save this document locally before using project settings.")
            self.path = (
                Path(project).resolve()
                if project
                else project_path(document.URL) or doc_path.parent / PROJECT_FILE
            )
            if self.path.name != PROJECT_FILE or self.path.parent not in doc_path.parents:
                raise ValueError("Choose a project folder containing this document.")
        else:
            self.path = None

    def read(self):
        return ProjectStore(self.path).read() if self.path else read_document(self.document)

    def update(self, change):
        if self.path:
            current = local_path(self.document.URL)
            if current is None or self.path.parent not in current.parents:
                raise ValueError("This document moved outside the selected project. Reopen its settings.")
            saved = ProjectStore(self.path).update(change)
        else:
            saved = self.read()
            change(saved)
            write_document(self.document, saved)
        self.app.bindings.refresh()
        self.app.changed()
        return saved
