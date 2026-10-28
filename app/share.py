"""Share links. A token maps to (session, file, version) with an expiry. links() builds
'send the link via WhatsApp / Telegram / Gmail' URLs; the dashboard offers them only when
the link is reachable by others (PDFSCOPE_PUBLIC_URL). Sending the file itself happens in
the browser (device share menu, or download + open the app). Drive / OneDrive need OAuth
keys (see integrations())."""
import json
import secrets
import threading
import time
from urllib.parse import quote

from .config import settings
from .errors import AppError

_FILE = settings.workspace / "shares.json"
_LOCK = threading.Lock()


def _load():
    return json.loads(_FILE.read_text()) if _FILE.exists() else {}


def create(sid, fid, v, name):
    tok = secrets.token_urlsafe(18)
    with _LOCK:
        d = {k: x for k, x in _load().items() if x["exp"] > time.time()}
        d[tok] = {"sid": sid, "fid": fid, "v": v, "name": name, "exp": time.time() + settings.share_ttl_hours * 3600}
        _FILE.write_text(json.dumps(d))
    return tok, d[tok]["exp"]


def resolve(tok):
    with _LOCK:
        x = _load().get(tok)
    if not x or x["exp"] < time.time():
        raise AppError("E_SHARE_EXPIRED", "Share link expired or invalid",
                       f"Links live for {settings.share_ttl_hours:g} hours and then stop working, or the token was never issued.",
                       "Ask the owner to create a new share link.", status=404)
    return x


def links(url, name):
    msg = f"{name}: {url}"
    return {
        "whatsapp": "https://wa.me/?text=" + quote(msg),
        "telegram": f"https://t.me/share/url?url={quote(url)}&text={quote(name)}",
        "gmail": f"https://mail.google.com/mail/?view=cm&fs=1&su={quote(name)}&body={quote(msg)}",
        "mailto": f"mailto:?subject={quote(name)}&body={quote(msg)}",
    }


def integrations():
    g = bool(settings.google_client_id and settings.google_client_secret)
    m = bool(settings.ms_client_id and settings.ms_client_secret)
    return {
        "gdrive": {"configured": g, "env": ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
                   "how": "Google Cloud Console > APIs > enable Drive API > OAuth client (Web) > redirect URI <your-url>/oauth/google/callback"},
        "onedrive": {"configured": m, "env": ["MS_CLIENT_ID", "MS_CLIENT_SECRET"],
                     "how": "Azure Portal > App registrations > new app > API permission Files.ReadWrite > redirect URI <your-url>/oauth/microsoft/callback"},
    }


def export_cloud(provider):
    info = integrations().get(provider)
    if not info:
        raise AppError("E_PROVIDER", "Unknown provider", provider, "Use gdrive or onedrive.")
    if not info["configured"]:
        raise AppError("E_NOT_CONFIGURED", f"{provider} upload is not configured yet",
                       f"Uploading to a personal cloud account needs the app to be registered with the provider (OAuth). Environment variables {', '.join(info['env'])} are empty on this server.",
                       info["how"], status=501, env=info["env"])
    raise AppError("E_NOT_IMPLEMENTED", "OAuth flow not implemented yet",
                   "Credentials are present but the consent screen / upload call is still a stub in this version.",
                   "See app/share.py: implement /oauth callbacks and the files.create upload.", status=501)
