"""PDF//SCOPE control helper.

Started by 'Start PDF Scope.vbs' through the venv's pythonw (no console window).
Serves a control page on 127.0.0.1:8100 with Start / Stop / Open / Quit and runs
the PDF server (run.py) as a child process. Nothing starts at boot or login.
"""
import json
import logging
import platform
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

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
LAST_ERROR = LOG_DIR / "last-error.txt"

# Error codes shown to the user. The README lists each one with what to do.
#   PS-203  the control helper itself crashed (Python error)
#   PS-301  the PDF server exited while starting
#   PS-302  the Python environment (venv) is missing
#   PS-303  port 8000 is already used by another program
#   PS-401  Windows Smart App Control blocked a file the app needs
SAC_MARKERS = ("application control policy has blocked", "smart app control", "winerror 4551")


def smart_app_control_blocked(text: str) -> bool:
    low = text.lower()
    return any(m in low for m in SAC_MARKERS)


def error_report(code: str, message: str, log_lines=None) -> str:
    """Plain-text report the user can paste to whoever supports them. Also saved to logs/last-error.txt."""
    lines = [
        f"PDF//SCOPE error {code}",
        message,
        "",
        f"Time:    {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"Windows: {platform.platform()}",
        f"Python:  {sys.version.split()[0]} ({sys.executable})",
        f"Folder:  {ROOT}",
    ]
    if log_lines:
        lines += ["", "--- last log lines ---", *log_lines]
    text = "\n".join(lines)
    try:
        LAST_ERROR.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text


try:
    import psutil
except Exception as exc:  # a broken venv, or Smart App Control blocking psutil's DLL
    code = "PS-401" if smart_app_control_blocked(str(exc)) else "PS-203"
    log.error("%s control helper could not start:\n%s", code, traceback.format_exc())
    error_report(code, f"The control helper could not start: {exc}", traceback.format_exc().splitlines())
    raise

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
            return _fail("PS-302", f"Python environment not found: {PYTHONW}. Double-click 'Start PDF Scope' again to rebuild it.")
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
            tail = "\n".join(_log_tail(60)).lower()
            if smart_app_control_blocked(tail):
                return _fail("PS-401", "Windows Smart App Control blocked a file the PDF server needs. See 'Smart App Control' in the README.")
            if "10048" in tail or "address already in use" in tail or "only one usage of each socket" in tail:
                return _fail("PS-303", "Port 8000 is already used by another program. Close that program (or restart the computer) and press Start again.")
            return _fail("PS-301", f"The PDF server stopped while starting (exit code {proc.returncode}).")
        return {"ok": True, "message": "Started, still loading"}


def _fail(code: str, message: str) -> dict:
    log.error("%s %s", code, message)
    return {"ok": False, "code": code, "message": f"[{code}] {message}",
            "report": error_report(code, message, _log_tail(60))}


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
        if "/api/status" in self.path:  # polled every 2 s by the page; would bury the useful lines
            return
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
        try:
            result = action()
        except Exception as exc:
            log.exception("PS-203 %s failed", self.path)
            result = {"ok": False, "code": "PS-203", "message": f"[PS-203] The launcher hit an error: {exc}",
                      "report": error_report("PS-203", f"{self.path} failed: {exc}", traceback.format_exc().splitlines())}
        self._json(result)


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
    try:
        main()
    except Exception as exc:
        log.exception("PS-203 control helper crashed")
        error_report("PS-203", f"The control helper crashed: {exc}", traceback.format_exc().splitlines())
        raise
