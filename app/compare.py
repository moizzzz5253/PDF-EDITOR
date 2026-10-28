"""Old-vs-new comparison. Pages are aligned by content (not by number) so inserting
or deleting a page does not mark every following page as changed."""
import difflib
import hashlib
import io

import pymupdf
from PIL import Image, ImageChops

from .config import settings
from .errors import AppError


def _sig(page):
    text = " ".join(page.get_text("text").split())
    if text:
        return "t:" + hashlib.md5(text.encode()).hexdigest()
    pix = page.get_pixmap(dpi=20, colorspace=pymupdf.csGRAY)
    return "i:" + hashlib.md5(pix.samples).hexdigest()


def _thumb(page, dpi=50):
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def pixel_diff(pa, pb, dpi=50):
    a, b = _thumb(pa, dpi), _thumb(pb, dpi)
    if a.size != b.size:
        b = b.resize(a.size)
    d = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 24 else 0)
    changed = sum(1 for v in d.getdata() if v)
    return round(changed / (a.size[0] * a.size[1]) * 100, 2)


def diff_png(pa, pb, dpi=80):
    """Red = only in A (old), green = only in B (new), grey = unchanged."""
    a, b = _thumb(pa, dpi), _thumb(pb, dpi)
    if a.size != b.size:
        b = b.resize(a.size)
    ga, gb = a.convert("L"), b.convert("L")
    ink_a = ga.point(lambda v: 255 if v < 160 else 0)
    ink_b = gb.point(lambda v: 255 if v < 160 else 0)
    both = ImageChops.multiply(ink_a, ink_b)
    only_a = ImageChops.subtract(ink_a, ink_b)
    only_b = ImageChops.subtract(ink_b, ink_a)
    out = Image.new("RGB", a.size, "white")
    out.paste((190, 190, 190), mask=both)
    out.paste((230, 50, 70), mask=only_a)
    out.paste((20, 190, 110), mask=only_b)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def page_text_diff(pa, pb):
    ta = pa.get_text("text").splitlines() if pa else []
    tb = pb.get_text("text").splitlines() if pb else []
    return [l for l in difflib.unified_diff(ta, tb, "OLD", "NEW", lineterm="", n=1)]


def compare(path_a, path_b):
    A, B = pymupdf.open(path_a), pymupdf.open(path_b)
    if len(A) > settings.compare_max_pages or len(B) > settings.compare_max_pages:
        raise AppError("E_COMPARE_BIG", "Documents too large to compare",
                       f"Compare renders every page; limit is {settings.compare_max_pages} pages (A has {len(A)}, B has {len(B)}).",
                       "Extract the pages of interest first, or raise PDFSCOPE_COMPARE_MAX_PAGES.", status=413)
    sa, sb = [_sig(p) for p in A], [_sig(p) for p in B]
    rows = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rows.append({"a": i1 + k, "b": j1 + k, "status": "same", "pixel_pct": 0})
        elif tag == "delete":
            rows += [{"a": i, "b": None, "status": "removed"} for i in range(i1, i2)]
        elif tag == "insert":
            rows += [{"a": None, "b": j, "status": "added"} for j in range(j1, j2)]
        else:  # replace: pair up one-to-one, rest are removed/added
            m = min(i2 - i1, j2 - j1)
            for k in range(m):
                rows.append({"a": i1 + k, "b": j1 + k, "status": "changed", "pixel_pct": pixel_diff(A[i1 + k], B[j1 + k])})
            rows += [{"a": i, "b": None, "status": "removed"} for i in range(i1 + m, i2)]
            rows += [{"a": None, "b": j, "status": "added"} for j in range(j1 + m, j2)]
    def meta(d, p):
        return {"pages": len(d), "size": p.stat().st_size, "title": d.metadata.get("title") or "",
                "page_size": f"{d[0].rect.width:.0f}x{d[0].rect.height:.0f}pt" if len(d) else "-"}
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in ("same", "changed", "added", "removed")}
    return {"a": meta(A, path_a), "b": meta(B, path_b), "rows": rows, "counts": counts}
