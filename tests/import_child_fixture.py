"""Synthetic process faults; never exported with Editor."""
import json
import sys
import time
mode, token = sys.argv[1:3]
if mode == "wait":
    print(json.dumps(dict(request=token, seq=1, stage="read", completed=0, total=1, unit="bytes")),flush=True)
    time.sleep(60)
elif mode == "flood":
    print("x" * 20000,flush=True)
    time.sleep(60)
elif mode == "wrong-request":
    print(json.dumps(dict(request="b"*32, seq=1, stage="read", completed=0, total=1, unit="bytes")),flush=True)
    time.sleep(60)
elif mode == "partial":
    print('{"request":',end="",flush=True)
else:
    print("synthetic adapter crash",file=sys.stderr,flush=True)
    sys.exit(7)
