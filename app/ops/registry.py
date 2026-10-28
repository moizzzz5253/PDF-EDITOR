import tempfile
from pathlib import Path

OPERATIONS = {}


def operation(id, label, group, desc, params=(), accepts=("pdf",), source="required"):
    """source: 'required' = needs a file selected in the workspace, 'none' = works from
    uploads only, 'optional' = either."""
    def deco(fn):
        OPERATIONS[id] = {"id": id, "label": label, "group": group, "desc": desc,
                          "params": list(params), "accepts": list(accepts), "source": source, "fn": fn}
        return fn
    return deco


class OpContext:
    def __init__(self, store, tracer, record, version, src_path, params, uploads):
        self.store, self.tracer, self.record, self.version = store, tracer, record, version
        self.src_path, self.params, self.uploads = src_path, params, uploads
        self.tmp = Path(tempfile.mkdtemp(prefix="op_", dir=store.root))

    @property
    def base(self):
        return Path(self.record["name"]).stem if self.record else "output"

    def out(self, name):
        return self.tmp / name

    def file_param(self, name):
        """Upload field first, otherwise a workspace file chosen in the dropdown."""
        if self.uploads.get(name):
            return self.uploads[name]
        ws = self.params.get(name + "_ws")
        if ws:
            rec = self.store.get(ws)
            return [self.store.version_path(rec, rec["current"])]
        return []
