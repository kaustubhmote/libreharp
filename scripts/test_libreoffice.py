"""Install and exercise the actual OXT in a disposable LibreOffice user profile.

Run with Python that can import UNO. Results and the test profile live under
LIBREHARP_TEST_ZONE or test-zone by default.
"""

import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import uno

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from libreharp import __version__
from libreharp.store import Store
from libreharp.uno_app import (
    PROOFREADER,
    Review,
    RuleBrowser,
    Runtime,
    Settings,
    apply_replacement,
    paragraphs,
)


def program_directory():
    if program := os.environ.get("LIBREHARP_LO_PROGRAM"):
        return Path(program).resolve()
    bundled = Path(sys.executable).resolve().parent
    if (bundled / "soffice").is_file():
        return bundled
    if launcher := shutil.which("soffice"):
        return Path(launcher).resolve().parent
    raise RuntimeError("Set LIBREHARP_LO_PROGRAM to the directory containing soffice and unopkg.")


PROGRAM = program_directory()
LAUNCHER = os.environ.get("LIBREHARP_LO_LAUNCHER", str(PROGRAM / "soffice"))
PACKAGE = Path(os.environ.get("LIBREHARP_TEST_PACKAGE", ROOT / "build" / f"LibreHarp_v{__version__}.oxt"))
ZONE = Path(os.environ.get("LIBREHARP_TEST_ZONE", ROOT / "test-zone")).resolve()
PROFILE = ZONE / "profile"
REPORT = {"libreoffice_program": str(PROGRAM), "checks": [], "errors": []}
process = None
desktop = None


def record(name, value=True):
    assert value, name
    REPORT["checks"].append(name)
    print("PASS", name, flush=True)


def prop(name, value):
    result = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    result.Name, result.Value = name, value
    return result


def profile_argument():
    if PROFILE.is_symlink() or (PROFILE / "user").is_symlink():
        raise RuntimeError("Choose a test directory with a separate LibreOffice profile.")
    return "-env:UserInstallation=" + PROFILE.as_uri()


def configuration(ctx, path, *, write=False):
    provider = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", ctx
    )
    kind = "ConfigurationUpdateAccess" if write else "ConfigurationAccess"
    return provider.createInstanceWithArguments(
        "com.sun.star.configuration." + kind, (prop("nodepath", path),)
    )


def skip_startup_prompts(ctx):
    misc = configuration(ctx, "/org.openoffice.Office.Common/Misc", write=True)
    misc.setPropertyValue("ShowTipOfTheDay", False)
    misc.commitChanges()
    product = configuration(ctx, "/org.openoffice.Setup/Product", write=True)
    product.setPropertyValue("WhatsNew", False)
    product.commitChanges()


def about_command(ctx):
    menus = configuration(ctx, "/org.openoffice.Office.Addons/AddonUI/OfficeMenuBar")
    about = menus.getByName("org.libreharp.Menu").getByName("Submenu").getByName("about")
    return about.getByName("URL")


def about_shows_version(ctx):
    toolkit = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)
    return any(
        toolkit.getTopWindow(i).getProperty("Text") == f"About LibreHarp {__version__}"
        for i in range(toolkit.getTopWindowCount())
    )


def start(visible=False):
    global process, desktop
    pipe = "libreharp_test_" + str(os.getpid())
    options = [] if visible else ["--headless"]
    command = [
        LAUNCHER,
        profile_argument(),
        *options,
        "--norestore",
        "--nodefault",
        "--nofirststartwizard",
        "--accept=pipe,name=" + pipe + ";urp;StarOffice.ServiceManager",
    ]
    ZONE.mkdir(parents=True, exist_ok=True)
    log = ZONE / "office.log"

    def launch():
        with log.open("ab") as output:
            return subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT)

    process = launch()
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
    deadline = time.monotonic() + 30
    restarted = False
    while True:
        try:
            ctx = resolver.resolve("uno:pipe,name=" + pipe + ";urp;StarOffice.ComponentContext")
            break
        except Exception as exc:
            status = process.poll()
            if status == 81 and not restarted:
                # AppRun can launch soffice.bin directly. It does not handle the
                # restart LibreOffice requests after initializing a fresh profile.
                restarted = True
                process = launch()
            elif status is not None:
                raise RuntimeError(f"LibreOffice exited with code {status}. See {log}.") from exc
            if time.monotonic() > deadline:
                raise RuntimeError(f"Could not connect to isolated LibreOffice. See {log}.") from exc
            time.sleep(0.2)
    paths = ctx.ServiceManager.createInstanceWithContext("com.sun.star.util.PathSubstitution", ctx)
    actual = Path(uno.fileUrlToSystemPath(paths.substituteVariables("$(user)", True))).resolve()
    if actual != PROFILE / "user":
        raise RuntimeError(f"LibreOffice used {actual} instead of the test profile.")
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    if visible:
        skip_startup_prompts(ctx)
    return ctx


def stop():
    global process, desktop
    if desktop:
        try:
            desktop.terminate()
        except Exception:
            pass
        desktop = None
    if process:
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        process = None


def bound_document(ctx, locale, text):
    document = desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, (prop("Hidden", True),))
    document.Text.String = text
    document.CharLocale = locale
    iterator = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.ProofreadingIterator", ctx
    )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        flat = document.getFlatParagraphIterator(2, False).getFirstPara()
        result = iterator.checkSentenceAtPosition(document, flat, text, locale, 0, len(text), 0)
        if any(p.Name == "LibreHarp.ScopeReady" and p.Value for p in result.aProperties):
            return document, result.aDocumentIdentifier
        time.sleep(0.1)
    raise AssertionError("Writer document was not bound to its proofreading ID")


def main():
    ZONE.mkdir(exist_ok=True)
    error_log = PROFILE / "user/LibreHarp/errors.log"
    previous_errors = error_log.read_text() if error_log.exists() else ""
    # Retain the profile between runs to exercise extension replacement and upgrades.
    result = subprocess.run(
        [
            str(PROGRAM / "unopkg"),
            "add",
            "--force",
            "--suppress-license",
            profile_argument(),
            str(PACKAGE),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    (ZONE / "install.log").write_text(result.stdout + result.stderr)
    record("OXT installs in isolated profile", result.returncode == 0)
    ctx = start()
    # Persist the setting before a later visible launch initializes its welcome dialog.
    skip_startup_prompts(ctx)
    smgr = ctx.ServiceManager
    checker = smgr.createInstanceWithContext(PROOFREADER, ctx)
    record("Installed Python UNO proofreader loads", checker is not None)
    locale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    linguistic = smgr.createInstanceWithContext("com.sun.star.linguistic2.LinguServiceManager", ctx)
    available = linguistic.getAvailableServices("com.sun.star.linguistic2.Proofreader", locale)
    record("LibreHarp advertised as English grammar service", PROOFREADER in available)
    linguistic.setConfiguredServices("com.sun.star.linguistic2.Proofreader", locale, (PROOFREADER,))
    record(
        "LibreHarp selected in isolated Writing Aids",
        linguistic.getConfiguredServices("com.sun.star.linguistic2.Proofreader", locale) == (PROOFREADER,),
    )
    store = Store(PROFILE / "user/LibreHarp")
    # Reset only this test profile's app preferences to make the test repeatable.
    import copy

    from libreharp.store import DEFAULTS

    store.update(lambda d: (d.clear(), d.update(copy.deepcopy(DEFAULTS))))
    text = "This is a example. This is is incorrect."
    doc, identity = bound_document(ctx, locale, text)
    result = checker.doProofreading(identity, text, locale, 0, len(text), ())
    record("Installed proofreader returns real Harper findings", len(result.aErrors) >= 2)
    issue = next(e for e in result.aErrors if "an" in e.aSuggestions)
    rule = issue.aRuleIdentifier
    record(
        "Installed suggestions include a -> an",
        text[issue.nErrorStart : issue.nErrorStart + issue.nErrorLength] == "a",
    )
    store.set_rule(rule, False)
    result = checker.doProofreading(identity, text, locale, 0, len(text), ())
    record(
        "Saved rule override invalidates installed checker cache",
        not any(e.aRuleIdentifier == rule for e in result.aErrors),
    )
    checker.resetIgnoreRules()
    result = checker.doProofreading(identity, text, locale, 0, len(text), ())
    record(
        "Native reset does not erase permanent suppression",
        not any(e.aRuleIdentifier == rule for e in result.aErrors),
    )
    doc.close(True)
    stop()
    ctx = start()
    checker = ctx.ServiceManager.createInstanceWithContext(PROOFREADER, ctx)
    doc, identity = bound_document(ctx, locale, text)
    result = checker.doProofreading(identity, text, locale, 0, len(text), ())
    record(
        "Permanent suppression survives LibreOffice process restart",
        not any(e.aRuleIdentifier == rule for e in result.aErrors),
    )
    store.set_rule(rule, True)
    iterator = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.linguistic2.ProofreadingIterator", ctx
    )
    flat = doc.getFlatParagraphIterator(2, False).getFirstPara()
    native_result = iterator.checkSentenceAtPosition(doc, flat, text, locale, 0, len(text), 8)
    record(
        "Writer proofreading pipeline invokes installed LibreHarp",
        any(e.aRuleIdentifier == rule for e in native_result.aErrors),
    )
    iterator.startProofreading(doc, doc)
    app = Runtime(ctx)
    settings = Settings(app)
    settings.show()
    settings.model.getByName("global").Text = "LongSentences=false"
    settings.model.getByName("words").Text = "Qzxnmrspectroprobe"
    settings.model.getByName("terms").Text = "utilize => use"
    settings.save()
    record(
        "Native Settings controls save rules, words and terminology",
        store.read()["rules"].get("LongSentences") is False and "Qzxnmrspectroprobe" in store.read()["words"],
    )
    settings.close()
    rules = RuleBrowser(app)
    rules.show()
    rules.model.getByName("search").Text = "LongSentences"
    rules.refresh()
    record(
        "Native rule browser searches the bundled catalog",
        len(rules.visible_rules) == 1 and rules.selected()["name"] == "LongSentences",
    )
    rules.set(True)
    record("Rule browser persists enabling a rule", store.effective()["rules"]["LongSentences"] is True)
    rules.set(False)
    record("Rule browser persists disabling a rule", store.effective()["rules"]["LongSentences"] is False)
    rules.close()
    review = Review(app, doc)
    review.show()
    review.check()
    deadline = time.monotonic() + 20
    while review.pending and time.monotonic() < deadline:
        time.sleep(0.05)
    record("Native review window completes background check", not review.pending and len(review.rows) >= 2)
    before = doc.Text.String
    bold = doc.Text.createTextCursor()
    bold.goRight(4, True)
    bold.CharWeight = 150.0
    paragraph, original, finding = next(row for row in review.rows if "an" in row[2]["suggestions"])
    apply_replacement(doc, paragraph, original, finding, "an")
    record(
        "Suggestion changes only selected text", doc.Text.String == before.replace("a example", "an example")
    )
    bold = doc.Text.createTextCursor()
    bold.goRight(4, True)
    record("Replacement preserves formatting outside its range", bold.CharWeight == 150.0)
    doc.getUndoManager().undo()
    record("Suggestion is undoable", doc.Text.String == before)
    doc.Text.String = before + " Changed."
    try:
        apply_replacement(doc, paragraph, original, finding, "an")
        raise AssertionError("Stale replacement was accepted")
    except ValueError:
        record("Changed paragraph refuses stale replacement")
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if review.rows and all(row[1] == doc.Text.String for row in review.rows) and not review.pending:
            break
        time.sleep(0.1)
    record(
        "Review automatically refreshes after document edits",
        bool(review.rows) and all(row[1] == doc.Text.String for row in review.rows),
    )
    review.close()
    # Exercise UTF-16 positions through the installed component, not only helper code.
    emoji_text = "😀 This is a example."
    result = checker.doProofreading(identity, emoji_text, locale, 0, 30, ())
    error = next(e for e in result.aErrors if e.aRuleIdentifier == "AnA")
    record("Installed Unicode code action includes the correct replacement", "an" in error.aSuggestions)
    record(
        "Installed proofreader returns correct UTF-16 offsets",
        error.nErrorStart == len(emoji_text[: emoji_text.index("a example")].encode("utf-16-le")) // 2,
    )
    doc.Text.String = emoji_text
    para = next(paragraphs(doc))
    start_index = emoji_text.index("a example")
    apply_replacement(
        doc, para, emoji_text, {"start": start_index, "end": start_index + 1, "text": "a"}, "an"
    )
    record("Non-BMP text replacement preserves surrounding text", doc.Text.String == "😀 This is an example.")
    table = doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(1, 2)
    end = doc.Text.createTextCursor()
    end.gotoEnd(False)
    doc.Text.insertTextContent(end, table, False)
    table.getCellByName("A1").String = "This is a example."
    table.getCellByName("B1").String = "Keep this cell unchanged."
    table_paragraph = next(p for p in paragraphs(doc) if p.String == "This is a example.")
    record("Review traversal reaches table paragraphs", table_paragraph is not None)
    apply_replacement(doc, table_paragraph, "This is a example.", {"start": 8, "end": 9, "text": "a"}, "an")
    record(
        "Table replacement changes only its target cell",
        table.getCellByName("A1").String == "This is an example."
        and table.getCellByName("B1").String == "Keep this cell unchanged.",
    )
    doc.getUndoManager().undo()
    record("Table replacement supports Undo", table.getCellByName("A1").String == "This is a example.")
    # Test actual registered menu protocol dispatch in the installed OXT.
    frame = doc.CurrentController.Frame
    url = uno.createUnoStruct("com.sun.star.util.URL")
    url.Complete, url.Protocol, url.Path = "org.libreharp:settings", "org.libreharp:", "settings"
    dispatch = frame.queryDispatch(url, "_self", 0)
    record("Installed menu protocol resolves", dispatch is not None)
    dispatch.dispatch(url, ())
    time.sleep(0.5)
    record("Installed Writer menu registers About", about_command(ctx) == "org.libreharp:about")
    url.Complete, url.Path = "org.libreharp:about", "about"
    frame.queryDispatch(url, "_self", 0).dispatch(url, ())
    record("Installed About dialog shows the extension version", about_shows_version(ctx))
    errors = store.directory / "errors.log"
    record(
        "Installed menu dispatch has no component exceptions",
        (errors.read_text() if errors.exists() else "") == previous_errors,
    )
    # Close test dialogs/windows via the isolated desktop shutdown.
    app.engine.close()
    doc.close(True)


if __name__ == "__main__":
    code = 0
    try:
        main()
    except Exception:
        code = 1
        REPORT["errors"].append(traceback.format_exc())
        traceback.print_exc()
    finally:
        stop()
        REPORT["passed"] = code == 0
        ZONE.mkdir(exist_ok=True)
        (ZONE / "report.json").write_text(json.dumps(REPORT, indent=2))
    sys.exit(code)
