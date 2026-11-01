"""Exercise the installed deck through Writer and capture its test window."""

import subprocess
import time

import test_libreoffice as test
import uno

from libreharp.scope_ui import ScopedSettings, Vocabulary
from libreharp.uno_app import Runtime


def capture(window, name):
    window.show()
    time.sleep(0.5)
    xid = (
        subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--name", "^" + window.model.Title + "$"], text=True
        )
        .strip()
        .splitlines()[-1]
    )
    path = test.ZONE / (name + ".png")
    subprocess.run(["import", "-window", xid, str(path)], check=True, timeout=15)
    print(path, flush=True)


try:
    error_log = test.PROFILE / "user/LibreHarp/errors.log"
    previous_errors = error_log.read_text() if error_log.exists() else ""
    ctx = test.start(visible=True)
    doc = test.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    doc.Text.String = (
        "This is a example. This is is incorrect.\nWe utilize Qzxnmrspectroprobe to analyse the samples."
    )
    doc.CharLocale = uno.createUnoStruct("com.sun.star.lang.Locale", "en", "US", "")
    doc.storeAsURL(
        (test.ZONE / "LibreHarp-sidebar-test.odt").as_uri(),
        (test.prop("FilterName", "writer8"), test.prop("Overwrite", True)),
    )
    frame = doc.CurrentController.Frame
    frame.ContainerWindow.setPosSize(20, 20, 1280, 920, 15)
    test_xid = (
        subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--name", "LibreHarp-sidebar-test.odt"], text=True
        )
        .strip()
        .splitlines()[-1]
    )
    subprocess.run(["xdotool", "windowactivate", "--sync", test_xid], check=True)
    time.sleep(0.2)
    url = uno.createUnoStruct("com.sun.star.util.URL")
    url.Complete, url.Protocol, url.Path = "org.libreharp:sidebar", "org.libreharp:", "sidebar"
    dispatch = frame.queryDispatch(url, "_self", 0)
    dispatch.dispatch(url, ())
    time.sleep(3)
    print("decks", doc.CurrentController.Sidebar.Decks.getElementNames(), flush=True)
    assert doc.CurrentController.Sidebar.Decks.hasByName("LibreHarpDeck")
    assert doc.CurrentController.Sidebar.Decks.getByName("LibreHarpDeck").isActive(), (
        "LibreHarp deck was not activated by its menu action"
    )
    assert (error_log.read_text() if error_log.exists() else "") == previous_errors, (
        "Sidebar opening logged an exception"
    )
    xid = (
        subprocess.check_output(
            ["xdotool", "search", "--onlyvisible", "--name", "LibreHarp-sidebar-test.odt"], text=True
        )
        .strip()
        .splitlines()[-1]
    )
    subprocess.run(["import", "-window", xid, str(test.ZONE / "sidebar-writer.png")], check=True, timeout=15)
    print(test.ZONE / "sidebar-writer.png", flush=True)
    frame.ContainerWindow.setPosSize(20, 20, 1000, 720, 15)
    time.sleep(0.5)
    subprocess.run(["import", "-window", xid, str(test.ZONE / "sidebar-compact.png")], check=True, timeout=15)
    print(test.ZONE / "sidebar-compact.png", flush=True)
    app = Runtime(ctx)
    scoped = ScopedSettings(app, doc)
    capture(scoped, "scoped-settings")
    scoped.close()
    vocabulary = Vocabulary(app, doc, "document")
    capture(vocabulary, "vocabulary-editor")
    vocabulary.close()
    app.engine.close()
    doc.close(True)
finally:
    test.stop()
