"""Structured errors. Every failure becomes a payload with: what happened, the root
cause in plain words, a suggested fix, and exactly where in the code it was raised."""
import subprocess
import traceback

from .config import BASE_DIR


class AppError(Exception):
    def __init__(self, code, title, cause, fix, status=400, **extra):
        super().__init__(title)
        self.code, self.title, self.cause, self.fix, self.status = code, title, cause, fix, status
        self.extra = extra


def _explain(exc):
    """Map well-known library exceptions to a readable diagnosis."""
    name = type(exc).__name__
    msg = str(exc)
    low = msg.lower()
    if isinstance(exc, AppError):
        return exc.code, exc.title, exc.cause, exc.fix, exc.status
    if name in ("FileDataError", "EmptyFileError") or "cannot open broken document" in low or "no objects found" in low:
        return ("E_PDF_CORRUPT", "PDF could not be parsed",
                "PyMuPDF could not find a valid PDF structure (cross-reference table / objects). The file is truncated, corrupted, or not really a PDF.",
                "Re-export or re-download the file. If it came from email, check the attachment was not cut off.", 422)
    if "password" in low or "encrypted" in low or "authenticate" in low:
        return ("E_PDF_ENCRYPTED", "PDF is password protected",
                "The document is encrypted and no password was supplied, so its pages cannot be read.",
                "Remove the password in the original app, then upload again. (Password entry is a planned feature.)", 422)
    if isinstance(exc, subprocess.TimeoutExpired):
        return ("E_CONVERT_TIMEOUT", "Conversion timed out",
                f"The LibreOffice process ran longer than {exc.timeout}s and was killed. Usually a huge document, or a stale soffice process holding a lock.",
                "Try a smaller document, or raise PDFSCOPE_SOFFICE_TIMEOUT.", 504)
    if isinstance(exc, FileNotFoundError):
        return ("E_FILE_MISSING", "A required file or program was not found",
                f"The OS reported: {msg}. Either a workspace file was deleted, or an external program (e.g. soffice) is not installed / not on PATH.",
                "Check the path above in the diagnostics. For soffice, install LibreOffice.", 500)
    if isinstance(exc, PermissionError):
        return ("E_PERMISSION", "Permission denied",
                f"The server process is not allowed to access: {msg}.",
                "Check ownership/permissions of the workspace directory shown in SYSTEM > workspace.", 500)
    if isinstance(exc, MemoryError):
        return ("E_MEMORY", "Out of memory", "Rendering or loading needed more RAM than available.",
                "Lower the DPI, process fewer pages at once, or give the server more memory.", 507)
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return ("E_DISK_FULL", "Disk full", "No space left on the device holding the workspace.",
                "Delete old files in the dashboard or free disk space.", 507)
    return ("E_INTERNAL", "Unexpected internal error",
            f"{name}: {msg}. This is not a known failure mode, so it is probably a bug. The stack frames below show where it was raised.",
            "Copy the diagnostic report and check the innermost app frame.", 500)


def error_payload(exc, tracer=None):
    code, title, cause, fix, status = _explain(exc)
    tb = traceback.extract_tb(exc.__traceback__)
    frames = [{"file": f.filename.replace(str(BASE_DIR.parent), "."), "line": f.lineno, "func": f.name,
               "code": (f.line or "").strip(), "app": f.filename.startswith(str(BASE_DIR))} for f in tb]
    app_frames = [f for f in frames if f["app"]]
    # keep our own frames + the innermost library frame (the real source of the failure); drop framework plumbing
    frames = [f for i, f in enumerate(frames) if f["app"] or i == len(frames) - 1]
    failing = None
    if tracer:
        failing = next((s for s in tracer.steps if s["status"] == "error"), None)
    payload = {
        "code": code, "title": title, "cause": cause, "fix": fix,
        "exc_type": type(exc).__name__, "exc_message": str(exc),
        "where": app_frames[-1] if app_frames else (frames[-1] if frames else None),
        "frames": frames[-8:],
        "failed_step": failing["title"] if failing else None,
        "failed_call": failing["call"] if failing else None,
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        "extra": getattr(exc, "extra", {}),
    }
    return status, payload
