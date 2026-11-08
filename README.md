# PDF//SCOPE

A PDF workbench that runs on your own computer. Convert, split, merge, crop, rotate and compare PDFs
in your browser. Your files never leave your PC.

Every command lights up a pipeline (INPUT → VALIDATE → PARSE → TRANSFORM → ENCODE → WRITE → VERIFY),
and the Step Inspector shows exactly what the server did.

---

# User guide (Windows)

## 1. Install

1. Download the project as a ZIP (on GitHub: green **Code** button → **Download ZIP**).
2. **Before you unzip it:** right-click the ZIP → **Properties** → tick **Unblock** at the bottom → **OK**.
   This tells Windows the files are yours and avoids most security pop-ups (see section 5).
3. Right-click the ZIP → **Extract All…** and put the folder somewhere permanent, such as `Documents\PDF-SCOPE`.
   Don't run it from inside the ZIP.
4. Double-click **`Start PDF Scope.vbs`** in the folder.

The first time, a blue setup window appears. It:
- installs Python if you don't have it (asks first; no admin rights needed),
- downloads the parts the app needs (about 100 MB, needs internet once),
- asks whether to install LibreOffice. That's only needed for **Word → PDF**. Say No if you don't need it.

This takes a few minutes the first time. After that, the app opens in seconds.

## 2. Start and stop

Double-clicking **Start PDF Scope** opens the **control page** in your browser (http://127.0.0.1:8100):

| Button | What it does |
|---|---|
| **Start** | Starts the PDF engine. The light turns green when it's ready. |
| **Open PDF Scope** | Opens the dashboard (http://127.0.0.1:8000). |
| **Stop** | Stops the PDF engine. Your files are kept. |
| **Quit launcher** | Stops everything and closes the control page. |

Nothing runs at startup or in the background after you quit. Bookmark the dashboard if you like, but it only
works while the launcher is running.

## 3. Using the dashboard

1. **Upload:** drag PDFs, images or Word files onto the page (or click to browse).
2. **Pick a file** in the workspace list on the left. Its pages appear as thumbnails. Double-click one to zoom.
3. **Pick a command** and fill in the short form. Page lists accept `1,3-5`, `last` or `all`.

| Area | What you can do |
|---|---|
| Convert | PDF → JPEG/PNG · images → PDF (choose order, page size, margins) · Word → PDF (needs LibreOffice) |
| Pages | Remove · add (blank or from another file) · crop (drag the frame) · rotate · reorder (drag thumbnails) · merge · extract |
| Versions | Every edit makes a new version (v1, v2…). Nothing is overwritten. Click an old version to view it or make it current again. |
| Compare | Old vs new side by side, with a highlighted difference overlay and a text diff |
| Share | Download any version, or send it to WhatsApp / Telegram / Gmail through the share menu |
| Themes | Several colour themes, or your own colours (top bar) |

Files live in the `workspace` folder inside the app folder. Idle files are cleaned up after 24 hours, so
**download anything you want to keep**.

## 4. If something goes wrong: send me the error report

Every error, at every stage, has a **code** (like `PS-103` or `E_PDF_CORRUPT`) and a report you can copy:

| Where the error appears | How to copy it |
|---|---|
| A pop-up window during setup or launch | The report is **already copied** for you. Just paste it (**Ctrl+V**) into a message. |
| The control page | Click **Copy error report**. |
| The dashboard (red fault card) | Click **COPY DIAGNOSTIC**. |
| Nothing opens at all | Open the app folder → `logs` → send the file `last-error.txt` (and `setup.log` if there is one). |

Paste the report into WhatsApp or email and send it to the person who gave you PDF//SCOPE.
The report contains the error code, your Windows version, the time and the last log lines. It contains no file contents.

### Error codes

| Code | Meaning | What you can try first |
|---|---|---|
| **PS-101** | Python could not be installed | Install Python from python.org (tick **Add python.exe to PATH**), then start again. |
| **PS-102** | The app's Python environment could not be created | Move the folder somewhere simple like `Documents\PDF-SCOPE` and start again. |
| **PS-103** | Packages could not be downloaded | Check your internet connection and start again. |
| **PS-104** | Setup stopped unexpectedly | Send the report. |
| **PS-201** | The setup window closed before finishing | Start again. If Windows showed a "blocked" message, see section 5. |
| **PS-202** | The launcher did not start | Restart the computer and start again. If it keeps happening, send the report. |
| **PS-203** | The launcher crashed | Send the report. |
| **PS-204** | Port 8100 is used by another program | Restart the computer and start again. |
| **PS-205** | The control page lost the launcher | Double-click **Start PDF Scope** again. |
| **PS-301** | The PDF engine stopped while starting | Send the report. |
| **PS-302** | The app's Python environment is missing | Double-click **Start PDF Scope**. It rebuilds itself. |
| **PS-303** | Port 8000 is used by another program | Close other local servers, or restart the computer, then press **Start**. |
| **PS-401** | **Windows Smart App Control blocked a file** | See section 5. |
| `E_…` codes | Errors inside the dashboard (bad PDF, password-protected file, etc.) | The fault card explains the cause and the fix. |

## 5. Windows security: Smart App Control and SmartScreen

PDF//SCOPE is a free project. Its files are not signed with a paid Microsoft certificate, so Windows 11 may
block or warn about them. Here is how to tell which message you got and what to do.

### "Windows protected your PC" (blue box, SmartScreen)
This one is only a warning. Click **More info** → **Run anyway**.

### "Smart App Control blocked an app that may be unsafe" / "Part of this app has been blocked"
Smart App Control (SAC) is stricter. It has no "Run anyway" button, and it can block the app before it even starts,
so you may see no PDF//SCOPE error at all. It can also block files the app uses later, which shows up as error **PS-401**.

**Step 1: try Unblock first (keeps SAC on).**
1. Quit the launcher if it's running.
2. Right-click the original ZIP → **Properties** → tick **Unblock** → **OK**.
3. Delete the old app folder, extract the ZIP again, and double-click **Start PDF Scope**.

If you no longer have the ZIP, right-click **Start PDF Scope.vbs** → **Properties** → tick **Unblock** if you see it.

**Step 2: if it is still blocked, turn Smart App Control off.**
1. Press **Start**, type **Smart App Control**, and open **Smart App Control settings**.
   (Or: **Settings → Privacy & security → Windows Security → App & browser control → Smart App Control settings**.)
2. Choose **Off**.
3. Double-click **Start PDF Scope** again.

> **Before you switch it off:** on many Windows 11 versions, once Smart App Control is turned off it
> **cannot be turned back on without resetting Windows**. Microsoft Defender antivirus and SmartScreen
> **stay on** and keep protecting your PC. Only turn it off if you trust where you got PDF//SCOPE from.

### "There is no script engine for file extension .vbs"
Newer Windows versions can remove VBScript. Turn it back on in **Settings → System → Optional features →
View features / More Windows features → VBScript**, then try again.

### Setup window flashes and closes / nothing happens
Look in the `logs` folder for `last-error.txt` or `setup.log` and send them.

---

# For developers

## Run

### Windows, one click (how it works)
On the first run of **`Start PDF Scope.vbs`**, a setup window (`launcher/setup.ps1`) takes care of the rest:
- **No Python 3.10+?** It offers to install Python 3.12 with winget, for your user only and without admin rights.
  Without winget, it opens python.org and explains the one installer checkbox that matters.
- **Builds `venv\` and installs the packages.** This needs internet once, about 100 MB.
- **Offers LibreOffice once.** It's optional and only needed for Word to PDF.

Later launches skip setup and start straight away. Setup runs again by itself when `requirements.txt` changes
(after a `git pull`, for example) or if `venv\` breaks.

The launcher then starts a small control helper with no console window and opens its page at http://127.0.0.1:8100.
Use **Start / Stop / Open / Quit** there. The app itself runs at http://127.0.0.1:8000.
The dashboard's **STOP** button also stops the server through the helper. Your files stay in the workspace.

Nothing starts at boot or login. Logs go to `logs/setup.log`, `logs/server.log` and `logs/launcher.log`.

Every launcher-stage failure has a `PS-xxx` code (table in the user guide above). The report is written to
`logs/last-error.txt`; `setup.ps1` and the `.vbs` also copy it to the clipboard, and the control page has a
**Copy error report** button. Codes are defined in `launcher/setup.ps1` (PS-1xx), `Start PDF Scope.vbs`
(PS-20x), `launcher/control.py` (PS-203, PS-3xx, PS-401) and `launcher/control.html` (PS-205).

### Any OS
```bash
pip install -r requirements.txt      # + install LibreOffice for Word to PDF
python run.py                        # http://127.0.0.1:8000
```
`HOST`, `PORT` and `RELOAD=1` change how `run.py` starts uvicorn.

LibreOffice is found on PATH or in its default Windows folder. For anywhere else, set `PDFSCOPE_SOFFICE` to the full `soffice` path.

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
| Pages | Remove (type a list or click pages) · add (blank, or pages from a PDF or image) · crop (drag the frame or type % / mm) · rotate 90/180/270° · reorder (drag the thumbnails, or type `3,1,2` / `reverse`) · merge PDFs and images onto the end · extract to PDF/JPEG/PNG/TXT |
| Versions | Every edit makes a new version (v1, v2…). Nothing is overwritten. Click a version to view it or make it current again. |
| Workspace | Drag-and-drop upload, page thumbnails, double-click to zoom, browse images inside zip results, rename, delete a file with all its versions, download any version |
| Compare | Old vs new: pages aligned by content, pixel diff overlay, blink mode, text diff |
| Share | Send the file itself to WhatsApp / Telegram / Gmail / mail app: through the device share menu (phones; Chrome or Edge on Windows 10/11), otherwise by downloading it and opening the app to attach it · expiring download links, which can be sent to apps once `PDFSCOPE_PUBLIC_URL` makes them reachable by others |
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
| `PDFSCOPE_SOFFICE` | auto | LibreOffice binary (default: `soffice` on PATH, then `Program Files\LibreOffice`) |
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
launcher/setup.ps1         first-run setup: Python, venv, packages, LibreOffice
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
