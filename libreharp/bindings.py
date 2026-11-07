"""Match Writer's opaque proofreading IDs using a document-specific API handshake.

No active-window fallback. Workers consume immutable snapshots and never touch UNO
documents. All enumeration, metadata reads and ID handshakes use UI callbacks.
"""

import copy
import threading

import unohelper
from com.sun.star.document import XDocumentEventListener
from com.sun.star.util import XModifyListener

from .ignores import read_ignores
from .scopes import read_document, resolve


class DocumentEvents(unohelper.Base, XDocumentEventListener):
    def __init__(self, owner):
        self.owner = owner

    def documentEventOccured(self, event):
        if event.EventName in (
            "OnLoadFinished",
            "OnViewCreated",
            "OnSaveDone",
            "OnSaveAsDone",
            "OnFocus",
            "OnUnload",
            "OnModifyChanged",
        ):
            self.owner.schedule()

    def disposing(self, event):
        pass


class Bindings:
    def __init__(self, app):
        self.app = app
        self.lock = threading.RLock()
        self.by_id = {}
        self.by_uid = {}
        self.documents = {}
        self.queued = False
        self.refreshing = False
        self.events = DocumentEvents(self)
        from .uno_app import service

        self.broadcaster = service(app.ctx, "frame.GlobalEventBroadcaster")
        self.broadcaster.addDocumentEventListener(self.events)
        self.schedule()

    def schedule(self):
        with self.lock:
            if self.queued or self.refreshing:
                return
            self.queued = True
        from .uno_app import Callback, service

        service(self.app.ctx, "awt.AsyncCallback").addCallback(Callback(self.refresh), None)

    def refresh(self):
        from .uno_app import PROOFREADER, service, units

        with self.lock:
            self.queued = False
            if self.refreshing:
                return
            self.refreshing = True
        changed = False
        try:
            self.app.context_menus.sync_words()
            desktop = service(self.app.ctx, "frame.Desktop")
            iterator = service(self.app.ctx, "linguistic2.ProofreadingIterator")
            enum = desktop.getComponents().createEnumeration()
            live = {}
            open_uids = set()
            while enum.hasMoreElements():
                doc = enum.nextElement()
                if not doc.supportsService("com.sun.star.text.TextDocument"):
                    continue
                uid = str(doc.RuntimeUID)
                open_uids.add(uid)
                controllers = doc.getControllers()
                while controllers.hasMoreElements():
                    self.app.context_menus.attach(controllers.nextElement())
                if uid not in self.documents:
                    listener = DocumentModify(self)
                    doc.addModifyListener(listener)
                    self.documents[uid] = (doc, listener)
                snapshot = {"url": doc.URL, "settings": None, "ignored": {}, "error": None}
                try:
                    snapshot["settings"] = read_document(doc)
                    snapshot["ignored"] = read_ignores(doc)
                except ValueError as exc:
                    snapshot["error"] = str(exc)
                identity = self.by_uid.get(uid)
                if identity is None:
                    flat_iter = doc.getFlatParagraphIterator(2, False)
                    flat = flat_iter.getFirstPara()
                    while flat is not None:
                        text = flat.getText()
                        if text.strip():
                            result = iterator.checkSentenceAtPosition(
                                doc, flat, text, doc.CharLocale, 0, units(text), 0
                            )
                            if (
                                result.xProofreader
                                and result.xProofreader.getImplementationName() == PROOFREADER
                                and result.aDocumentIdentifier
                            ):
                                identity = result.aDocumentIdentifier
                                break
                        flat = flat_iter.getNextPara()
                if identity:
                    live[uid] = identity
                    with self.lock:
                        changed |= self.by_id.get(identity) != snapshot
                        self.by_id[identity] = snapshot
            with self.lock:
                for identity in set(self.by_id) - set(live.values()):
                    self.by_id.pop(identity, None)
                self.by_uid = live
            for uid in set(self.documents) - open_uids:
                old, listener = self.documents.pop(uid)
                try:
                    old.removeModifyListener(listener)
                except Exception:
                    pass
            self.app.context_menus.prune(open_uids)
        except Exception:
            self.app.log_error()
        finally:
            self.refreshing = False
        if changed:
            self.app.changed()

    def for_id(self, identity):
        with self.lock:
            snapshot = copy.deepcopy(self.by_id.get(identity))
        if snapshot is None:
            self.schedule()
            return None
        if snapshot["error"]:
            raise ValueError(snapshot["error"])
        return self.options(snapshot["url"], snapshot["settings"], snapshot["ignored"])

    def for_document(self, document):
        return self.options(document.URL, read_document(document), read_ignores(document))

    @staticmethod
    def options(url, settings, ignored):
        return {**resolve(url, settings)[0], "document_url": url, "ignored": ignored}


class DocumentModify(unohelper.Base, XModifyListener):
    def __init__(self, owner):
        self.owner = owner

    def modified(self, event):
        self.owner.schedule()

    def disposing(self, event):
        self.owner.schedule()
