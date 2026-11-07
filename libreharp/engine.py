"""A managed, bounded LSP client. A timeout is an error, never a clean result."""

import atexit
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path


class EngineError(RuntimeError):
    pass


def offset(text, position):
    lines = text.splitlines(keepends=True)
    line = position.get("line", 0)
    if line >= len(lines):
        return len(text)
    units = position.get("character", 0)
    decoded = lines[line].encode("utf-16-le")[: units * 2].decode("utf-16-le", errors="ignore")
    return sum(len(s) for s in lines[:line]) + len(decoded)


class Engine:
    def __init__(self, binary, timeout=12, data_dir=None):
        self.binary = str(Path(binary).resolve())
        self.timeout = timeout
        self._temp = tempfile.TemporaryDirectory(prefix="libreharp-engine-") if data_dir is None else None
        self.data_dir = Path(data_dir if data_dir is not None else self._temp.name)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.process = None
        self.messages = queue.Queue()
        self.request_id = 0
        self.revision = 0
        self.uri = f"file:///libreharp/check-{os.getpid()}-{id(self)}.txt"
        self.settings = {}
        self.opened = False
        self.version = "unknown"
        atexit.register(self.close)

    def close(self):
        process, self.process = self.process, None
        if process:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1)
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()

    def _reader(self, process, messages):
        try:
            while True:
                headers = {}
                while True:
                    line = process.stdout.readline()
                    if not line:
                        return
                    if line in (b"\r\n", b"\n"):
                        break
                    key, value = line.decode().split(":", 1)
                    headers[key.lower()] = value.strip()
                size = int(headers["content-length"])
                if not 0 <= size <= 16_000_000:
                    raise EngineError("Engine response is too large")
                data = bytearray()
                while len(data) < size:
                    chunk = process.stdout.read(size - len(data))
                    if not chunk:
                        raise EngineError("Incomplete engine response")
                    data.extend(chunk)
                messages.put(json.loads(data))
        except Exception as exc:
            messages.put(EngineError(str(exc)))
        finally:
            messages.put(EngineError("Harper stopped unexpectedly"))

    def _send(self, payload):
        data = json.dumps({"jsonrpc": "2.0", **payload}).encode()
        self.process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
        self.process.stdin.flush()

    def _next(self, deadline):
        while True:
            if time.monotonic() >= deadline:
                raise EngineError("Harper timed out; retry the check.")
            try:
                message = self.messages.get(timeout=max(0.001, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise EngineError("Harper timed out; retry the check.") from exc
            if isinstance(message, Exception):
                raise message
            if "method" in message and "id" in message:
                response = (
                    [self.settings for _ in message.get("params", {}).get("items", [])]
                    if message["method"] == "workspace/configuration"
                    else None
                )
                self._send({"id": message["id"], "result": response})
                continue
            return message

    def _request(self, method, params, deadline):
        self.request_id += 1
        number = self.request_id
        self._send({"id": number, "method": method, "params": params})
        while time.monotonic() < deadline:
            msg = self._next(deadline)
            if msg.get("id") == number:
                if "error" in msg:
                    raise EngineError(str(msg["error"]))
                return msg.get("result")
        raise EngineError("Harper request timed out")

    def _start(self):
        if self.process and self.process.poll() is None:
            return
        self.close()
        binary = Path(self.binary)
        if not binary.is_file():
            raise EngineError(f"Bundled Harper is missing: {binary}")
        if not os.access(binary, os.X_OK):
            binary.chmod(binary.stat().st_mode | 0o100)
        self.version = subprocess.check_output([self.binary, "--version"], text=True, timeout=5).strip()
        env = dict(
            os.environ,
            XDG_CONFIG_HOME=str(self.data_dir / "config"),
            XDG_DATA_HOME=str(self.data_dir / "data"),
        )
        self.process = subprocess.Popen(
            [self.binary, "--stdio"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=self.data_dir,
            env=env,
        )
        self.messages = queue.Queue()
        threading.Thread(target=self._reader, args=(self.process, self.messages), daemon=True).start()
        self.opened = False
        self._request(
            "initialize",
            {
                "processId": os.getpid(),
                "rootUri": self.data_dir.as_uri(),
                "capabilities": {"textDocument": {"publishDiagnostics": {"versionSupport": True}}},
            },
            time.monotonic() + self.timeout,
        )
        self._send({"method": "initialized", "params": {}})

    def check(self, text, settings):
        with self.lock:
            try:
                maximum = settings.get("maxFileLength", 120_000)
                if len(text.encode("utf-8")) > maximum:
                    raise EngineError(
                        f"This paragraph exceeds Harper's {maximum / 1000:g} KB limit. Split it before checking."
                    )
                self.settings = settings
                self._start()
                deadline = time.monotonic() + self.timeout
                if self.opened:
                    self._send(
                        {"method": "textDocument/didClose", "params": {"textDocument": {"uri": self.uri}}}
                    )
                self._send(
                    {
                        "method": "workspace/didChangeConfiguration",
                        "params": {"settings": {"harper-ls": settings}},
                    }
                )
                self.revision += 1
                # Harper may publish diagnostics without a version, including an older
                # document's diagnostics after configuration changes. A unique URI is
                # therefore the request identity; a version check alone is insufficient.
                self.uri = f"file:///libreharp/check-{os.getpid()}-{id(self)}-{self.revision}.txt"
                self._send(
                    {
                        "method": "textDocument/didOpen",
                        "params": {
                            "textDocument": {
                                "uri": self.uri,
                                "languageId": "plaintext",
                                "version": self.revision,
                                "text": text,
                            }
                        },
                    }
                )
                self.opened = True
                while True:
                    msg = self._next(deadline)
                    params = msg.get("params", {})
                    if (
                        msg.get("method") == "textDocument/publishDiagnostics"
                        and params.get("uri") == self.uri
                    ):
                        if params.get("version", self.revision) != self.revision:
                            continue
                        diagnostics = params.get("diagnostics", [])
                        break
                issues = []
                for diag in diagnostics:
                    begin = offset(text, diag["range"]["start"])
                    end = offset(text, diag["range"]["end"])
                    action_range = diag["range"]
                    if self.version.split()[-1] in {"3.0.0", "3.1.0"}:
                        # Harper 3.0.0 and 3.1.0 emit UTF-16 diagnostics but read
                        # code-action positions as scalar indices. Adapt requests only;
                        # returned edits must still exactly match the UTF-16 diagnostic.
                        lines = text.splitlines(keepends=True)
                        action_range = {}
                        for bound, pos in diag["range"].items():
                            line = lines[pos["line"]] if pos["line"] < len(lines) else ""
                            column = len(
                                line.encode("utf-16-le")[: pos["character"] * 2].decode(
                                    "utf-16-le", errors="ignore"
                                )
                            )
                            action_range[bound] = {"line": pos["line"], "character": column}
                    actions = (
                        self._request(
                            "textDocument/codeAction",
                            {
                                "textDocument": {"uri": self.uri},
                                "range": action_range,
                                "context": {"diagnostics": [diag]},
                            },
                            deadline,
                        )
                        or []
                    )
                    suggestions = []
                    for action in actions:
                        for edit in action.get("edit", {}).get("changes", {}).get(self.uri, []):
                            # Only offer replacements for this precise finding. Larger workspace
                            # edits must not be mistaken for replacements of the underlined word.
                            if edit.get("range") == diag["range"] and edit.get("newText") not in suggestions:
                                suggestions.append(edit["newText"])
                    issues.append(
                        {
                            "start": begin,
                            "end": end,
                            "text": text[begin:end],
                            "rule": str(diag.get("code", "Grammar")),
                            "message": diag.get("message", ""),
                            "suggestions": suggestions,
                        }
                    )
                return issues
            except Exception as exc:
                self.close()
                if isinstance(exc, EngineError):
                    raise
                raise EngineError(str(exc)) from exc
