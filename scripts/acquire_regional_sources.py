#!/usr/bin/env python3
"""Explicit authoring acquisition of bounded WorldCover/Overture snapshots.

This command alone uses the network. Generation consumes the resulting local
hash-bound descriptors; existing destinations are never overwritten.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import duckdb
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.windows import Window, from_bounds

RELEASE = "2026-10-21.0"
WORLD_ROOT = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
STAC_ROOT = "https://stac.overturemaps.org/"
WORLD_LICENSE = "CC-BY-4.0; © ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium"
OVERTURE_LICENSE = "Overture Maps Foundation; CDLA-Permissive-2.0 / ODbL-1.0 by source; individual sources retained in snapshot"


def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def digest(data): return hashlib.sha256(data).hexdigest()
def intersects(a,b): return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def get(url):
    with urlopen(Request(url,headers={"User-Agent":"MapEditor regional authoring/1"}),timeout=45) as response:
        data=response.read(16*1024*1024+1)
        if len(data)>16*1024*1024: raise ValueError("STAC metadata exceeds budget")
        return data


def stac_index(kind,cache):
    path=cache/f"overture-{kind}-files-{RELEASE}.json"
    if path.exists():
        value=json.loads(path.read_bytes())
        if value.get("version")!=1 or value.get("release")!=RELEASE:raise ValueError("invalid fixed-release STAC cache")
        return value
    url=f"{STAC_ROOT}{RELEASE}/buildings/{kind}/collection.json"
    raw=get(url);collection=json.loads(raw)
    urls=[urljoin(url,link["href"]) for link in collection["links"] if link["rel"]=="item"]
    def item(link):
        data=get(link);value=json.loads(data)
        return dict(url=link,sha256=digest(data),bbox=value["bbox"],assets=value["assets"])
    with ThreadPoolExecutor(max_workers=8) as pool:files=list(pool.map(item,urls))
    value=dict(version=1,release=RELEASE,catalog_url=url,catalog_sha256=digest(raw),files=files)
    cache.mkdir(parents=True,exist_ok=True)
    with path.open("xb") as stream:stream.write(canonical(value))
    return value


def worldcover(bounds,directory):
    windows=[];sources=[]
    west,south,east,north=bounds
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",GDAL_HTTP_TIMEOUT="45",GDAL_HTTP_CONNECTTIMEOUT="15"):
        for lat in range(3*math.floor(south/3),3*math.floor(north/3)+1,3):
            for lon in range(3*math.floor(west/3),3*math.floor(east/3)+1,3):
                tile=f"{'N' if lat>=0 else 'S'}{abs(lat):02d}{'E' if lon>=0 else 'W'}{abs(lon):03d}"
                url=WORLD_ROOT+f"ESA_WorldCover_10m_2021_v200_{tile}_Map.tif"
                with urlopen(Request(url,method="HEAD"),timeout=30) as head:etag=head.headers.get("ETag","")
                with rasterio.open(url) as src:
                    clipped=[max(west,src.bounds.left),max(south,src.bounds.bottom),min(east,src.bounds.right),min(north,src.bounds.top)]
                    if clipped[0]>=clipped[2] or clipped[1]>=clipped[3]:continue
                    raw=from_bounds(*clipped,transform=src.transform)
                    window=Window(math.floor(raw.col_off),math.floor(raw.row_off),math.ceil(raw.col_off+raw.width)-math.floor(raw.col_off),math.ceil(raw.row_off+raw.height)-math.floor(raw.row_off))
                    if window.width*window.height>4000000:raise ValueError("requested WorldCover crop exceeds authoring memory budget")
                    values=src.read(1,window=window)
                    target=directory/f"worldcover-part-{len(windows)}.tif"
                    profile=dict(driver="GTiff",width=values.shape[1],height=values.shape[0],count=1,dtype="uint8",crs=src.crs,transform=src.window_transform(window),compress="DEFLATE")
                    with rasterio.open(target,"w",**profile) as dst:dst.write(values,1)
                    windows.append(target);sources.append(dict(url=url,etag=etag,window=[window.col_off,window.row_off,window.width,window.height]))
        readers=[rasterio.open(p) for p in windows]
        try:
            values,affine=merge(readers,nodata=0,method="first")
            if values.size>4000000 or set(np.unique(values))-{10,20,30,40,50,60,70,80,90,95,100}:raise ValueError("WorldCover acquisition contains missing classes")
            target=directory/"worldcover-2021-v200.tif"
            with rasterio.open(target,"w",driver="GTiff",width=values.shape[2],height=values.shape[1],count=1,dtype="uint8",crs="EPSG:4326",transform=affine,compress="DEFLATE") as dst:dst.write(values)
        finally:
            for reader in readers:reader.close()
    # Only acquisition-owned intermediate crops are retired.
    for path in windows:path.unlink()
    return target,sources


def rows(connection,kind,bounds,cache):
    index=stac_index(kind,cache)
    selected=[f for f in index["files"] if intersects(f["bbox"],bounds)]
    if not selected:return [],dict(catalog_url=index["catalog_url"],catalog_sha256=index["catalog_sha256"],files=[])
    urls=[f["assets"]["aws"]["href"] for f in selected]
    wanted=["id","sources","level","height","min_height","is_underground","num_floors","min_floor","subtype","class","facade_color","facade_material","roof_material","roof_shape","roof_direction","roof_orientation","roof_color","roof_height","has_parts","building_id","version"]
    schema={row[0] for row in connection.execute("DESCRIBE SELECT * FROM read_parquet(?)",[urls]).fetchall()}
    required={"id","geometry","bbox","sources","height"}|({"building_id"} if kind=="building_part" else {"has_parts"})
    if not required<=schema:raise ValueError("Overture source schema is missing required fields")
    columns=[c for c in wanted if c in schema]
    select=",".join('"'+name+'"' for name in columns)
    west,south,east,north=bounds
    query=f"SELECT {select},ST_AsGeoJSON(geometry) AS geometry FROM read_parquet(?) WHERE bbox.xmin < ? AND bbox.xmax > ? AND bbox.ymin < ? AND bbox.ymax > ? ORDER BY id"
    cursor=connection.execute(query,[urls,east,west,north,south])
    result=[]
    while True:
        batch=cursor.fetchmany(1000)
        if not batch:break
        for row in batch:
            result.append(dict(type="Feature",geometry=json.loads(row[-1]),properties=dict(zip(columns,row[:-1]))))
        if len(result)>100000:raise ValueError("requested Overture crop exceeds 100000 footprints")
    receipt=dict(catalog_url=index["catalog_url"],catalog_sha256=index["catalog_sha256"],files=[dict(item_url=f["url"],item_sha256=f["sha256"],parquet_url=f["assets"]["aws"]["href"]) for f in selected])
    return result,receipt


def buildings(bounds,directory,cache):
    connection=duckdb.connect()
    connection.execute("LOAD httpfs");connection.execute("LOAD spatial")
    connection.execute("SET memory_limit='512MB'");connection.execute("SET threads=2");connection.execute("SET http_timeout=45")
    try:
        features,receipt=rows(connection,"building",bounds,cache)
        parents={f["properties"]["id"]:f for f in features if f["properties"].get("has_parts")}
        if parents:
            parts,part_receipt=rows(connection,"building_part",bounds,cache)
            receipt["parts"]=part_receipt
            for part in parts:
                props=part["properties"];parent=parents.get(props["building_id"])
                if parent is not None:parent["properties"].setdefault("parts",[]).append(dict(geometry=part["geometry"],**props))
            for parent in parents.values():
                if not parent["properties"].get("parts"):raise ValueError("Overture parts missing for "+parent["properties"]["id"])
                parent["properties"]["parts_complete"]=True
        value=dict(type="FeatureCollection",version=1,release=RELEASE,bbox=bounds,features=features,acquisition=receipt)
        target=directory/f"buildings-{RELEASE}.geojson"
        target.write_bytes(canonical(value))
        return target,receipt
    finally:connection.close()


def acquire(bounds,destination,cache):
    if destination.exists():raise ValueError("destination exists; choose a new snapshot directory")
    if len(bounds)!=4 or any(not math.isfinite(x) for x in bounds) or not -180<=bounds[0]<bounds[2]<=180 or not -80<=bounds[1]<bounds[3]<=84 or bounds[2]-bounds[0]>.2 or bounds[3]-bounds[1]>.2:raise ValueError("acquisition requires a valid WGS84 bbox at most .2 degrees per side")
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".regional-acquire-",dir=destination.parent) as scratch:
        directory=Path(scratch)/"snapshot";directory.mkdir()
        print("WorldCover native-grid crop",flush=True)
        wc,wc_receipt=worldcover(bounds,directory)
        print("Overture bounded building/part query",flush=True)
        ov,ov_receipt=buildings(bounds,directory,cache)
        descriptors={}
        for kind,path,release,url,license_name in (("worldcover",wc,"2021-v200",WORLD_ROOT,WORLD_LICENSE),("buildings",ov,RELEASE,f"{STAC_ROOT}{RELEASE}/buildings/",OVERTURE_LICENSE)):
            descriptors[kind]=dict(path=str(destination/path.name),sha256=digest(path.read_bytes()),release=release,bbox=bounds,source_url=url,license=license_name)
        (directory/"sources.json").write_bytes(canonical(dict(version=1,**descriptors)))
        (directory/"acquisition.json").write_bytes(canonical(dict(version=1,bbox=bounds,worldcover=wc_receipt,buildings=ov_receipt)))
        if destination.exists():raise ValueError("destination appeared during acquisition")
        directory.rename(destination)
    return descriptors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bbox",nargs=4,type=float,required=True);parser.add_argument("--destination",type=Path,required=True);parser.add_argument("--catalog-cache",type=Path,required=True)
    args=parser.parse_args();result=acquire(args.bbox,args.destination.absolute(),args.catalog_cache.absolute())
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
