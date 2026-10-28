"""Step tracer: every operation records what it did, the real call it made, and how
long it took. The UI replays these as the signal-flow animation and the log."""
import time
from contextlib import contextmanager

# Pipeline stages shown as nodes in the dashboard, in order.
NODES = ["INPUT", "VALIDATE", "PARSE", "TRANSFORM", "ENCODE", "WRITE", "VERIFY"]


class Tracer:
    def __init__(self, op):
        self.op = op
        self.steps = []
        self.t0 = time.perf_counter()

    @contextmanager
    def step(self, node, title, explain, call=""):
        s = {"node": node, "title": title, "explain": explain, "call": call,
             "status": "run", "ms": None, "detail": None}
        self.steps.append(s)
        t = time.perf_counter()
        try:
            yield s
        except BaseException as e:
            s["status"] = "error"
            s["ms"] = round((time.perf_counter() - t) * 1000, 2)
            s["detail"] = f"{type(e).__name__}: {e}"
            raise
        s["status"] = "ok"
        s["ms"] = round((time.perf_counter() - t) * 1000, 2)

    def total_ms(self):
        return round((time.perf_counter() - self.t0) * 1000, 2)
