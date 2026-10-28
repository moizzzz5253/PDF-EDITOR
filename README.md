# PDF//SCOPE

A PDF workbench with an oscilloscope look: every command lights up a signal-flow pipeline
(INPUT → VALIDATE → PARSE → TRANSFORM → ENCODE → WRITE → VERIFY), and the real server steps,
calls and timings are shown in the Step Inspector and Backend Log.

## Run

```bash
pip install -r requirements.txt      # + install LibreOffice for Word to PDF
python run.py                        # http://127.0.0.1:8000
```
Windows: install LibreOffice, then set `PDFSCOPE_SOFFICE="C:\Program Files\LibreOffice\program\soffice.exe"`.
Docker (many users): see `Dockerfile`.

## Features
| Area | What |
|---|---|
| Convert | PDF → JPEG/PNG (zip if many pages), JPEG/PNG → PDF, Word (docx/doc/odt/rtf) → PDF |
| Pages | Remove, add (blank / PDF / image), crop (drag frame), extract to PDF/JPEG/PNG/TXT |
| Versions | Every edit is a new version (v1, v2…). Nothing is overwritten. |
| Compare | Old vs new: pages aligned by content, pixel diff overlay, blink mode, text diff |
| File | Rename; download any version |
| Share | Expiring link; WhatsApp / Telegram / Gmail / mail app launchers; device share menu |
| Diagnostics | Faults show code, root cause, fix, failing step, exact `file:line`, stack, copy-able report |
| Technical | cwd, workspace, session folder, file sizes, MD5, disk, memory, CPU, versions, limits |

## Not built yet (on purpose)
PDF → Word · password-protected PDFs · OCR · editing text inside pages · true redaction (crop only hides content) ·
Drive/OneDrive upload (buttons exist; need `GOOGLE_CLIENT_ID/SECRET`, `MS_CLIENT_ID/SECRET` and the OAuth flow in `app/share.py`) · user accounts.

## Settings (environment variables)
`PDFSCOPE_WORKSPACE` · `PDFSCOPE_MAX_UPLOAD_MB` (100) · `PDFSCOPE_SESSION_TTL_HOURS` (24) · `PDFSCOPE_SHARE_TTL_HOURS` (24) ·
`PDFSCOPE_PUBLIC_URL` (needed so share links work for other people) · `PDFSCOPE_SOFFICE` · `PDFSCOPE_SOFFICE_TIMEOUT` · `PDFSCOPE_COMPARE_MAX_PAGES`

## Adding a feature (the whole point of the layout)
1. Write a function in `app/ops/` and decorate it:
```python
@operation("rotate_pages", "Rotate pages", "PAGES", "Turn pages 90°.",
           params=[{"name": "pages", "type": "pages", "label": "Pages", "default": "all"},
                   {"name": "angle", "type": "select", "label": "Angle", "default": "90", "options": ["90", "180", "270"]}])
def rotate_pages(ctx):
    doc = open_pdf(ctx)
    with ctx.tracer.step("TRANSFORM", "Rotate", "Sets /Rotate on each page.", "page.set_rotation(...)"):
        ...
    out = ctx.out("out.pdf"); save_pdf(ctx, doc, out)
    return {"mode": "version", "path": out, "message": "Rotated", "kind": "pdf"}
```
2. Import the module in `app/ops/__init__.py`. The button, form, pipeline animation, trace and error card appear automatically.
Raise `AppError(code, title, cause, fix)` for any failure you can explain.

## Layout
```
run.py                  start server
app/main.py             HTTP routes, sessions, logging
app/ops/                one function per feature (registry.py = plug-in point)
app/compare.py          old-vs-new engine
app/store.py            per-session files + versions
app/share.py            links + cloud stubs
app/errors.py trace.py  fault payloads, step tracer
app/static/             index.html, style.css, app.js (no build step)
tests/smoke.py          API test · tests/ui_test.py browser walkthrough
```

## Going multi-user
Done: per-browser session folders, size limit, auto-cleanup, expiring links, Docker.
Before a public launch add: login (sessions are anonymous), HTTPS via a reverse proxy, rate limiting, a job queue for slow Word conversions, and object storage instead of local disk.
