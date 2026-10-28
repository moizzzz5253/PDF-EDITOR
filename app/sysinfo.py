import os
import platform
import shutil
import subprocess
import sys
import time

import psutil
import pymupdf

from .config import APP_VERSION, BASE_DIR, settings

_START = time.time()
_SOFFICE = {}


def soffice_version():
    if "v" not in _SOFFICE:
        exe = shutil.which(settings.soffice_bin)
        try:
            _SOFFICE["v"] = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20).stdout.strip() if exe else None
        except Exception:
            _SOFFICE["v"] = None
    return _SOFFICE["v"]


def snapshot(store, requests_seen, avg_ms):
    du = shutil.disk_usage(settings.workspace)
    proc = psutil.Process()
    return {
        "cwd": os.getcwd(), "app_dir": str(BASE_DIR), "workspace": str(settings.workspace),
        "session_dir": str(store.root), "session_id": store.sid,
        "session_bytes": store.total_bytes(),
        "disk_total": du.total, "disk_free": du.free,
        "python": sys.version.split()[0], "platform": platform.platform(), "pid": os.getpid(),
        "app_version": APP_VERSION, "pymupdf": pymupdf.__version__, "mupdf": pymupdf.mupdf_version,
        "libreoffice": soffice_version(),
        "uptime_s": round(time.time() - _START), "rss_mb": round(proc.memory_info().rss / 1e6, 1),
        "cpu_pct": psutil.cpu_percent(interval=None), "threads": proc.num_threads(),
        "requests": requests_seen, "avg_ms": round(avg_ms, 1),
        "limits": {"max_upload_mb": settings.max_upload_mb, "session_ttl_h": settings.session_ttl_hours,
                   "share_ttl_h": settings.share_ttl_hours, "soffice_timeout_s": settings.soffice_timeout_s},
    }
