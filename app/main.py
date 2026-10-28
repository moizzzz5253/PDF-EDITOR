import asyncio
import io
import json
import shutil
import time
import uuid
import zipfile
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageDraw

import pymupdf

from . import compare as cmp
from . import share, sysinfo
from .config import APP_VERSION, BASE_DIR, settings
from .errors import AppError, error_payload
from .ops import OPERATIONS, OpContext
from .store import SID_RE, Store, cleanup_expired, detect_kind, clean_name
from .trace import NODES, Tracer

app = FastAPI(title="PDF//SCOPE", version=APP_VERSION)

EVENTS = deque(maxlen=1000)  # backend log shown in the dashboard
STATS = {"requests": 0, "total_ms": 0.0}
COOKIE = "pdfscope_sid"


def log(sid, level, kind, msg, ms=None):
    EVENTS.append({"id": next(_ids), "t": time.time(), "sid": sid, "level": level, "kind": kind, "msg": msg, "ms": ms})


def _counter():
    n = 0
    while True:
        n += 1
        yield n


_ids = _counter()


# ---------------------------------------------------------------- middleware
@app.middleware("http")
async def session_and_log(request: Request, call_next):
    sid = request.cookies.get(COOKIE)
    new = not (sid and SID_RE.match(sid))
    if new:
        sid = uuid.uuid4().hex
    request.state.sid = sid
    t = time.perf_counter()
    resp = await call_next(request)
    ms = (time.perf_counter() - t) * 1000
    if new:
        resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax", max_age=int(settings.session_ttl_hours * 3600))
        log(sid, "info", "session", f"new session {sid[:8]} -> workspace/{sid[:8]}...")
    p = request.url.path
    if p.startswith("/api") and not p.startswith(("/api/logs", "/api/system")) and "/page/" not in p:
        STATS["requests"] += 1
        STATS["total_ms"] += ms
        log(sid, "warn" if resp.status_code >= 400 else "info", "http", f"{request.method} {p} -> {resp.status_code}", round(ms, 1))
    if not p.startswith("/api"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def store_of(request: Request) -> Store:
    s = Store(request.state.sid)
    s.touch()
    return s


# ---------------------------------------------------------------- errors
def err_response(request, exc, tracer=None, op=None):
    status, payload = error_payload(exc, tracer)
    sid = getattr(request.state, "sid", "-")
    log(sid, "error", "error", f"{payload['code']}: {payload['title']}  @ {payload['where']['file']}:{payload['where']['line']}" if payload["where"] else payload["code"])
    body = {"ok": False, "error": payload, "op": op}
    if tracer:
        body["trace"] = tracer.steps
        body["total_ms"] = tracer.total_ms()
    return JSONResponse(body, status_code=status)


@app.exception_handler(AppError)
async def _app_error(request, exc):
    return err_response(request, exc)


@app.exception_handler(RequestValidationError)
async def _validation(request, exc):
    e = AppError("E_BAD_REQUEST", "The request was malformed", "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in exc.errors()),
                 "This is a client/server contract mismatch - check the browser console and the request body.", 422)
    return err_response(request, e)


@app.exception_handler(Exception)
async def _any(request, exc):
    return err_response(request, exc)


# ---------------------------------------------------------------- housekeeping
@app.on_event("startup")
async def _startup():
    async def loop():
        while True:
            n = await run_in_threadpool(cleanup_expired)
            if n:
                log("-", "info", "cleanup", f"removed {n} expired session folder(s)")
            await asyncio.sleep(3600)
    asyncio.create_task(loop())
    log("-", "info", "boot", f"PDF//SCOPE {APP_VERSION} up. cwd={Path.cwd()} workspace={settings.workspace}")


# ---------------------------------------------------------------- info
@app.get("/api/system")
def api_system(request: Request):
    avg = STATS["total_ms"] / STATS["requests"] if STATS["requests"] else 0
    return sysinfo.snapshot(store_of(request), STATS["requests"], avg)


@app.get("/api/ops")
def api_ops():
    return {"nodes": NODES, "ops": [{k: v for k, v in o.items() if k != "fn"} for o in OPERATIONS.values()],
            "integrations": share.integrations()}


@app.get("/api/logs")
def api_logs(request: Request, since: int = 0):
    sid = request.state.sid
    return [e for e in EVENTS if e["id"] > since and e["sid"] in (sid, "-")][-200:]


@app.post("/api/client-error")
async def api_client_error(request: Request):
    d = await request.json()
    log(request.state.sid, "error", "browser", f"{d.get('message')} @ {d.get('source')}")
    return {"ok": True}


# ---------------------------------------------------------------- files
def public(rec):
    return rec


@app.get("/api/files")
def api_files(request: Request):
    return store_of(request).files()


async def save_upload(store, up) -> Path:
    limit = settings.max_upload_mb * 1024 * 1024
    dst = store.root / f"_up_{uuid.uuid4().hex[:8]}{Path(up.filename or 'file').suffix.lower()}"
    size = 0
    try:
        with open(dst, "wb") as f:
            while chunk := await up.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    raise AppError("E_TOO_LARGE", "Upload exceeds the size limit",
                                   f"'{up.filename}' is larger than {settings.max_upload_mb} MB (limit PDFSCOPE_MAX_UPLOAD_MB). Upload was stopped after {size / 1e6:.0f} MB.",
                                   "Compress the file or raise the limit in the server environment.", status=413)
                f.write(chunk)
    except BaseException:
        dst.unlink(missing_ok=True)
        raise
    if size == 0:
        dst.unlink(missing_ok=True)
        raise AppError("E_EMPTY_UPLOAD", "Uploaded file is empty", f"'{up.filename}' has 0 bytes - the browser sent nothing.", "Check the file opens locally, then retry.")
    return dst


@app.post("/api/files")
async def api_upload(request: Request):
    store = store_of(request)
    form = await request.form()
    ups = [v for k, v in form.multi_items() if hasattr(v, "filename")]
    if not ups:
        raise AppError("E_NO_INPUT", "No file received", "The request contained no file part named 'file'.", "Choose a file and try again.")
    out = []
    for up in ups:
        tmp = await save_upload(store, up)
        kind = detect_kind(tmp)
        name = clean_name(Path(up.filename or "file").name.replace("\\", "_"))
        rec = await run_in_threadpool(store.create_file, name, tmp, kind, "upload", f"uploaded {up.filename}")
        log(store.sid, "info", "upload", f"{name} ({rec['versions'][0]['size']:,} B, kind={kind}, pages={rec['versions'][0]['pages']}) -> {rec['id']}/v1")
        out.append(rec)
    return out


@app.delete("/api/files/{fid}")
def api_delete(fid: str, request: Request):
    store_of(request).delete(fid)
    return {"ok": True}


@app.patch("/api/files/{fid}")
async def api_rename(fid: str, request: Request):
    d = await request.json()
    st = store_of(request)
    old = st.get(fid)["name"]
    rec = st.rename(fid, d.get("name"))
    log(st.sid, "info", "rename", f"'{old}' -> '{rec['name']}' (display name only; disk file stays {fid}/v{rec['current']} so nothing can collide)")
    return rec


@app.post("/api/files/{fid}/current")
async def api_set_current(fid: str, request: Request):
    d = await request.json()
    return store_of(request).set_current(fid, int(d["v"]))


@app.get("/api/files/{fid}/download")
def api_download(fid: str, request: Request, v: int = 0):
    st = store_of(request)
    rec = st.get(fid)
    p = st.version_path(rec, v or None)
    name = rec["name"] if not v or v == rec["current"] else f"{Path(rec['name']).stem}-v{v}{Path(rec['name']).suffix}"
    return FileResponse(p, filename=name)


def render_page(st, rec, n, i, dpi):
    p = st.version_path(rec, n)
    cache = st.root / rec["id"] / "cache"
    cache.mkdir(exist_ok=True)
    cf = cache / f"v{n}_p{i}_{dpi}.png"
    if not cf.exists():
        with pymupdf.open(p) as d:
            if i < 0 or i >= len(d):
                raise AppError("E_PAGE_RANGE", "No such page", f"Page index {i} but the document has {len(d)} page(s).", "Use 0.." + str(len(d) - 1), 404)
            d[i].get_pixmap(dpi=dpi, alpha=False).save(cf)
    return cf


def placeholder(text="no page"):
    im = Image.new("RGB", (300, 400), (12, 24, 22))
    ImageDraw.Draw(im).text((110, 195), text, fill=(90, 140, 130))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


@app.get("/api/files/{fid}/v/{n}/page/{i}.png")
def api_page(fid: str, n: int, i: int, request: Request, dpi: int = 60):
    if not 20 <= dpi <= 300:
        raise AppError("E_DPI", "DPI out of range", f"dpi={dpi}; allowed 20-300.", "Use a value in range.")
    st = store_of(request)
    cf = render_page(st, st.get(fid), n, i, dpi)
    return FileResponse(cf, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/files/{fid}/v/{n}/entries")
def api_entries(fid: str, n: int, request: Request):
    st = store_of(request)
    with zipfile.ZipFile(st.version_path(st.get(fid), n)) as z:
        return [{"name": i.filename, "size": i.file_size} for i in z.infolist()]


@app.get("/api/files/{fid}/v/{n}/entry")
def api_entry(fid: str, n: int, name: str, request: Request):
    st = store_of(request)
    with zipfile.ZipFile(st.version_path(st.get(fid), n)) as z:
        if name not in z.namelist():
            raise AppError("E_NO_ENTRY", "Entry not in zip", name, "Pick a listed entry.", 404)
        return Response(z.read(name), media_type="image/jpeg" if name.lower().endswith("jpg") else "image/png", headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/files/{fid}/v/{n}/raw")
def api_raw(fid: str, n: int, request: Request):
    st = store_of(request)
    return FileResponse(st.version_path(st.get(fid), n))


# ---------------------------------------------------------------- operations
def execute(store: Store, op, fid, ver, params, uploads, tracer):
    rec = src = None
    if op["source"] != "none" and fid:
        rec = store.get(fid)
        ver = ver or rec["current"]
        src = store.version_path(rec, ver)
        if rec["kind"] not in op["accepts"]:
            if op["source"] == "required":
                raise AppError("E_WRONG_KIND", f"'{op['label']}' cannot use a {rec['kind'].upper()} file",
                               f"This tool accepts: {', '.join(op['accepts']).upper()}. '{rec['name']}' was detected as {rec['kind'].upper()}.",
                               "Select a different file, or convert it first with the CONVERT tools.")
            rec = src = None  # optional source of wrong type: ignore
    elif op["source"] == "required":
        raise AppError("E_NO_SOURCE", "No file selected", f"'{op['label']}' works on an existing file, but none is selected.", "Click a file in the FILES list (or upload one) first.")
    ctx = OpContext(store, tracer, rec, ver, src, params, uploads)
    try:
        res = op["fn"](ctx)
        with tracer.step("WRITE", "Register in workspace",
                         "The finished file is moved from the scratch folder into your session workspace and its size, page count and checksum (MD5) are recorded in meta.json.",
                         "store.add_version() / store.create_file()") as s:
            if res["mode"] == "version":
                new = store.add_version(fid, res["path"], op["id"], res.get("message", ""))
                s["detail"] = f"{new['name']} is now v{new['current']}"
            else:
                new = store.create_file(res["name"], res["path"], res.get("kind", "other"), op["id"], res.get("message", ""))
                s["detail"] = f"new file {new['name']}"
    finally:
        shutil.rmtree(ctx.tmp, ignore_errors=True)
    return rec, ver, new, res


@app.post("/api/ops/{op_id}")
async def api_run(op_id: str, request: Request):
    op = OPERATIONS.get(op_id)
    if not op:
        raise AppError("E_NO_OP", "Unknown operation", f"'{op_id}' is not registered. Known: {', '.join(OPERATIONS)}.", "Reload the page.", 404)
    store = store_of(request)
    form = await request.form()
    tracer = Tracer(op_id)
    saved = []
    try:
        params = json.loads(form.get("params") or "{}")
        uploads = {}
        with tracer.step("INPUT", "Receive request",
                         f"Browser sent a multipart form: operation '{op_id}', chosen file/version, parameters (JSON) and any attached files. Upload size limit {settings.max_upload_mb} MB.",
                         "await request.form(); json.loads(form['params'])") as s:
            for k, v in form.multi_items():
                if hasattr(v, "filename") and v.filename:
                    p = await save_upload(store, v)
                    saved.append(p)
                    uploads.setdefault(k, []).append(p)
            s["detail"] = f"params={params}  uploads={ {k: [x.name for x in v] for k, v in uploads.items()} }"
        fid = form.get("file_id") or None
        ver = int(form["version"]) if form.get("version") else None
        rec, ver, new, res = await run_in_threadpool(execute, store, op, fid, ver, params, uploads, tracer)
        log(store.sid, "info", "op", f"{op_id} ok in {tracer.total_ms()} ms - {res.get('message', '')}", tracer.total_ms())
        return {"ok": True, "op": op_id, "message": res.get("message"), "mode": res["mode"], "file": new,
                "from_version": ver, "to_version": new["current"], "page_map": res.get("page_map"),
                "removed": res.get("removed"), "highlight": res.get("highlight"), "trace": tracer.steps, "total_ms": tracer.total_ms()}
    except json.JSONDecodeError as e:
        return err_response(request, AppError("E_BAD_PARAMS", "Parameters were not valid JSON", str(e), "Browser/server mismatch - reload."), tracer, op_id)
    except Exception as e:
        return err_response(request, e, tracer, op_id)
    finally:
        for p in saved:
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------- compare
def _path_ver(st, fid, v):
    rec = st.get(fid)
    return rec, st.version_path(rec, v)


def _doc_page(st, fid, v, i):
    if i is None or i < 0:
        return None
    _, p = _path_ver(st, fid, v)
    d = pymupdf.open(p)
    return d, d[i]


@app.get("/api/compare")
def api_compare(request: Request, fa: str, va: int, fb: str, vb: int):
    st = store_of(request)
    t = time.perf_counter()
    ra, pa = _path_ver(st, fa, va)
    rb, pb = _path_ver(st, fb, vb)
    for r in (ra, rb):
        if r["kind"] != "pdf":
            raise AppError("E_WRONG_KIND", "Compare needs two PDFs", f"'{r['name']}' is {r['kind'].upper()}.", "Pick PDF versions.")
    res = cmp.compare(pa, pb)
    res["a"]["label"], res["b"]["label"] = f"{ra['name']} v{va}", f"{rb['name']} v{vb}"
    res["ms"] = round((time.perf_counter() - t) * 1000)
    log(st.sid, "info", "compare", f"{res['a']['label']} vs {res['b']['label']}: {res['counts']} in {res['ms']} ms", res["ms"])
    return res


@app.get("/api/compare/diff.png")
def api_diff_png(request: Request, fa: str, va: int, pa: int, fb: str, vb: int, pb: int):
    st = store_of(request)
    da, A = _doc_page(st, fa, va, pa)
    db, B = _doc_page(st, fb, vb, pb)
    return Response(cmp.diff_png(A, B), media_type="image/png")


@app.get("/api/compare/text")
def api_text(request: Request, fa: str, va: int, fb: str, vb: int, pa: int = -1, pb: int = -1):
    st = store_of(request)
    A = _doc_page(st, fa, va, pa) if pa >= 0 else None
    B = _doc_page(st, fb, vb, pb) if pb >= 0 else None
    return {"lines": cmp.page_text_diff(A[1] if A else None, B[1] if B else None)}


# ---------------------------------------------------------------- share
@app.post("/api/files/{fid}/share")
async def api_share(fid: str, request: Request):
    d = await request.json()
    st = store_of(request)
    rec = st.get(fid)
    v = int(d.get("v") or rec["current"])
    st.version_path(rec, v)
    tok, exp = share.create(st.sid, fid, v, rec["name"])
    base = settings.public_base_url or str(request.base_url).rstrip("/")
    url = f"{base}/s/{tok}"
    local = any(h in base for h in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"))
    log(st.sid, "info", "share", f"link for {rec['name']} v{v} valid {settings.share_ttl_hours:g}h; reachable_by_others={not local}")
    return {"url": url, "expires": exp, "reachable": not local, "links": share.links(url, rec["name"]),
            "warning": "This link points to localhost, so only this computer can open it. Set PDFSCOPE_PUBLIC_URL (or run behind ngrok / Cloudflare Tunnel) so recipients can download." if local else None}


@app.get("/s/{tok}")
def public_download(tok: str):
    x = share.resolve(tok)
    st = Store(x["sid"])
    rec = st.get(x["fid"])
    return FileResponse(st.version_path(rec, x["v"]), filename=rec["name"])


@app.post("/api/files/{fid}/export/{provider}")
def api_export(fid: str, provider: str, request: Request):
    store_of(request).get(fid)
    share.export_cloud(provider)


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")
