"""Read-only page navigation data: bookmarks, links and per-page info.

Nothing here changes a file. Results are cached next to the version (versions never change
once written), so a 5,000-page document is scanned once and then served instantly.
"""
import json
import threading

import pymupdf

from .errors import AppError

_locks, _guard = {}, threading.Lock()  # one scan per cache file; a second request waits for it


def _pct(r, pr):
    return [round((r.x0 - pr.x0) / pr.width * 100, 2), round((r.y0 - pr.y0) / pr.height * 100, 2),
            round((r.x1 - pr.x0) / pr.width * 100, 2), round((r.y1 - pr.y0) / pr.height * 100, 2)]


def outline(path, cache):
    """{pages, bookmarks:[{level,title,page}], links:[{src,rect,kind,page|uri|file,text}]}; pages are zero-based."""
    with _guard:
        lock = _locks.setdefault(str(cache), threading.Lock())
    with lock:
        if cache.exists():
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except ValueError:
                pass  # damaged cache: rebuild it
        return _scan(path, cache)


def _scan(path, cache):
    try:
        doc = pymupdf.open(path)
    except Exception as e:
        raise AppError("E_NAV_OPEN", "Could not read this version for navigation", f"{type(e).__name__}: {e}", "Re-select the file; if it persists the version file is damaged.", status=422)
    n = len(doc)
    bookmarks = [{"level": lvl, "title": title, "page": pno - 1 if 1 <= pno <= n else None} for lvl, title, pno in doc.get_toc()]
    links, seen, broken = [], {}, 0
    for page in doc:
        try:
            pl = page.get_links()
            if not pl:
                continue
            # words once per page, matched to link boxes here: page.get_textbox() per link is ~50x slower
            pr, words = page.rect, page.get_text("words", flags=0)
            for l in pl:
                kind = l["kind"]
                if kind in (pymupdf.LINK_GOTO, pymupdf.LINK_NAMED):
                    tgt = l.get("page", -1)
                    item = {"kind": "page", "page": tgt if 0 <= tgt < n else None}
                elif kind == pymupdf.LINK_URI:
                    item = {"kind": "web", "uri": l.get("uri", "")}
                elif kind == pymupdf.LINK_LAUNCH:
                    item = {"kind": "file", "file": l.get("file", "")}
                else:
                    continue
                # link boxes come as displayed (rotation applied); words are in unrotated page space
                r = l["from"]
                f = r * page.derotation_matrix
                text = " ".join(w[4] for w in words if w[0] < f.x1 and w[2] > f.x0 and w[1] < f.y1 and w[3] > f.y0)[:160]
                # Word writes some links twice (a wide box and a narrow one): keep one per line and target
                key = (page.number, round(r.y0), item.get("page"), item.get("uri"), item.get("file"))
                if key in seen:
                    prev = links[seen[key]]
                    if len(text) > len(prev["text"]):
                        prev["text"], prev["rect"] = text, _pct(r, pr)
                    continue
                seen[key] = len(links)
                links.append({"src": page.number, "rect": _pct(r, pr), "text": text, **item})
        except Exception:
            broken += 1  # one unreadable page must not hide the rest
    out = {"pages": n, "bookmarks": bookmarks, "links": links, "skipped_pages": broken}
    try:
        cache.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return out


def page_info(path, i):
    """Page size in points (as displayed) and the box around everything drawn on it, as % insets [top,right,bottom,left]."""
    with pymupdf.open(path) as doc:
        if not 0 <= i < len(doc):
            raise AppError("E_PAGE_RANGE", "No such page", f"Page index {i} but the document has {len(doc)} page(s).", f"Use 0..{len(doc) - 1}", 404)
        page = doc[i]
        pr = page.rect
        box = pymupdf.Rect()
        for _, r in page.get_bboxlog():
            r = pymupdf.Rect(r) * page.rotation_matrix & pr
            # skip empty marks and full-page backgrounds, which would make the content box the whole page
            if r.is_empty or (r.width > pr.width * .97 and r.height > pr.height * .97):
                continue
            box |= r
        content = None
        if not box.is_empty:
            content = [round(max(0.0, (box.y0 - pr.y0) / pr.height * 100), 2), round(max(0.0, (pr.x1 - box.x1) / pr.width * 100), 2),
                       round(max(0.0, (pr.y1 - box.y1) / pr.height * 100), 2), round(max(0.0, (box.x0 - pr.x0) / pr.width * 100), 2)]
        return {"page": i, "width": round(pr.width, 2), "height": round(pr.height, 2), "content": content}
