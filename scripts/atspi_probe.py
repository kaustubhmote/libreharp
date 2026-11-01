"""Read only the named LibreHarp test dialog through the Linux screen-reader bridge."""

import json
import sys
import time

import pyatspi


def find_dialog(title):
    desktop = pyatspi.Registry.getDesktop(0)
    for app in desktop:
        for frame in app:
            if frame.name == title:
                return frame
    return None


deadline = time.monotonic() + 15
dialog = None
while time.monotonic() < deadline and dialog is None:
    dialog = find_dialog(sys.argv[1])
    if dialog is None:
        time.sleep(0.2)
if dialog is None:
    raise RuntimeError("LibreHarp test dialog was not exposed through AT-SPI")
result = []


def walk(node, depth=0):
    if depth > 30 or len(result) > 5000:
        return
    item = {
        "name": node.name,
        "role": node.getRoleName(),
        "focused": node.getState().contains(pyatspi.STATE_FOCUSED),
        "description": node.description,
    }
    if node.name == "Status":
        item["text"] = node.queryText().getText(0, -1)
    result.append(item)
    start = len(result)
    for child in node:
        walk(child, depth + 1)
    item["focus_within"] = item["focused"] or any(n["focused"] for n in result[start:])


walk(dialog)
print(json.dumps(result))
