"""Synthetic held worker using the production parent-EOF watchdog."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, sys.argv[1])
from geojson import watch_parent_lifetime
watch_parent_lifetime()
print(json.dumps(dict(request=sys.argv[2], seq=1, stage="read", completed=0, total=1, unit="bytes")), flush=True)
time.sleep(120)
