"""All tunables live here and come from environment variables, so the same code runs
on a laptop, in Docker, or behind a reverse proxy without edits."""
import os
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
APP_VERSION = "0.1.0"


def _f(name, default):
    return type(default)(os.getenv(name, default))


def _soffice():
    """PDFSCOPE_SOFFICE, else soffice on PATH, else the standard Windows install folders."""
    if os.getenv("PDFSCOPE_SOFFICE"):
        return os.getenv("PDFSCOPE_SOFFICE")
    if shutil.which("soffice"):
        return "soffice"
    for base in (os.getenv("ProgramFiles"), os.getenv("ProgramFiles(x86)")):
        exe = Path(base or "") / "LibreOffice" / "program" / "soffice.exe"
        if base and exe.exists():
            return str(exe)
    return "soffice"


class Settings:
    workspace = Path(os.getenv("PDFSCOPE_WORKSPACE", BASE_DIR.parent / "workspace")).resolve()
    max_upload_mb = _f("PDFSCOPE_MAX_UPLOAD_MB", 100)
    session_ttl_hours = _f("PDFSCOPE_SESSION_TTL_HOURS", 24.0)
    share_ttl_hours = _f("PDFSCOPE_SHARE_TTL_HOURS", 24.0)
    public_base_url = os.getenv("PDFSCOPE_PUBLIC_URL", "").rstrip("/")
    soffice_bin = _soffice()
    soffice_timeout_s = _f("PDFSCOPE_SOFFICE_TIMEOUT", 120)
    compare_max_pages = _f("PDFSCOPE_COMPARE_MAX_PAGES", 150)
    # Cloud export (inactive until set; see README)
    google_client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    ms_client_id = os.getenv("MS_CLIENT_ID", "")
    ms_client_secret = os.getenv("MS_CLIENT_SECRET", "")


settings = Settings()
settings.workspace.mkdir(parents=True, exist_ok=True)
