"""Phase 1 page tools: rotate, reorder, merge.

Each function is one feature. The @operation decorator registers it, the dashboard
builds its form from `params`, and the tracer shows every step in the signal-flow view.
"""
import re

import pymupdf

from ..errors import AppError
from ..pagespec import parse_pages
from .pages import open_pdf, save_pdf
from .registry import operation

ANGLES = ["90", "180", "270"]
ACCEPT_MERGE = "application/pdf,image/png,image/jpeg"


@operation("rotate_pages", "Rotate pages", "PAGES",
           "Turn pages 90, 180 or 270 degrees. Use it for sideways scans.",
           params=[
               {"name": "pages", "type": "pages", "label": "Pages", "default": "all", "help": "all, or e.g. 1,3-5"},
               {"name": "angle", "type": "select", "label": "Clockwise turn", "default": "90", "options": ANGLES},
           ])
def rotate_pages(ctx):
    doc = open_pdf(ctx)
    n = len(doc)
    with ctx.tracer.step("VALIDATE", "Resolve page list",
                         "The page text is turned into zero-based indexes and checked against the page count.",
                         f"parse_pages('{ctx.params.get('pages')}', n={n})") as s:
        idx = parse_pages(ctx.params.get("pages"), n, sort=True)
        angle = int(ctx.params.get("angle") or 90)
        if angle not in (90, 180, 270):
            raise AppError("E_ANGLE", "Unsupported angle", f"Got {angle} degrees; only 90, 180 and 270 are offered.", "Choose one of the listed angles.")
        s["detail"] = f"{len(idx)} page(s), +{angle}°"
    with ctx.tracer.step("TRANSFORM", f"Turn {len(idx)} page(s)",
                         "Rotation is a page attribute (/Rotate). The page content is not redrawn, so this is lossless and fast.",
                         f"page.set_rotation((page.rotation + {angle}) % 360)"):
        for i in idx:
            page = doc[i]
            page.set_rotation((page.rotation + angle) % 360)
    out = ctx.out("out.pdf")
    save_pdf(ctx, doc, out)
    return {"mode": "version", "path": out, "message": f"Rotated {len(idx)} page(s) by {angle}°",
            "page_map": [{"from": i, "state": "kept"} for i in range(n)], "removed": [], "kind": "pdf"}


@operation("reorder_pages", "Reorder pages", "PAGES",
           "Set the new page order. Every page must appear exactly once.",
           params=[
               {"name": "order", "type": "text", "label": "New page order", "default": "", "required": True,
                "help": "e.g. 3,1,2 for three pages, or type reverse"},
           ])
def reorder_pages(ctx):
    doc = open_pdf(ctx)
    n = len(doc)
    raw = (ctx.params.get("order") or "").strip().lower()
    with ctx.tracer.step("VALIDATE", "Read the new order",
                         "The order must list every page number exactly once, so no page is lost or doubled.",
                         "sorted(order) == list(range(n))") as s:
        if not raw:
            raise AppError("E_ORDER", "No order given", "The new order field is empty.", f"Type all page numbers once, e.g. {','.join(str(i) for i in range(n, 0, -1))}.")
        if raw == "reverse":
            order = list(range(n - 1, -1, -1))
        else:
            try:
                order = [int(t) - 1 for t in re.split(r"[,\s]+", raw) if t]
            except ValueError:
                raise AppError("E_ORDER", "Order must be page numbers",
                               f"'{ctx.params.get('order')}' contains something that is not a page number.",
                               "Use numbers separated by commas, e.g. 3,1,2.")
            if sorted(order) != list(range(n)):
                raise AppError("E_ORDER", "Order must list every page exactly once",
                               f"The file has {n} page(s). Your order has {len(order)} entr{'y' if len(order) == 1 else 'ies'} and they are not exactly 1 to {n}.",
                               f"Write each of 1 to {n} once, e.g. {','.join(str(i) for i in range(n, 0, -1))}.")
        s["detail"] = "new order " + ", ".join(str(i + 1) for i in order)
    with ctx.tracer.step("TRANSFORM", f"Rearrange {n} page(s)",
                         "doc.select() keeps the listed pages in the order given. Every page is listed, so none are dropped.",
                         f"doc.select({order})"):
        doc.select(order)
    out = ctx.out("out.pdf")
    save_pdf(ctx, doc, out)
    return {"mode": "version", "path": out, "message": f"Reordered {n} page(s)",
            "page_map": [{"from": i, "state": "kept"} for i in order], "removed": [], "kind": "pdf"}


def _open_any(ctx, path):
    """Open an uploaded PDF, or turn a JPEG/PNG into a one-page PDF first."""
    with ctx.tracer.step("PARSE", f"Open {path.name}",
                         "Images are turned into a one-page PDF first, so every input is handled the same way.",
                         f"pymupdf.open('{path.name}')") as s:
        try:
            src = pymupdf.open(path)
            if not src.is_pdf:
                src = pymupdf.open("pdf", src.convert_to_pdf())
        except Exception as e:
            raise AppError("E_BAD_MERGE_INPUT", f"{path.name} could not be read",
                           f"{type(e).__name__}: {e}", "Use a valid PDF, JPEG or PNG.")
        if src.needs_pass:
            raise AppError("E_PDF_ENCRYPTED", f"{path.name} is password protected",
                           "The file is encrypted, so its pages cannot be read.", "Remove the password in the original app and upload it again.", status=422)
        s["detail"] = f"{len(src)} page(s)"
    return src


@operation("merge_pdfs", "Merge PDFs", "PAGES",
           "Add PDFs or images to the end of the selected file. The selected file stays first.",
           params=[
               {"name": "extra", "type": "file", "label": "Files to add, in order", "accept": ACCEPT_MERGE, "multiple": True,
                "help": "Hold Ctrl to pick several. They are added in the order you select them."},
           ])
def merge_pdfs(ctx):
    extras = ctx.uploads.get("extra", [])
    if not extras:
        raise AppError("E_NO_INPUT", "No files to add",
                       "Merge needs at least one PDF or image besides the selected file.",
                       "Choose files in 'Files to add, in order'.")
    doc = open_pdf(ctx)
    base_n = len(doc)
    page_map = [{"from": i, "state": "kept"} for i in range(base_n)]
    for path in extras:
        src = _open_any(ctx, path)
        with ctx.tracer.step("TRANSFORM", f"Append {len(src)} page(s) from {path.name}",
                             "Pages are copied object-by-object (fonts and images included) to the end of the document.",
                             f"doc.insert_pdf(src)"):
            doc.insert_pdf(src)
        page_map += [{"from": None, "state": "new"} for _ in range(len(src))]
    out = ctx.out("out.pdf")
    save_pdf(ctx, doc, out)
    added = len(doc) - base_n
    return {"mode": "version", "path": out, "message": f"Merged {len(extras)} file(s): +{added} page(s)",
            "page_map": page_map, "removed": [], "kind": "pdf"}
