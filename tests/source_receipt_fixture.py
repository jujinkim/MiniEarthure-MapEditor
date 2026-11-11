"""Cross-language lossless receipt fixture; synthetic evidence only."""
from pathlib import Path
import json
import base64
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/"scripts/importers"))
import regional

path=Path(sys.argv[2])
if sys.argv[1]=="write":
    rows=[dict(source_id=f"way/{i}",style_id="building/modern/school/concrete",
               evidence=dict(height="source:height",material="context:profile"),label="학교") for i in range(1200)]
    packed=dict(objects=rows)
    regional.pack_rows(packed,"objects")
    path.write_text(regional.canonical(dict(expected=rows,packed=packed)))
elif sys.argv[1]=="verify":
    value=json.loads(path.read_text())
    assert base64.b64decode(value["packed"]["objects_blob"]["data"])[4:8]==bytes(4), "gzip mtime must not change output identity"
    assert regional.receipt_rows(value["packed"],"objects")==value["expected"]
else:
    raise ValueError("unknown fixture mode")
