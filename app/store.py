"""Per-session file store. Each session gets its own folder; each file keeps every
version (v1, v2...) so Compare can diff old vs new and nothing is ever overwritten."""
import hashlib
import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from .config import settings
from .errors import AppError

_LOCK = threading.RLock()
SID_RE = re.compile(r"^[a-f0-9]{32}$")
BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def detect_kind(path: Path):
    ext = path.suffix.lower()
    with open(path, "rb") as f:
        head = f.read(8)
    if head.startswith(b"%PDF-"):
        return "pdf"
    if ext == ".pdf":
        return "pdf"  # extension claims PDF; ops will give a precise E_NOT_PDF
    if ext in (".docx", ".doc", ".odt", ".rtf"):
        return "docx"
    if ext in (".jpg", ".jpeg", ".png"):
        return "image"
    if ext == ".zip":
        return "zip"
    return "other"


def clean_name(name, keep_ext=None):
    name = (name or "").strip()
    if not name:
        raise AppError("E_NAME_EMPTY", "File name is empty", "A file needs at least one character in its name.", "Type a name, e.g. report-final.pdf")
    bad = sorted(set(BAD_NAME.findall(name)))
    if bad:
        raise AppError("E_NAME_CHARS", "File name has forbidden characters",
                       f"These characters are not allowed on Windows/macOS/Linux file systems: {' '.join(bad)}",
                       "Remove them. Letters, digits, spaces, - _ ( ) . are fine.")
    if len(name) > 150:
        raise AppError("E_NAME_LONG", "File name is too long", f"{len(name)} characters; limit is 150.", "Shorten it.")
    if keep_ext and not name.lower().endswith(keep_ext.lower()):
        name += keep_ext
    return name


class Store:
    def __init__(self, sid):
        if not SID_RE.match(sid):
            raise AppError("E_SESSION", "Invalid session id", "The session cookie is malformed.", "Clear cookies for this site and reload.")
        self.sid = sid
        self.root = settings.workspace / sid
        self.root.mkdir(parents=True, exist_ok=True)
        self.meta = self.root / "meta.json"

    # ---- persistence
    def _load(self):
        if self.meta.exists():
            return json.loads(self.meta.read_text())
        return {"files": {}}

    def _save(self, d):
        tmp = self.meta.with_suffix(".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(self.meta)

    def touch(self):
        self.root.touch()

    # ---- queries
    def files(self):
        with _LOCK:
            return sorted(self._load()["files"].values(), key=lambda r: r["created"], reverse=True)

    def get(self, fid):
        with _LOCK:
            rec = self._load()["files"].get(fid)
        if not rec:
            raise AppError("E_NO_FILE", "File not found in this session",
                           f"No file with id '{fid}' exists in session {self.sid[:8]}... It was deleted, expired (sessions are cleaned after {settings.session_ttl_hours:g}h), or belongs to another browser session.",
                           "Reload the page and upload the file again.", status=404)
        return rec

    def version_path(self, rec, n=None):
        n = n or rec["current"]
        v = next((v for v in rec["versions"] if v["n"] == n), None)
        if not v:
            raise AppError("E_NO_VERSION", "Version not found", f"File '{rec['name']}' has versions {[v['n'] for v in rec['versions']]}, not {n}.", "Pick an existing version.", status=404)
        p = self.root / rec["id"] / v["filename"]
        if not p.exists():
            raise AppError("E_FILE_MISSING", "Version file missing on disk", f"Metadata lists {p} but it does not exist (deleted outside the app?).", "Remove the file from the list and upload again.", status=500)
        return p

    # ---- mutations
    def _describe(self, path, kind):
        pages = None
        if kind == "pdf":
            import pymupdf
            try:
                with pymupdf.open(path) as d:
                    pages = len(d)
            except Exception:
                pages = None
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return {"size": path.stat().st_size, "pages": pages, "md5": h.hexdigest()}

    def create_file(self, name, src: Path, kind, op="upload", note=""):
        with _LOCK:
            d = self._load()
            fid = uuid.uuid4().hex[:10]
            folder = self.root / fid
            folder.mkdir()
            ext = src.suffix or ".bin"
            dst = folder / f"v1{ext}"
            shutil.move(str(src), dst)
            ver = {"n": 1, "filename": dst.name, "kind": kind, "op": op, "note": note, "created": time.time(), **self._describe(dst, kind)}
            rec = {"id": fid, "name": name, "kind": kind, "created": time.time(), "current": 1, "versions": [ver]}
            d["files"][fid] = rec
            self._save(d)
            return rec

    def add_version(self, fid, src: Path, op, note=""):
        with _LOCK:
            d = self._load()
            rec = d["files"][fid]
            n = max(v["n"] for v in rec["versions"]) + 1
            dst = self.root / fid / f"v{n}{src.suffix}"
            shutil.move(str(src), dst)
            rec["versions"].append({"n": n, "filename": dst.name, "kind": rec["kind"], "op": op, "note": note, "created": time.time(), **self._describe(dst, rec["kind"])})
            rec["current"] = n
            self._save(d)
            return rec

    def set_current(self, fid, n):
        with _LOCK:
            d = self._load()
            rec = d["files"][fid]
            if n not in [v["n"] for v in rec["versions"]]:
                raise AppError("E_NO_VERSION", "Version not found", f"No version {n}.", "Pick an existing version.", status=404)
            rec["current"] = n
            self._save(d)
            return rec

    def rename(self, fid, name):
        with _LOCK:
            d = self._load()
            rec = d["files"].get(fid)
            if not rec:
                self.get(fid)
            old_ext = Path(rec["name"]).suffix
            rec["name"] = clean_name(name, keep_ext=old_ext or None)
            self._save(d)
            return rec

    def delete(self, fid):
        with _LOCK:
            d = self._load()
            if fid not in d["files"]:
                self.get(fid)
            del d["files"][fid]
            self._save(d)
        shutil.rmtree(self.root / fid, ignore_errors=True)

    def total_bytes(self):
        return sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())


def cleanup_expired():
    """Delete session folders untouched for longer than the TTL. Called hourly."""
    cutoff = time.time() - settings.session_ttl_hours * 3600
    removed = 0
    for d in settings.workspace.iterdir():
        if d.is_dir() and SID_RE.match(d.name) and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
