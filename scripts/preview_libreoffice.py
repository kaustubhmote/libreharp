"""Capture only LibreHarp test windows on the display for visual QA."""

import subprocess
import time

import test_libreoffice as test

from libreharp.uno_app import Review, RuleBrowser, Runtime, Settings


def capture(window, name):
    window.show()
    time.sleep(0.5)
    result = subprocess.check_output(
        ["xdotool", "search", "--onlyvisible", "--name", "^" + window.model.Title + "$"], text=True
    )
    window_id = result.strip().splitlines()[-1]
    target = test.ZONE / (name + ".png")
    subprocess.run(["import", "-window", window_id, str(target)], check=True, timeout=15)
    print(target, flush=True)
    return target


try:
    ctx = test.start(visible=True)
    app = Runtime(ctx)
    doc = test.desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, ())
    doc.Text.String = (
        "This is a example. This is is incorrect.\nWe utilize Qzxnmrspectroprobe to analyse the samples."
    )
    review = Review(app, doc)
    review.show()
    review.check()
    deadline = time.monotonic() + 20
    while review.pending and time.monotonic() < deadline:
        time.sleep(0.1)
    if not review.rows:
        raise RuntimeError("Review did not produce suggestions")
    capture(review, "review-window")
    review.close()
    rules = RuleBrowser(app)
    rules.model.getByName("search").Text = "sentence"
    rules.refresh()
    capture(rules, "rule-browser")
    rules.close()
    settings = Settings(app)
    capture(settings, "settings-window")
    settings.close()
    doc.close(True)
    app.engine.close()
finally:
    test.stop()
