# PDF//SCOPE

A PDF workbench with an oscilloscope look. Every command lights up a signal-flow pipeline
(INPUT → VALIDATE → PARSE → TRANSFORM → ENCODE → WRITE → VERIFY). The Step Inspector and
Backend Log show the real server steps, calls and timings.

## Run

### Windows, one click
1. Once, from the project folder:
   ```bash
   python -m venv venv
   venv\Scripts\pip install -r requirements.txt
   ```
2. Double-click **`Start PDF Scope.vbs`**. It starts a small control helper with no console window
   and opens its page at http://127.0.0.1:8100.
3. Use **Start / Stop / Open / Quit** there. The app itself runs at http://127.0.0.1:8000.
   The dashboard's **STOP** button also stops the server through the helper. Your files stay in the workspace.

Nothing starts at boot or login. Logs go to `logs/server.log` and `logs/launcher.log`.

### Any OS
```bash
pip install -r requirements.txt      # + install LibreOffice for Word to PDF
python run.py                        # http://127.0.0.1:8000
```
`HOST`, `PORT` and `RELOAD=1` change how `run.py` starts uvicorn.

On Windows, install LibreOffice and set `PDFSCOPE_SOFFICE="C:\Program Files\LibreOffice\program\soffice.exe"`.

### Docker (many users)
```bash
docker build -t pdfscope .
docker run -p 8000:8000 -v pdfscope-data:/data pdfscope
```
The image includes LibreOffice, so Word to PDF works out of the box.

## Features
| Area | What |
|---|---|
| Convert | PDF → JPEG/PNG (choose pages; a zip if there are several) · JPEG/PNG → PDF (pick order; fit, A4 or Letter pages with margin; also accepts an image or image zip already in the workspace) · Word (docx/doc/odt/rtf) → PDF using headless LibreOffice |
| Pages | Remove (type a list or click pages) · add (blank, or pages from a PDF or image) · crop (drag the frame or type % / mm) · rotate 90/180/270° · reorder (`3,1,2` or `reverse`) · merge PDFs and images onto the end · extract to PDF/JPEG/PNG/TXT |
| Versions | Every edit makes a new version (v1, v2…). Nothing is overwritten. Click a version to view it or make it current again. |
| Workspace | Drag-and-drop upload, page thumbnails, double-click to zoom, browse images inside zip results, rename, delete a file with all its versions, download any version |
| Compare | Old vs new: pages aligned by content, pixel diff overlay, blink mode, text diff |
| Share | Expiring link · WhatsApp / Telegram / Gmail / mail app launchers · device share menu (Web Share API) |
| Diagnostics | Faults show the code, root cause, fix, failing step, exact `file:line`, stack and a copyable report. Browser-side errors are reported to the server log too. |
| Technical | cwd, workspace, session folder, file sizes, MD5, disk, memory, CPU, uptime, request count and timing, versions, limits |
| Themes | Phosphor, Paper, Blush, Sakura, Hot Pink and Rose Gold presets, plus custom accent and background colours. Saved per browser. |

## Not built yet (on purpose)
PDF → Word · password-protected PDFs · OCR · editing text inside pages · true redaction (crop only hides content) ·
Drive/OneDrive upload (the buttons exist but need `GOOGLE_CLIENT_ID/SECRET`, `MS_CLIENT_ID/SECRET` and the OAuth flow in `app/share.py`) · user accounts.

## Settings (environment variables)
| Variable | Default | What |
|---|---|---|
| `PDFSCOPE_WORKSPACE` | `./workspace` | Where session files and versions are stored |
| `PDFSCOPE_MAX_UPLOAD_MB` | 100 | Upload size limit |
| `PDFSCOPE_SESSION_TTL_HOURS` | 24 | Idle sessions are cleaned up after this |
| `PDFSCOPE_SHARE_TTL_HOURS` | 24 | Share link lifetime |
| `PDFSCOPE_PUBLIC_URL` | (empty) | Public base URL, needed so share links work for other people |
| `PDFSCOPE_SOFFICE` | `soffice` | LibreOffice binary |
| `PDFSCOPE_SOFFICE_TIMEOUT` | 120 | Seconds before a Word conversion is aborted |
| `PDFSCOPE_COMPARE_MAX_PAGES` | 150 | Page limit for Compare |

## Adding a feature (the whole point of the layout)
1. Write a function in `app/ops/` and decorate it with `@operation`:
```python
@operation("grayscale", "Grayscale", "PAGES", "Turn pages black and white.",
           params=[{"name": "pages", "type": "pages", "label": "Pages", "default": "all"}])
def grayscale(ctx):
    doc = open_pdf(ctx)
    with ctx.tracer.step("TRANSFORM", "Grayscale", "Re-renders each page in gray.", "page.get_pixmap(colorspace=GRAY)"):
        ...
    out = ctx.out("out.pdf"); save_pdf(ctx, doc, out)
    return {"mode": "version", "path": out, "message": "Converted to grayscale", "kind": "pdf"}
```
   Parameter types: `pages`, `select`, `int`, `text`, `file` (with `multiple`, `accept`, `ws` to allow workspace files),
   plus `show_if` to show a field only for certain choices. `rotate_pages` in `app/ops/pages_tools.py` is a full working example.
2. If it's a new module, import it in `app/ops/__init__.py`. The button, form, pipeline animation, trace and error card appear automatically.

Raise `AppError(code, title, cause, fix)` for any failure you can explain.

## Layout
```
run.py                     start the server
Start PDF Scope.vbs        Windows one-click launcher
launcher/control.py/.html  control helper on :8100 (Start/Stop/Open/Quit)
app/main.py                HTTP routes, sessions, logging
app/config.py              settings from environment variables
app/ops/                   one function per feature (registry.py = plug-in point)
  convert.py               PDF↔image, Word → PDF
  pages.py                 remove, add, crop, extract
  pages_tools.py           rotate, reorder, merge
app/pagespec.py            page-list parsing ("1,3-5", "last", "all")
app/compare.py             old-vs-new engine
app/store.py               per-session files and versions
app/share.py               links and cloud stubs
app/errors.py, trace.py    fault payloads, step tracer
app/sysinfo.py             Technical panel data
app/static/                index.html, app.js, style.css, theme.js, server.js (no build step)
tests/smoke.py             API test (server must be running)
tests/ui_test.py           Playwright browser walkthrough
```

## Going multi-user
Done: per-browser session folders, a size limit, auto-cleanup, expiring links, Docker.
Before a public launch, add login (sessions are anonymous), HTTPS through a reverse proxy, rate limiting, a job queue for slow Word conversions, and object storage instead of local disk.

## License
GPL-3.0. See `LICENSE`.
