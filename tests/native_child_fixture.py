"""Synthetic native supervisor faults; excluded from product exports."""
import hashlib
import json
from pathlib import Path
import sys
import time

mode, token, directory = sys.argv[1:4]
sequence = 0

def event(stage="source", completed=0, total=1, unit="bytes", **extra):
    global sequence
    sequence += 1
    print(json.dumps(dict(request=token, seq=sequence, stage=stage,
                          completed=completed, total=total, unit=unit, **extra)), flush=True)

if mode == "wrong-request":
    token = "0" * 32
    event()
elif mode == "regress":
    event(completed=1)
    event(completed=0)
elif mode == "over-cells":
    event()
    event("validate", 1, 1, "steps")
    event("snapshot")
    event("open", 1, 1, "steps")
    event("generate", 0, 17, "cells")
elif mode in ("zero-cells-success", "unexpected-cells"):
    event()
    event("validate", 1, 1, "steps")
    event("snapshot")
    event("open", 1, 1, "steps")
    count = 0 if mode == "zero-cells-success" else 1
    event("generate", count, count, "cells")
    source_bytes = json.loads((Path(directory) / "request.json").read_text())["layer"]["source"]["bytes"]
    event("recheck", source_bytes, source_bytes)
    output = json.dumps(dict(ok=True, request=token, payloads="0" * 64)).encode()
    (Path(directory) / "layer.json").write_bytes(output)
    event("complete", len(output), len(output), sha256=hashlib.sha256(output).hexdigest())
    sys.stdin.read(1)
    sys.exit(0)
elif mode == "flood":
    print("x" * 20000, flush=True)
elif mode == "partial":
    print('{"request":', end="", flush=True)
    sys.exit(0)
elif mode == "crash":
    sys.exit(7)
elif mode == "diagnostic":
    print("ERROR: synthetic native diagnostic", file=sys.stderr, flush=True)
    event()
elif mode in ("wrong-result", "premature-success", "invalid-error"):
    if mode == "premature-success":
        output = json.dumps(dict(ok=True, request=token, payloads="0" * 64)).encode()
    elif mode == "invalid-error":
        output = json.dumps(dict(ok=False, request=token)).encode()
    else:
        output = b'{"ok":true}'
    (Path(directory) / "layer.json").write_bytes(output)
    event("complete", len(output), len(output), sha256="0" * 64 if mode == "wrong-result" else hashlib.sha256(output).hexdigest())
    sys.stdin.read(1)
    sys.exit(0)
else:
    event()
time.sleep(60)  # Parent terminates deterministically; no test waits for this delay.
