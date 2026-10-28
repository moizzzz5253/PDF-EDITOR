"""'1,3,5-8,last' -> [0,2,4,5,6,7,n-1]. Errors say which token was wrong and why."""
import re

from .errors import AppError


def parse_pages(spec, n, *, dedupe=True, required=False, sort=False):
    spec = (spec or "").strip().lower()
    if spec in ("", "all", "*"):
        if required and spec == "":
            raise AppError("E_PAGE_SPEC", "No pages selected",
                           "This operation needs a page list but the field was empty.",
                           "Type pages like 1,3,5-8 or click page thumbnails to select them.")
        return list(range(n))
    out = []
    for tok in re.split(r"[,\s;]+", spec):
        if not tok:
            continue
        m = re.fullmatch(r"(\d+|last)?(-)?(\d+|last)?", tok)
        if not m or not (m.group(1) or m.group(3)):
            raise AppError("E_PAGE_SPEC", f"Cannot read page token '{tok}'",
                           f"'{tok}' is not a number, a range like 3-7, or the word 'last'. Full input was: '{spec}'.",
                           "Use comma-separated numbers and ranges, e.g. 1,3,5-8,last")
        def val(x):
            return n if x == "last" else int(x)
        a, dash, b = m.group(1), m.group(2), m.group(3)
        if not dash:
            lo = hi = val(a)
        else:
            lo = val(a) if a else 1
            hi = val(b) if b else n
        for p in (lo, hi):
            if p < 1 or p > n:
                raise AppError("E_PAGE_RANGE", f"Page {p} is outside the document",
                               f"Token '{tok}' refers to page {p} but this document has {n} page(s) (valid: 1-{n}). Page numbers start at 1, not 0.",
                               f"Use numbers between 1 and {n}.", pages=n)
        step = 1 if lo <= hi else -1
        out.extend(range(lo - 1, hi - 1 + step, step))
    if dedupe:
        out = list(dict.fromkeys(out))
    return sorted(out) if sort else out
