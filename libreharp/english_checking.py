"""Opt-in English checking configuration for the current LibreOffice profile."""

import json
import os
import tempfile

import uno

from .uno_app import PROOFREADER, service

COUNTRIES = ("US", "GB", "AU", "CA", "IN")
SPELL = "com.sun.star.linguistic2.SpellChecker"
GRAMMAR = "com.sun.star.linguistic2.Proofreader"


def config(ctx):
    provider = service(ctx, "configuration.ConfigurationProvider")
    arg = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    arg.Name, arg.Value = "nodepath", "/org.openoffice.Office.Linguistic"
    return provider.createInstanceWithArguments(
        "com.sun.star.configuration.ConfigurationUpdateAccess", (arg,)
    )


def locale(country):
    return uno.createUnoStruct("com.sun.star.lang.Locale", "en", country, "")


def snapshot(ctx):
    manager = service(ctx, "linguistic2.LinguServiceManager")
    settings = config(ctx)
    return {
        "schema": 1,
        "services": {
            country: {
                kind: list(manager.getConfiguredServices(kind, locale(country))) for kind in (SPELL, GRAMMAR)
            }
            for country in COUNTRIES
        },
        "spell_auto": settings.getByName("SpellChecking").getPropertyValue("IsSpellAuto"),
        "grammar_auto": settings.getByName("GrammarChecking").getPropertyValue("IsAutoCheck"),
    }


def validate(data):
    try:
        valid = (
            data["schema"] == 1
            and set(data["services"]) == set(COUNTRIES)
            and type(data["spell_auto"]) is bool
            and type(data["grammar_auto"]) is bool
        )
        for entry in data["services"].values():
            valid &= set(entry) == {SPELL, GRAMMAR} and all(
                isinstance(names, list) and all(isinstance(n, str) for n in names) for names in entry.values()
            )
        if not valid:
            raise ValueError("Invalid checker configuration")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("The saved English checker configuration is invalid. No settings changed.") from exc
    return data


def apply(ctx, data):
    validate(data)
    manager = service(ctx, "linguistic2.LinguServiceManager")
    for country, entry in data["services"].items():
        for kind, names in entry.items():
            manager.setConfiguredServices(kind, locale(country), tuple(names))
    settings = config(ctx)
    settings.getByName("SpellChecking").setPropertyValue("IsSpellAuto", data["spell_auto"])
    settings.getByName("GrammarChecking").setPropertyValue("IsAutoCheck", data["grammar_auto"])
    settings.commitChanges()


def save_backup(path, data):
    handle, temporary = tempfile.mkstemp(prefix=".english-checkers-", dir=path.parent)
    try:
        with os.fdopen(handle, "w") as stream:
            json.dump(data, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(app, *, restore=False):
    """Change only supported English providers; preserve a durable restore point."""
    path = app.store.directory / "previous-english-checkers.json"
    before = snapshot(app.ctx)
    if restore:
        if not path.exists():
            raise ValueError("No previous English checker configuration has been saved.")
        try:
            target = validate(json.loads(path.read_text()))
        except (ValueError, OSError) as exc:
            raise ValueError(
                "Cannot read the saved English checker configuration. No settings changed."
            ) from exc
    else:
        manager = service(app.ctx, "linguistic2.LinguServiceManager")
        for country in COUNTRIES:
            if PROOFREADER not in manager.getAvailableServices(GRAMMAR, locale(country)):
                raise ValueError("Install and enable LibreHarp before changing English checking.")
        if path.exists():
            validate(json.loads(path.read_text()))
        else:
            save_backup(path, before)
        target = {
            "schema": 1,
            "services": {country: {SPELL: [], GRAMMAR: [PROOFREADER]} for country in COUNTRIES},
            "spell_auto": True,
            "grammar_auto": True,
        }
    try:
        apply(app.ctx, target)
        if snapshot(app.ctx) != target:
            raise ValueError("LibreOffice did not accept the English checker configuration.")
    except Exception:
        apply(app.ctx, before)
        raise
    if restore:
        path.unlink()
    app.bindings.refresh()
    app.changed()
