"""Verify exclusive English checking, persistence, scope isolation, and restoration."""

import copy
import json
import time
import traceback

import test_libreoffice as test
import uno
from test_scopes_libreoffice import wait_for

from libreharp.english_checking import COUNTRIES, GRAMMAR, SPELL, configure, locale, snapshot
from libreharp.scopes import ScopeTarget
from libreharp.store import DEFAULTS, Store
from libreharp.uno_app import PROOFREADER, Runtime


def dispatch(document, command):
    url = uno.createUnoStruct("com.sun.star.util.URL")
    url.Complete, url.Protocol, url.Path = "org.libreharp:" + command, "org.libreharp:", command
    frame = document.CurrentController.Frame
    handler = frame.queryDispatch(url, "_self", 0)
    assert handler is not None
    handler.dispatch(url, ())


def main():
    ctx = test.start()
    store = Store(test.PROFILE / "user/LibreHarp")
    store.update(lambda data: (data.clear(), data.update(copy.deepcopy(DEFAULTS))))
    backup = store.directory / "previous-english-checkers.json"
    doc = test.desktop.loadComponentFromURL(
        "private:factory/swriter", "_blank", 0, (test.prop("Hidden", True),)
    )
    if backup.exists():
        dispatch(doc, "restore-english")
        assert wait_for(lambda: not backup.exists())
    before = snapshot(ctx)
    manager = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.LinguServiceManager", ctx
    )
    untouched = [uno.createUnoStruct("com.sun.star.lang.Locale", "fr", "FR", ""), locale("NZ")]
    others = [
        [tuple(manager.getConfiguredServices(kind, language)) for kind in (SPELL, GRAMMAR)]
        for language in untouched
    ]
    dispatch(doc, "english")
    assert wait_for(lambda: backup.exists())
    active = snapshot(ctx)
    test.record(
        "Installed action selects LibreHarp and disables duplicate spelling for all supported dialects",
        all(active["services"][country] == {SPELL: [], GRAMMAR: [PROOFREADER]} for country in COUNTRIES),
    )
    test.record(
        "English takeover enables automatic spelling and grammar feedback",
        active["spell_auto"] and active["grammar_auto"],
    )
    test.record(
        "Previous providers and automatic-check choices are saved", json.loads(backup.read_text()) == before
    )
    test.record(
        "Other languages and unsupported English dialects retain their providers",
        others
        == [
            [tuple(manager.getConfiguredServices(kind, language)) for kind in (SPELL, GRAMMAR)]
            for language in untouched
        ],
    )
    saved = backup.read_bytes()
    dispatch(doc, "english")
    time.sleep(0.1)
    test.record("Repeating takeover preserves the original restore point", backup.read_bytes() == saved)
    app = Runtime(ctx)
    backup.write_text('{"schema": 1}')
    try:
        configure(app, restore=True)
        raise AssertionError("Invalid restore point was accepted")
    except ValueError:
        test.record(
            "Invalid restore data preserves current checker choices",
            snapshot(ctx) == active and backup.read_text() == '{"schema": 1}',
        )
    finally:
        backup.write_bytes(saved)
        app.engine.close()
    doc.close(True)
    test.stop()
    ctx = test.start()
    test.record("Exclusive English checking survives LibreOffice restart", snapshot(ctx) == active)
    text = "The Qzxexclusiveprobe works. This is a example."
    a, aid = test.bound_document(ctx, locale("US"), text)
    b, bid = test.bound_document(ctx, locale("US"), text)
    proofreader = ctx.ServiceManager.createInstanceWithContext(PROOFREADER, ctx)

    def errors(identity):
        return proofreader.doProofreading(identity, text, locale("US"), 0, len(text), ()).aErrors

    result = errors(aid)
    test.record(
        "LibreHarp still reports both spelling and grammar with native English spelling disabled",
        {"SpellCheck", "AnA"}.issubset({e.aRuleIdentifier for e in result}),
    )
    app = Runtime(ctx)
    ScopeTarget(app, a).update(lambda data: data.update(words=["Qzxexclusiveprobe"]))
    test.record(
        "Document acceptance removes its LibreHarp spelling finding",
        wait_for(lambda: not any(e.aRuleIdentifier == "SpellCheck" for e in errors(aid))),
    )
    test.record(
        "Document acceptance leaves the identical sibling flagged",
        any(e.aRuleIdentifier == "SpellCheck" for e in errors(bid)),
    )
    test.record(
        "No native English provider remains to add a duplicate underline",
        not snapshot(ctx)["services"]["US"][SPELL],
    )
    dispatch(a, "restore-english")
    test.record(
        "Restore action recovers the exact previous configuration",
        wait_for(lambda: snapshot(ctx) == before) and not backup.exists(),
    )
    app.engine.close()
    a.close(True)
    b.close(True)
    test.stop()
    ctx = test.start()
    test.record("Restored providers survive LibreOffice restart", snapshot(ctx) == before)


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Exception:
        code = 1
        test.REPORT["errors"].append(traceback.format_exc())
        traceback.print_exc()
    finally:
        test.stop()
        test.REPORT["passed"] = code == 0
        (test.ZONE / "english-checking-report.json").write_text(json.dumps(test.REPORT, indent=2))
    raise SystemExit(code)
