import io
import shutil
import subprocess
import uuid
import zipfile
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from ..config import settings
from ..errors import AppError
from ..pagespec import parse_pages
from .registry import operation
from .pages import open_pdf, save_pdf


def render_pages(ctx, doc, idxs, dpi, fmt, quality, out_dir, stem):
    """Render pages -> list of image files. Returns paths."""
    paths = []
    with ctx.tracer.step("TRANSFORM", f"Rasterise {len(idxs)} page(s) @ {dpi} DPI",
                         f"Each PDF page is vector/text instructions. To get pixels, the page is drawn onto a bitmap of size "
                         f"(page_points/72 x {dpi}). Higher DPI = sharper but bigger file and slower.",
                         f"page.get_pixmap(dpi={dpi}, alpha=False)  # x{len(idxs)}") as s:
        pix_list = []
        for i in idxs:
            pix_list.append((i, doc[i].get_pixmap(dpi=dpi, alpha=False)))
        s["detail"] = f"{pix_list[0][1].width}x{pix_list[0][1].height}px first page"
    ext = "jpg" if fmt == "jpeg" else "png"
    with ctx.tracer.step("ENCODE", f"Encode as {fmt.upper()}",
                         ("JPEG throws away detail the eye misses (lossy) - quality sets how much. " if fmt == "jpeg" else
                          "PNG compresses without loss - larger files but pixel-perfect. ") + "Each bitmap is compressed to bytes.",
                         f"pix.save(path, jpg_quality={quality})" if fmt == "jpeg" else "pix.save(path)"):
        for i, pix in pix_list:
            p = out_dir / f"{stem}-p{i + 1:03d}.{ext}"
            if fmt == "jpeg":
                pix.save(p, jpg_quality=quality)
            else:
                pix.save(p)
            paths.append(p)
    return paths


def package_images(ctx, paths, stem, ext):
    """One image -> the image itself; several -> a zip."""
    with ctx.tracer.step("WRITE", "Package output",
                         "One page becomes a single image file; several pages are bundled into a .zip so you download one file.",
                         "zipfile.ZipFile(..., ZIP_STORED).write(...)" if len(paths) > 1 else "shutil.move(img, out)") as s:
        if len(paths) == 1:
            return {"path": paths[0], "name": paths[0].name, "kind": "image"}
        zp = ctx.out(f"{stem}-images.zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_STORED) as z:  # JPEG/PNG are already compressed
            for p in paths:
                z.write(p, p.name)
        s["detail"] = f"{len(paths)} images in zip"
        return {"path": zp, "name": zp.name, "kind": "zip"}


@operation("pdf_to_image", "PDF to JPEG/PNG", "CONVERT",
           "Turn pages into images. One page gives a single image, several give a zip.",
           params=[
               {"name": "pages", "type": "pages", "label": "Pages", "default": "all", "help": "e.g. 1,3,5-8 or all"},
               {"name": "format", "type": "select", "label": "Format", "default": "jpeg", "options": ["jpeg", "png"]},
               {"name": "dpi", "type": "int", "label": "DPI (sharpness)", "default": 150, "min": 30, "max": 600, "help": "72 = screen, 150 = good, 300 = print"},
               {"name": "quality", "type": "int", "label": "JPEG quality", "default": 85, "min": 10, "max": 100, "show_if": {"format": "jpeg"}},
           ])
def pdf_to_image(ctx):
    p = ctx.params
    doc = open_pdf(ctx)
    idxs = parse_pages(p.get("pages"), len(doc))
    dpi, q, fmt = int(p.get("dpi", 150)), int(p.get("quality", 85)), p.get("format", "jpeg")
    if dpi * len(idxs) > 600 * 400:
        raise AppError("E_TOO_HEAVY", "Request is too heavy", f"{len(idxs)} pages at {dpi} DPI would use too much memory/time.", "Lower DPI or select fewer pages.")
    paths = render_pages(ctx, doc, idxs, dpi, fmt, q, ctx.tmp, ctx.base)
    out = package_images(ctx, paths, ctx.base, fmt)
    out.update(mode="new_file", message=f"{len(paths)} page(s) converted to {fmt.upper()}", highlight=idxs)
    return out


@operation("image_to_pdf", "JPEG/PNG to PDF", "CONVERT",
           "Combine images into one PDF, in the order you pick them. You can also select an image or image-zip already in your workspace.",
           accepts=("image", "zip"), source="optional",
           params=[
               {"name": "images", "type": "file", "label": "Images", "accept": "image/png,image/jpeg", "multiple": True},
               {"name": "page_size", "type": "select", "label": "Page size", "default": "fit", "options": ["fit", "a4", "letter"],
                "help": "fit = page matches image; a4/letter = image centred with margin"},
               {"name": "margin", "type": "int", "label": "Margin (pt)", "default": 24, "min": 0, "max": 200, "show_if": {"page_size": ["a4", "letter"]}},
           ])
def image_to_pdf(ctx):
    p = ctx.params
    with ctx.tracer.step("INPUT", "Collect images",
                         "Images come from the upload field, or from the selected workspace file (an image, or a zip of images such as PDF to JPEG produces).",
                         "ctx.uploads['images'] or workspace file") as s:
        imgs = []  # (name, bytes)
        for up in ctx.uploads.get("images", []):
            imgs.append((up.name, up.read_bytes()))
        if not imgs and ctx.src_path:
            if ctx.src_path.suffix == ".zip":
                with zipfile.ZipFile(ctx.src_path) as z:
                    for n in sorted(z.namelist()):
                        if n.lower().endswith((".jpg", ".jpeg", ".png")):
                            imgs.append((n, z.read(n)))
            else:
                imgs.append((ctx.src_path.name, ctx.src_path.read_bytes()))
        s["detail"] = f"{len(imgs)} image(s)"
    if not imgs:
        raise AppError("E_NO_INPUT", "No images supplied", "No image was uploaded and no image/zip is selected in the workspace.", "Choose image files in the form, or select an image in the file list.")
    size = {"a4": (595, 842), "letter": (612, 792)}.get(p.get("page_size", "fit"))
    margin = int(p.get("margin", 24))
    doc = pymupdf.open()
    with ctx.tracer.step("TRANSFORM", "Place each image on its own page",
                         "A new empty PDF is created; per image we make a page and draw the picture on it. EXIF rotation (phone photos) is applied first so pictures are upright.",
                         "doc.new_page(width,height); page.insert_image(rect, stream=jpeg_bytes)") as s:
        for name, raw in imgs:
            try:
                im = Image.open(io.BytesIO(raw))
                im = ImageOps.exif_transpose(im)
                if im.mode in ("RGBA", "LA", "P"):
                    im = im.convert("RGBA")
                    bg = Image.new("RGB", im.size, "white")
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                else:
                    im = im.convert("RGB")
            except Exception as e:
                raise AppError("E_BAD_IMAGE", f"'{name}' is not a readable image",
                               f"Pillow could not decode it ({type(e).__name__}: {e}). It may be corrupt or a different format renamed to .jpg.",
                               "Open the file in an image viewer; if it fails there too, re-export it.")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=92)
            w, h = im.size
            if size:
                pw, ph = size
                if w > h and size:  # landscape image -> landscape page
                    pw, ph = ph, pw
                page = doc.new_page(width=pw, height=ph)
                box = pymupdf.Rect(margin, margin, pw - margin, ph - margin)
                scale = min(box.width / w, box.height / h)
                iw, ih = w * scale, h * scale
                cx, cy = pw / 2, ph / 2
                rect = pymupdf.Rect(cx - iw / 2, cy - ih / 2, cx + iw / 2, cy + ih / 2)
            else:
                pw, ph = w * 0.75, h * 0.75  # assume 96 px per inch
                page = doc.new_page(width=pw, height=ph)
                rect = page.rect
            page.insert_image(rect, stream=buf.getvalue())
        s["detail"] = f"{len(doc)} page(s)"
    out = ctx.out(f"{ctx.base if ctx.record else 'images'}-from-images.pdf")
    save_pdf(ctx, doc, out)
    return {"mode": "new_file", "path": out, "name": out.name, "kind": "pdf", "message": f"{len(imgs)} image(s) combined into a PDF"}


@operation("docx_to_pdf", "Word to PDF", "CONVERT",
           "Convert a .docx/.doc/.odt/.rtf document to PDF using LibreOffice running headless on the server.",
           accepts=("docx",),
           params=[])
def docx_to_pdf(ctx):
    exe = shutil.which(settings.soffice_bin)
    with ctx.tracer.step("VALIDATE", "Locate LibreOffice",
                         "Word files cannot be rendered by a PDF library - layout, fonts and tables need a full office engine. "
                         "The server calls LibreOffice in headless (no window) mode.",
                         f"shutil.which('{settings.soffice_bin}')") as s:
        if not exe:
            raise AppError("E_NO_SOFFICE", "LibreOffice is not installed on the server",
                           f"'{settings.soffice_bin}' was not found on PATH, so Word to PDF cannot run.",
                           "Install it (Ubuntu: apt install libreoffice-writer; Windows/macOS: install LibreOffice and set PDFSCOPE_SOFFICE to its soffice path).")
        s["detail"] = exe
    work = ctx.tmp / "lo"
    work.mkdir()
    src = work / ("input" + ctx.src_path.suffix)
    shutil.copy(ctx.src_path, src)
    profile = ctx.tmp / f"profile_{uuid.uuid4().hex[:6]}"
    cmd = [exe, f"-env:UserInstallation=file://{profile}", "--headless", "--convert-to", "pdf", "--outdir", str(work), str(src)]
    with ctx.tracer.step("TRANSFORM", "Run LibreOffice conversion",
                         "A throw-away LibreOffice profile is used so concurrent users do not lock each other. "
                         "The process is killed if it exceeds the timeout.",
                         "subprocess.run(['soffice','--headless','--convert-to','pdf',...], timeout=%ds)" % settings.soffice_timeout_s) as s:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.soffice_timeout_s)
        s["detail"] = f"exit={r.returncode}"
        result = work / "input.pdf"
        if r.returncode != 0 or not result.exists():
            raise AppError("E_CONVERT_FAILED", "LibreOffice did not produce a PDF",
                           f"Exit code {r.returncode}. stderr: {(r.stderr or r.stdout or 'empty').strip()[:400]}",
                           "Open the document in Word to check it is not corrupt or password protected, then retry.")
    out = ctx.out(f"{ctx.base}.pdf")
    shutil.move(result, out)
    shutil.rmtree(profile, ignore_errors=True)
    with ctx.tracer.step("WRITE", "Collect result", "The PDF produced in the scratch folder is moved into your workspace.", "shutil.move()"):
        pass
    return {"mode": "new_file", "path": out, "name": out.name, "kind": "pdf", "message": "Word document converted to PDF"}
