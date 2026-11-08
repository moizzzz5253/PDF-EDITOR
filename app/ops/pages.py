import bisect
import re

import pymupdf

from ..errors import AppError
from ..pagespec import parse_pages
from .registry import operation

MM = 72 / 25.4


def open_pdf(ctx, path=None):
    path = path or ctx.src_path
    with ctx.tracer.step("INPUT", f"Read {path.name}",
                         "The selected version is read from the session workspace on disk. Nothing leaves the server.",
                         f"open('{path.name}','rb').read(5)") as s:
        with open(path, "rb") as f:
            head = f.read(8)
        s["detail"] = f"{path.stat().st_size:,} bytes, header={head!r}"
    with ctx.tracer.step("VALIDATE", "Check it really is a PDF",
                         "Every PDF starts with the bytes '%PDF-'. A wrong extension or a damaged download fails here, before any heavy work.",
                         "head.startswith(b'%PDF-')"):
        if not head.startswith(b"%PDF-"):
            raise AppError("E_NOT_PDF", "File is not a PDF",
                           f"The first bytes are {head!r}, a PDF must begin with b'%PDF-'. The file extension is not trustworthy - the content is something else.",
                           "Upload the original PDF again. If it is a Word/image file use the CONVERT tools.")
    with ctx.tracer.step("PARSE", "Parse document structure",
                         "PyMuPDF reads the cross-reference table (the PDF's index) and builds the page tree in memory.",
                         f"pymupdf.open('{path.name}')") as s:
        doc = pymupdf.open(path)
        if doc.needs_pass:
            raise AppError("E_PDF_ENCRYPTED", "PDF is password protected", "The document is encrypted; pages cannot be read without the password.", "Remove the password in the original app and re-upload.", status=422)
        s["detail"] = f"{len(doc)} page(s), PDF {doc.metadata.get('format', '?')}"
    return doc


def keep_pages(ctx, doc, keep):
    """Keep only the pages in `keep` (zero-based, in that order) without leaving dead links.

    doc.select() renumbers every surviving link and bookmark and drops the ones whose page
    is gone. A bookmark is a section heading, so instead of losing it we point it at the
    next page that is still there - "Chapter 4" still opens chapter 4 when its first page is removed.
    A section with no page left loses its bookmark (or keeps it as a plain heading if it has kept sub-bookmarks)."""
    toc = doc.get_toc(simple=False)
    first = {}
    for new, old in enumerate(keep):
        first.setdefault(old, new)
    lost = [t for t in toc if t[2] >= 1 and t[2] - 1 not in first]
    with ctx.tracer.step("TRANSFORM", f"Keep {len(keep)} page(s), repair links",
                         "doc.select() rebuilds the page tree from the pages you keep. Links and bookmarks that point at kept pages are renumbered; "
                         "links to removed pages are deleted so nothing is left that clicks to nowhere. "
                         "Bookmarks whose page was removed are moved to the next kept page of the same section.",
                         f"doc.select({len(keep)} pages); doc.set_toc(redirected)") as s:
        doc.select(keep)
        s["detail"] = f"{len(toc)} bookmark(s)"
        if not lost:
            return
        kept = sorted(first)
        rows, moved = [], 0
        for n_, (lvl, title, pno, dest) in enumerate(toc):
            if pno >= 1 and pno - 1 not in first:
                # the section runs until the next bookmark at the same or a higher level
                end = next((t[2] - 1 for t in toc[n_ + 1:] if t[0] <= lvl and t[2] - 1 > pno - 1), float("inf"))
                i = bisect.bisect_right(kept, pno - 1)
                if i < len(kept) and kept[i] < end:
                    dest = {k: v for k, v in dest.items() if k in ("color", "bold", "italic", "collapse")}
                    dest["kind"] = pymupdf.LINK_GOTO
                    pno = first[kept[i]] + 1
                    moved += 1
                else:
                    pno = None
            elif pno >= 1:
                pno = first[pno - 1] + 1
            rows.append([lvl, title, pno, dest])
        # drop sections with nothing left, unless a sub-bookmark survives (then keep a heading with no target)
        fixed, child_kept = [], {}
        for lvl, title, pno, dest in reversed(rows):
            has_child = any(v for k, v in child_kept.items() if k > lvl)
            child_kept = {k: v for k, v in child_kept.items() if k <= lvl}
            if pno is None and has_child:
                pno, dest = -1, {"kind": pymupdf.LINK_NONE}
            if pno is not None:
                fixed.append([lvl, title, pno, dest])
            child_kept[lvl] = child_kept.get(lvl, False) or pno is not None or has_child
        fixed.reverse()
        s["detail"] = f"{len(toc)} bookmark(s): {moved} moved to the next kept page, {len(toc) - len(fixed)} dropped (section fully removed)"
        doc.set_toc(fixed, collapse=0)


URLISH = re.compile(r"^(https?://|www\.|wa\.me/|mailto:)", re.I)


def fix_launch_urls(doc):
    """Word sometimes stores web addresses as 'launch a file' actions, which viewers block. Turn them back into web links."""
    n = 0
    for page in doc:
        for l in page.get_links():
            f = (l.get("file") or "").strip()
            if l["kind"] == pymupdf.LINK_LAUNCH and URLISH.match(f):
                page.delete_link(l)
                uri = f if re.match(r"^(https?:|mailto:)", f, re.I) else "https://" + f
                page.insert_link({"kind": pymupdf.LINK_URI, "from": l["from"], "uri": uri})
                n += 1
    return n


def save_pdf(ctx, doc, out):
    with ctx.tracer.step("WRITE", "Write new PDF version",
                         "The edited page tree is serialised to a new file. garbage=1 drops objects no page uses any more (removed pages, their images and fonts), "
                         "deflate compresses streams and object streams pack the small objects, so the file stays as compact as the original. "
                         "(garbage=3 also hunts for duplicate objects, which takes hours on documents with thousands of pages.) "
                         "The previous version is kept untouched so you can compare or roll back.",
                         f"doc.save('{out.name}', garbage=1, deflate=True, use_objstms=1)") as s:
        fixed = fix_launch_urls(doc)
        doc.save(out, garbage=1, deflate=True, use_objstms=1)
        s["detail"] = f"{out.stat().st_size:,} bytes" + (f", {fixed} launch link(s) turned into web links" if fixed else "")
    with ctx.tracer.step("VERIFY", "Re-open the output to prove it is valid",
                         "A file that was written is not necessarily a file that opens. We re-open it, count the pages, and check that every internal link and bookmark points at a real page.",
                         f"pymupdf.open('{out.name}').page_count; page.get_links(); get_toc()") as s:
        chk = pymupdf.open(out)
        if chk.page_count != len(doc):
            raise AppError("E_VERIFY", "Output page count mismatch", f"Expected {len(doc)} pages, re-opened file has {chk.page_count}.", "This is a bug - copy the diagnostic report.", status=500)
        links = dead = 0
        for page in chk:
            for l in page.get_links():
                if l["kind"] in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED):
                    links += 1
                    dead += not 0 <= l.get("page", -1) < chk.page_count
        toc = chk.get_toc(simple=False)
        bad_bm = sum(1 for t in toc if t[2] < 1 and t[3].get("kind") == pymupdf.LINK_GOTO)
        s["detail"] = f"{chk.page_count} page(s) confirmed, {links} internal link(s), {len(toc)} bookmark(s)"
        if dead or bad_bm:
            s["detail"] += f" - WARNING: {dead} link(s) and {bad_bm} bookmark(s) point nowhere"
        chk.close()


@operation("remove_pages", "Remove pages", "PAGES", "Delete the pages you list (or click them in the page view).",
           params=[{"name": "pages", "type": "pages", "label": "Pages to remove", "default": "", "required": True, "help": "e.g. 2,4-6 or last"}])
def remove_pages(ctx):
    doc = open_pdf(ctx)
    n = len(doc)
    with ctx.tracer.step("VALIDATE", "Resolve page list",
                         "The text you typed is turned into zero-based page indexes and checked against the page count.",
                         f"parse_pages('{ctx.params.get('pages')}', n={n})") as s:
        rm = parse_pages(ctx.params.get("pages"), n, required=True, sort=True)
        s["detail"] = "remove indexes " + str(rm)
        if len(rm) >= n:
            raise AppError("E_REMOVE_ALL", "Cannot remove every page",
                           f"You selected all {n} page(s). A PDF with zero pages is invalid.",
                           "Leave at least one page, or delete the file instead.")
    kept = [i for i in range(n) if i not in set(rm)]
    keep_pages(ctx, doc, kept)
    out = ctx.out("out.pdf")
    save_pdf(ctx, doc, out)
    return {"mode": "version", "path": out, "message": f"Removed {len(rm)} page(s)",
            "page_map": [{"from": i, "state": "kept"} for i in kept], "removed": rm, "kind": "pdf"}


@operation("add_pages", "Add pages", "PAGES", "Insert blank pages, or pages from another PDF / an image.",
           params=[
               {"name": "source", "type": "select", "label": "What to add", "default": "blank", "options": ["blank", "file"]},
               {"name": "insert", "type": "file", "label": "PDF or image", "accept": "application/pdf,image/png,image/jpeg", "ws": True, "show_if": {"source": "file"}},
               {"name": "insert_pages", "type": "pages", "label": "Pages from that file", "default": "all", "show_if": {"source": "file"}},
               {"name": "blank_count", "type": "int", "label": "How many blank pages", "default": 1, "min": 1, "max": 100, "show_if": {"source": "blank"}},
               {"name": "position", "type": "select", "label": "Where", "default": "end", "options": ["start", "end", "after"]},
               {"name": "after_page", "type": "int", "label": "After page number", "default": 1, "min": 1, "show_if": {"position": "after"}},
           ])
def add_pages(ctx):
    p = ctx.params
    doc = open_pdf(ctx)
    n = len(doc)
    with ctx.tracer.step("VALIDATE", "Work out insert position",
                         "'start' = before page 1, 'end' = after the last page, 'after' = after the page number you give. Internally this is a zero-based index.",
                         "at = {'start':0,'end':n,'after':after_page}[position]") as s:
        pos = p.get("position", "end")
        at = 0 if pos == "start" else n if pos == "end" else int(p.get("after_page", 1))
        if at < 0 or at > n:
            raise AppError("E_PAGE_RANGE", f"Page {at} is outside the document", f"Document has {n} page(s); you asked to insert after page {at}.", f"Choose 1-{n}.")
        s["detail"] = f"insert at index {at}"
    if p.get("source", "blank") == "blank":
        cnt = int(p.get("blank_count", 1))
        ref = doc[min(max(at - 1, 0), n - 1)].rect
        with ctx.tracer.step("TRANSFORM", f"Insert {cnt} blank page(s)",
                             "Blank pages copy the width/height of the neighbouring page so the document keeps a consistent size.",
                             f"doc.new_page(pno=at+i, width={ref.width:.0f}, height={ref.height:.0f})"):
            for i in range(cnt):
                doc.new_page(pno=at + i, width=ref.width, height=ref.height)
        added = cnt
    else:
        files = ctx.file_param("insert")
        if not files:
            raise AppError("E_NO_INPUT", "No file to insert", "'File' was selected but no upload or workspace PDF was chosen.", "Pick a file in the form.")
        with ctx.tracer.step("PARSE", f"Open insert file {files[0].name}",
                             "The file being inserted is parsed too. Images are first turned into a one-page PDF so everything can be treated the same way.",
                             "src = pymupdf.open(path); src.convert_to_pdf() if image") as s:
            try:
                src = pymupdf.open(files[0])
                if not src.is_pdf:
                    src = pymupdf.open("pdf", src.convert_to_pdf())
            except Exception as e:
                raise AppError("E_BAD_INSERT", "The file to insert could not be read", f"{type(e).__name__}: {e}", "Use a valid PDF, JPEG or PNG.")
            s["detail"] = f"{len(src)} page(s) available"
        idx = parse_pages(p.get("insert_pages"), len(src))
        with ctx.tracer.step("TRANSFORM", f"Copy {len(idx)} page(s) in",
                             "Pages are copied object-by-object (fonts, images and all) into this document at the chosen position. "
                             "They are copied in one go, so links between the inserted pages keep working.",
                             f"src.select({idx}); doc.insert_pdf(src, start_at=at)"):
            src.select(idx)
            doc.insert_pdf(src, start_at=at)
        added = len(idx)
    out = ctx.out("out.pdf")
    save_pdf(ctx, doc, out)
    pm = [{"from": i, "state": "kept"} for i in range(at)] + [{"from": None, "state": "new"}] * added + \
         [{"from": i, "state": "kept"} for i in range(at, n)]
    return {"mode": "version", "path": out, "message": f"Added {added} page(s) after page {at}", "page_map": pm, "removed": [], "kind": "pdf"}


@operation("crop_pages", "Crop pages", "PAGES", "Trim margins off selected pages. Drag the frame on the preview, or type values.",
           params=[
               {"name": "pages", "type": "pages", "label": "Pages", "default": "all"},
               {"name": "unit", "type": "select", "label": "Unit", "default": "percent", "options": ["percent", "mm"]},
               {"name": "top", "type": "float", "label": "Trim top", "default": 0, "min": 0},
               {"name": "right", "type": "float", "label": "Trim right", "default": 0, "min": 0},
               {"name": "bottom", "type": "float", "label": "Trim bottom", "default": 0, "min": 0},
               {"name": "left", "type": "float", "label": "Trim left", "default": 0, "min": 0},
           ])
def crop_pages(ctx):
    p = ctx.params
    doc = open_pdf(ctx)
    n = len(doc)
    idx = parse_pages(p.get("pages"), n)
    unit = p.get("unit", "percent")
    t, r, b, l = (float(p.get(k) or 0) for k in ("top", "right", "bottom", "left"))
    if min(t, r, b, l) < 0:
        raise AppError("E_CROP_NEG", "Negative crop value", "Crop amounts must be zero or positive.", "Use values >= 0.")
    if not any((t, r, b, l)):
        raise AppError("E_CROP_ZERO", "Nothing to crop", "All four margins are 0, so the page would not change.", "Enter at least one margin or drag the frame.")
    insets = {}
    with ctx.tracer.step("TRANSFORM", f"Set crop box on {len(idx)} page(s)",
                         "Cropping does not delete content. It sets the page's CropBox - a window that viewers must respect. "
                         "(The hidden content is still inside the file; true redaction is a separate planned feature.)",
                         "page.set_cropbox(Rect(x0+left, y0+top, x1-right, y1-bottom))") as s:
        for i in idx:
            pg = doc[i]
            R = pg.rect
            if unit == "percent":
                dt, dr, db, dl = t / 100 * R.height, r / 100 * R.width, b / 100 * R.height, l / 100 * R.width
            else:
                dt, dr, db, dl = t * MM, r * MM, b * MM, l * MM
            new_w, new_h = R.width - dl - dr, R.height - dt - db
            if new_w < 20 or new_h < 20:
                raise AppError("E_CROP_TOO_LARGE", f"Crop leaves nothing on page {i + 1}",
                               f"Page {i + 1} is {R.width:.0f}x{R.height:.0f}pt. Trimming {dl + dr:.0f}pt horizontally and {dt + db:.0f}pt vertically leaves {new_w:.0f}x{new_h:.0f}pt (minimum 20pt).",
                               "Reduce the margins.")
            visible = pymupdf.Rect(R.x0 + dl, R.y0 + dt, R.x1 - dr, R.y1 - db)
            # set_cropbox wants unrotated coordinates measured from the media box, not from the current crop
            vis = visible * pg.derotation_matrix
            cb = pg.cropbox
            pg.set_cropbox(pymupdf.Rect(vis.x0 + cb.x0, vis.y0 + cb.y0, vis.x1 + cb.x0, vis.y1 + cb.y0))
            insets[i] = [round(dt / R.height * 100, 2), round(dr / R.width * 100, 2), round(db / R.height * 100, 2), round(dl / R.width * 100, 2)]
        s["detail"] = f"inset % (top,right,bottom,left) first page: {insets[idx[0]]}"
    out = ctx.out("out.pdf")
    save_pdf(ctx, doc, out)
    return {"mode": "version", "path": out, "message": f"Cropped {len(idx)} page(s)",
            "page_map": [{"from": i, "state": "cropped" if i in insets else "kept", "inset": insets.get(i)} for i in range(n)],
            "removed": [], "kind": "pdf"}


@operation("extract_pages", "Extract pages", "PAGES", "Copy chosen pages into a brand-new file (PDF, JPEG, PNG or text). The original is untouched.",
           params=[
               {"name": "pages", "type": "pages", "label": "Pages to extract", "default": "", "required": True},
               {"name": "format", "type": "select", "label": "Output", "default": "pdf", "options": ["pdf", "jpeg", "png", "txt"]},
               {"name": "dpi", "type": "int", "label": "DPI", "default": 150, "min": 30, "max": 600, "show_if": {"format": ["jpeg", "png"]}},
           ])
def extract_pages(ctx):
    from .convert import render_pages, package_images
    p = ctx.params
    doc = open_pdf(ctx)
    idx = parse_pages(p.get("pages"), len(doc), required=True)
    fmt = p.get("format", "pdf")
    if fmt == "pdf":
        # the source file on disk is untouched; only this in-memory copy is cut down
        keep_pages(ctx, doc, idx)
        out = ctx.out("extract.pdf")
        save_pdf(ctx, doc, out)
        res = {"path": out, "name": f"{ctx.base}-extract.pdf", "kind": "pdf"}
    elif fmt == "txt":
        with ctx.tracer.step("TRANSFORM", "Read text layer",
                             "Text is read from the PDF's text objects. Scanned pages have no text layer and come out empty - that needs OCR (not built yet).",
                             "page.get_text('text')") as s:
            parts = [f"--- page {i + 1} ---\n{doc[i].get_text('text')}" for i in idx]
            s["detail"] = f"{sum(len(x) for x in parts):,} characters"
        out = ctx.out("extract.txt")
        with ctx.tracer.step("WRITE", "Write text file", "UTF-8 text file.", "Path.write_text()"):
            out.write_text("\n".join(parts), encoding="utf-8")
        res = {"path": out, "name": f"{ctx.base}-extract.txt", "kind": "other"}
    else:
        paths = render_pages(ctx, doc, idx, int(p.get("dpi", 150)), fmt, 85, ctx.tmp, ctx.base)
        res = package_images(ctx, paths, ctx.base, fmt)
    res.update(mode="new_file", message=f"Extracted {len(idx)} page(s) to {fmt.upper()}", highlight=idx)
    return res
