"""End-to-end API smoke test: python tests/smoke.py (server must be running)."""
import json, httpx
B = "http://127.0.0.1:8000"; A = "tests/assets/"
c = httpx.Client(base_url=B, timeout=180)
def up(name):
    return c.post("/api/files", files={"file": (name, open(A + name, "rb"))}).json()[0]
def op(oid, fid=None, params=None, files=None, v=None):
    data = {"params": json.dumps(params or {})}
    if fid: data["file_id"] = fid
    if v: data["version"] = str(v)
    r = c.post(f"/api/ops/{oid}", data=data, files=files or None).json()
    print(("OK  " if r["ok"] else "ERR ") + oid, r.get("message") or (r["error"]["code"] + " " + r["error"]["title"]), r.get("total_ms"))
    return r
pdf = up("sample.pdf"); print("uploaded", pdf["id"], pdf["versions"][0]["pages"], "pages")
r = op("remove_pages", pdf["id"], {"pages": "2,4"}); assert r["file"]["versions"][-1]["pages"] == 3, r
r = op("add_pages", pdf["id"], {"source": "blank", "blank_count": 2, "position": "after", "after_page": 1}); assert r["file"]["versions"][-1]["pages"] == 5
r = op("crop_pages", pdf["id"], {"pages": "1-2", "unit": "percent", "top": 10, "bottom": 5, "left": 5, "right": 5}); assert r["ok"]
r = op("extract_pages", pdf["id"], {"pages": "3,1", "format": "pdf"}); assert r["file"]["versions"][-1]["pages"] == 2
r = op("extract_pages", pdf["id"], {"pages": "1-2", "format": "txt"})
r = op("rotate_pages", pdf["id"], {"pages": "1", "angle": "90"}); assert r["ok"]
r = op("reorder_pages", pdf["id"], {"order": "reverse"}); assert r["file"]["versions"][-1]["pages"] == 5, r
op("reorder_pages", pdf["id"], {"order": "1,1"})
r = op("merge_pdfs", pdf["id"], {}, files=[("extra", open(A + "sample.pdf", "rb")), ("extra", open(A + "a.jpg", "rb"))])
v = r["file"]["versions"]; assert v[-1]["pages"] == v[-2]["pages"] + pdf["versions"][0]["pages"] + 1, v
r = op("pdf_to_image", pdf["id"], {"pages": "all", "format": "jpeg", "dpi": 80}); zipf = r["file"]; assert zipf["kind"] == "zip"
r = op("image_to_pdf", zipf["id"], {"page_size": "a4"}); assert r["file"]["versions"][0]["pages"] == 5
r = op("image_to_pdf", None, {"page_size": "fit"}, files=[("images", open(A + "a.jpg", "rb")), ("images", open(A + "b.png", "rb"))]); assert r["file"]["versions"][0]["pages"] == 2
r = op("add_pages", pdf["id"], {"source": "file", "position": "start"}, files=[("insert", open(A + "a.jpg", "rb"))]); assert r["ok"]
docx = up("sample.docx"); r = op("docx_to_pdf", docx["id"]); assert r["file"]["kind"] == "pdf"
op("remove_pages", pdf["id"], {"pages": "99"})
op("remove_pages", pdf["id"], {"pages": "1-100000"})
op("remove_pages", pdf["id"], {"pages": "abc"})
op("pdf_to_image", docx["id"], {})
f = c.get("/api/files").json(); cur = next(x for x in f if x["id"] == pdf["id"]); print("versions", [(v["n"], v["op"], v["pages"], v["size"]) for v in cur["versions"]])
cm = c.get("/api/compare", params={"fa": pdf["id"], "va": 1, "fb": pdf["id"], "vb": 3}).json(); print("compare", cm["counts"])
print(c.get("/api/compare/diff.png", params={"fa": pdf["id"], "va": 1, "pa": 0, "fb": pdf["id"], "vb": 3, "pb": 0}).status_code)
print(c.patch(f"/api/files/{pdf['id']}", json={"name": "bad/name.pdf"}).json()["error"]["code"])
print(c.patch(f"/api/files/{pdf['id']}", json={"name": "Renamed"}).json()["name"])
s = c.post(f"/api/files/{pdf['id']}/share", json={}).json(); print(s["url"], s["reachable"]); print(c.get(s["url"].replace(B, "")).status_code)
print(c.post(f"/api/files/{pdf['id']}/export/gdrive").json()["error"]["code"])
print(json.dumps(c.get("/api/system").json())[:300])
