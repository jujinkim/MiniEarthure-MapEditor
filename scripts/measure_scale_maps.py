#!/usr/bin/env python3
"""Measure L02 source/package stages with the actual public MapKit CLI.

Run on an existing scale_maps source, writing evidence to a NEW directory.
Failures are recorded, never silently retried or treated as supported gameplay.
This is a development experiment, not a platform performance acceptance runner.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import struct
import subprocess
import sys
import time


def run(command, name, output, timeout):
    actual = ["/usr/bin/time", "-l", *command] if sys.platform == "darwin" else command
    log = output/(name+".log")
    started = time.monotonic()
    timed_out = False
    with log.open("xb") as stream:
        process = subprocess.Popen(actual,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid,signal.SIGTERM)
            try: code=process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                code=process.wait()
    text=log.read_text(errors="replace")
    rss=re.search(r"(\d+)\s+maximum resident set size",text)
    native=[]
    for line in text.splitlines():
        if line.startswith("{"):
            try:native.append(json.loads(line))
            except json.JSONDecodeError:pass
    result=dict(command=actual,exit_code=code,timed_out=timed_out,elapsed_s=time.monotonic()-started,
        peak_process_rss_bytes=int(rss[1]) if rss else None,log=log.name,native=native)
    (output/(name+".json")).write_text(json.dumps(result,indent=2)+"\n")
    return result


def accounting(path):
    # Read only the documented front index for byte accounting. No independent
    # geometry validation or audit claims: the actual CLI owns those stages.
    with path.open("rb") as stream:
        header=stream.read(48)
        if header[:8]!=b"MKREGN01":raise ValueError("Unexpected indexed format")
        length=struct.unpack("<Q",header[8:16])[0]
        if length>4*1024*1024:raise ValueError("Oversized front index")
        data=stream.read(length)
    if hashlib.sha256(data).digest()!=header[16:]:raise ValueError("Index digest mismatch")
    index=json.loads(data)
    records=index["records"]
    assets={record for name,record in index["payloads"].items() if name.startswith("assets/")}
    return dict(file_bytes=path.stat().st_size,file_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        index_bytes=length,expanded_all_records_bytes=sum(r["size"] for r in records),
        original_document_bytes=records[index["authoring_source"]]["size"],
        region_source_expanded_bytes=sum(records[r["source"]]["size"] for r in index["regions"]),
        asset_expanded_bytes=sum(records[i]["size"] for i in assets),
        asset_compressed_bytes=sum(records[i]["compressed_bytes"] for i in assets),
        payload_expanded_bytes=sum(records[i]["size"] for i in index["payloads"].values()),
        base_compressed_including_envelope_bytes=path.stat().st_size-sum(records[i]["compressed_bytes"] for i in assets),
        region_count=len(index["regions"]),world_content_hash=index["world_content_hash"],
        under_50mb=path.stat().st_size<=50000000,verification="accounting only; see native stages")


def measure(source,output,cli,sides,timeout):
    source,output,cli=Path(source).resolve(),Path(output).resolve(),Path(cli).resolve()
    summary=json.loads((source/"scale.json").read_text())
    # Fixed source hashes ensure experiments cannot accidentally use another map.
    for name,digest in summary["source_hashes"].items():
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:raise ValueError("Source changed: "+name)
    output.mkdir(parents=True,exist_ok=False)
    results=dict(source=str(source),source_identity=summary["source_hashes"]["document.json"],
        cli_sha256=hashlib.sha256(cli.read_bytes()).hexdigest(),condition=summary["condition"],size_m=summary["size_m"],variants={})
    for side in sides:
        package=output/f"side-{side}.mkregions"
        packed=run([str(cli),"pack-regions",str(source),str(package),str(side)],f"pack-{side}",output,timeout)
        variant=dict(pack=packed)
        results["variants"][str(side)]=variant
        if packed["exit_code"]==0 and not packed["timed_out"]:
            variant["accounting"]=accounting(package)
            variant["audits"]={}
            for limit in [536870912,1073741824]:
                variant["audits"][str(limit)]=run([str(cli),"audit-regions",str(package),str(limit)],f"audit-{side}-{limit}",output,timeout)
        (output/"measurements.json").write_text(json.dumps(results,indent=2)+"\n")
    return results


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source",type=Path);p.add_argument("output",type=Path)
    p.add_argument("--mapkit",type=Path,required=True)
    p.add_argument("--side-cells",type=int,nargs="+",default=[8,16])
    p.add_argument("--timeout",type=int,default=180)
    a=p.parse_args()
    if any(not 1<=side<=128 for side in a.side_cells) or len(set(a.side_cells))!=len(a.side_cells):p.error("unique storage cell sides 1..128 required")
    result=measure(a.source,a.output,a.mapkit,a.side_cells,a.timeout)
    print(json.dumps({k:dict(pack_exit=v["pack"]["exit_code"],accounting=v.get("accounting"),audits={n:r["exit_code"] for n,r in v.get("audits",{}).items()}) for k,v in result["variants"].items()},indent=2))
