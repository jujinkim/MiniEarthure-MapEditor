#!/usr/bin/env python3
"""Verify all shipped school-town cells with the public MapKit CLI.

Outputs are new, isolated evidence. This never rewrites a lock or source file.
"""
import argparse
import json
from pathlib import Path
import subprocess
import shutil
import time
from reference_maps import sha


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapkit",type=Path,required=True)
    parser.add_argument("--project",type=Path,default=Path(__file__).resolve().parents[1]/"examples/driving-school")
    parser.add_argument("--output",type=Path,required=True,help="new evidence directory")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cli=str(args.mapkit.resolve())
    def run(*command):
        result=subprocess.run([cli,*map(str,command)],capture_output=True,text=True,timeout=60)
        if result.returncode: raise RuntimeError(result.stderr or result.stdout)
        return result.stdout.strip()
    started=time.monotonic()
    # Freeze the input before generating many cells; edits during a long check
    # must never produce an evidence report mixing two different packages.
    package=args.output/"input.memap"
    shutil.copy2(args.project.with_suffix(".memap"),package)
    source_digest=sha((args.project/"document.json").read_bytes())
    inspection=json.loads(run("validate",package))
    regenerated=json.loads(run("pack",args.project,args.output/"regenerated.memap"))
    assert regenerated==inspection,"source must reproduce the shipped package exactly"
    document=json.loads((args.project/"document.json").read_text())
    size=document["cell_size_cm"]
    extent=document["bounds"]["max"]
    hashes={}
    for y in range((extent[1]+size-1)//size):
        for x in range((extent[0]+size-1)//size):
            target=args.output/f"cell-{x}-{y}.json"
            hashes[f"{x}/{y}"]=run("generate-chunk",package,x,y,target)
        print(f"school native cells: {len(hashes)}/{inspection['cell_count']}",flush=True)
    assert sha((args.project/"document.json").read_bytes())==source_digest,"source changed during verification"
    report=dict(source_sha256=source_digest,inspection=inspection,
                generated_cells=hashes,seconds=round(time.monotonic()-started,3))
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("check_driving_school: PASS",flush=True)


if __name__=="__main__": main()
