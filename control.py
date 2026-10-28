"""PDF//SCOPE control helper.

Started by 'Start PDF Scope.vbs' through the venv's pythonw (no console window).
Serves a control page on 127.0.0.1:8100 with Start / Stop / Open / Quit and runs
the PDF server (run.py) as a child process. Nothing starts at boot or login.
"""
import json
import logging
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_DIR = ROOT / "launcher"
LOG_DIR = ROOT / "logs"
SERVER_LOG = LOG_DIR / "server.log"
PID_FILE = LAUNCHER_DIR / "server.pid"
PYTHONW = ROOT / "venv" / "Scripts" / "pythonw.exe"
CONTROL_PORT = 8100
APP_URL = "http://127.0.0.1:8000"
CREATE_NO_WINDOW = 0x08000000  # Windows flag: the child process gets no console

# Only these Host/Origin values are accepted. This blocks other websites from
# driving this helper through your browser (cross-site POSTs and DNS rebinding).
ALLOWED_HOSTS = {"127.0.0.1:8100", "localhost:8100"}
ALLOWED_ORIGINS = {
    "http://127.0.0.1:8100", "http://localhost:8100",
    "http://127.0.0.1:8000", "http://localhost:8000",
}

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "launcher.log", level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("pdfscope.control")

_lock = threading.Lock()
_httpd = None


class _Server(ThreadingHTTPServer):
    # Off on purpose: on Windows, address reuse would let a second helper bind the same port.
    allow_reuse_address = False


def _app_responds() -> bool:
    try:
        with urllib.request.urlopen(APP_URL + "/", timeout=1.5) as r:
            return r.status < 500
    except Exception:
        return False


def _read_pid():
    try:
        return int(PID_FILE.read_text().strip())
    except (OSError, ValueError):
        return None


def _clear_pid():
    PID_FILE.unlink(missing_ok=True)


def _server_pid():
    """PID of the PDF server we started, or None. Confirms the process really is run.py."""
    pid = _read_pid()
    if pid is None:
        return None
    try:
        proc = psutil.Process(pid)
        if proc.is_running() and "run.py" in " ".join(proc.cmdline()).lower():
            return pid
    except psutil.Error:
        pass
    _clear_pid()  # stale: it ended, or the PID now belongs to another program
    return None


def _log_tail(lines: int = 12) -> list:
    try:
        with open(SERVER_LOG, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 8192))
            text = f.read().decode("utf-8", errors="replace")
        return text.splitlines()[-lines:]
    except OSError:
        return []


def status() -> dict:
    pid = _server_pid()
    return {
        "running": pid is not None,
        "pid": pid,
        "app_responding": _app_responds(),
        "url": APP_URL,
        "log_tail": _log_tail(),
    }


def start() -> dict:
    with _lock:
        if _server_pid() is not None:
            return {"ok": True, "message": "Already running"}
        if not PYTHONW.exists():
            return {"ok": False, "message": f"Python environment not found: {PYTHONW}. Create the venv and install requirements.txt."}
        # 'wb' keeps only this run's output, so the log cannot grow without limit.
        with open(SERVER_LOG, "wb") as out:
            proc = subprocess.Popen(
                [str(PYTHONW), str(ROOT / "run.py")],
                cwd=str(ROOT), stdin=subprocess.DEVNULL,
                stdout=out, stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
        PID_FILE.write_text(str(proc.pid))
        log.info("started PDF server pid=%s", proc.pid)
        for _ in range(40):  # wait up to 20 s for the app to answer
            if proc.poll() is not None:
                break
            if _app_responds():
                return {"ok": True, "message": "Started"}
            time.sleep(0.5)
        if proc.poll() is not None:
            _clear_pid()
            log.error("PDF server exited during startup, code=%s", proc.returncode)
            return {"ok": False, "message": f"Server exited during startup (code {proc.returncode}). See the log below."}
        return {"ok": True, "message": "Started, still loading"}


def stop() -> dict:
    with _lock:
        pid = _server_pid()
        if pid is None:
            return {"ok": True, "message": "Not running"}
        try:
            proc = psutil.Process(pid)
            procs = proc.children(recursive=True) + [proc]
            for p in procs:
                p.terminate()
            _, alive = psutil.wait_procs(procs, timeout=8)
            for p in alive:
                p.kill()
        except psutil.Error as exc:
            log.warning("stop: %s", exc)
        _clear_pid()
        log.info("stopped PDF server pid=%s", pid)
        return {"ok": True, "message": "Stopped"}


def quit_helper() -> dict:
    stop()

    def _shutdown():
        time.sleep(0.5)  # let the HTTP reply leave first
        _httpd.shutdown()

    threading.Thread(target=_shutdown, daemon=True).start()
    log.info("control helper quit")
    return {"ok": True, "message": "Launcher closed"}


class Handler(BaseHTTPRequestHandler):
    server_version = "PDFScopeControl/1.0"

    def log_message(self, format, *args):  # route access logs to launcher.log
        log.info("%s %s", self.address_string(), format % args)

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in ALLOWED_HOSTS

    def _origin(self):
        origin = self.headers.get("Origin")
        return origin if origin in ALLOWED_ORIGINS else None

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = self._origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _refuse(self):
        self._json({"ok": False, "message": "Request refused"}, 403)

    def do_GET(self):
        if not self._host_ok():
            return self._refuse()
        if self.path == "/":
            return self._send(200, (LAUNCHER_DIR / "control.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/status":
            return self._json(status())
        self._send(404, b"Not found", "text/plain")

    def do_POST(self):
        origin = self.headers.get("Origin")
        if not self._host_ok() or (origin is not None and origin not in ALLOWED_ORIGINS):
            return self._refuse()
        routes = {"/api/start": start, "/api/stop": stop, "/api/quit": quit_helper}
        action = routes.get(self.path)
        if action is None:
            return self._send(404, b"Not found", "text/plain")
        self._json(action())


def main():
    global _httpd
    try:
        _httpd = _Server(("127.0.0.1", CONTROL_PORT), Handler)
    except OSError:
        # Another helper already holds the port. The .vbs just opens its page.
        log.info("port %s busy, a helper is already running; exiting", CONTROL_PORT)
        return
    log.info("control helper on http://127.0.0.1:%s", CONTROL_PORT)
    try:
        _httpd.serve_forever()
    finally:
        _httpd.server_close()
        log.info("control helper stopped")


if __name__ == "__main__":
    main()
