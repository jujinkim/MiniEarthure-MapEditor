"""Bounded public Copernicus 2021 COG to explicitly authored local PNG16 terrain."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import time
import zlib
from import_layer import Progress, number, strict_json, soft_limit, limit_entries, limit_text
from projection import Coordinates
# DEM is optional: a region beyond these ceilings keeps its flat terrain. Above
# the former budgets (MAX_*) a DEM is still read and records limit warnings.
KEEP_FLAT = "; the map keeps its flat terrain (DEM is optional for multi-district regions)"

MAX_SOURCE = 64 * 1024 * 1024  # Warn above.
SOURCE_CEILING = 256 * 1024 * 1024  # A full float32 3600² tile decodes to ~49 MiB.
# Full-resolution COG blocks the bilinear support decodes, counted at review.
MAX_DECODE = 64 * 1024 * 1024  # Warn above.
DECODE_CEILING = 512 * 1024 * 1024
MAX_BLOCK = 2048 * 2048  # Warn above.
BLOCK_CEILING = 4096 * 4096
MAX_WINDOW = 1024 * 1024  # Warn above.
WINDOW_CEILING = 4096 * 4096  # Covers a whole tile.
MAX_REVIEW_AGE = 600  # Seconds; re-planning and hash checks still bind the review.
MAX_REQUEST = 16384  # Warn above.
REQUEST_CEILING = 1024 * 1024
LICENSE_URL = "https://copernicus-dem-30m.s3.amazonaws.com/readme.html#license"
NOTICE = "produced using Copernicus WorldDEM-{resolution} © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved"


def integer(value, name, low, high):
    value = number(value, name, low, high)
    if value != int(value): raise ValueError(name + " must be an integer")
    return int(value)


def grid(options, coordinates=None):
    if not isinstance(options, dict) or set(options) - {"osm_denominator"} != {"coordinates", "cell", "cell_size_cm", "map_min_cm", "spacing_cm", "vertical_zero_m", "source"}:
        raise ValueError("Invalid DEM options")
    if not isinstance(options["source"], str) or len(options["source"]) > 4096:
        raise ValueError("Invalid local COG path")
    denominator = options.get("osm_denominator", 1)
    if type(denominator) not in (int, float) or denominator not in (1, 8): raise ValueError("Invalid OSM import units")
    coordinates = Coordinates(options["coordinates"]) if coordinates is None else coordinates
    if coordinates.mode != "wgs84-utm": raise ValueError("DEM requires explicit WGS84/local origins")
    size = integer(options["cell_size_cm"], "cell size", 200, 102400)
    spacing = integer(options["spacing_cm"], "spacing", 200, size)
    if size % spacing or size // spacing + 1 > 513: raise ValueError("Spacing must divide cell; maximum 513 samples/side")
    for key in ("cell", "map_min_cm"):
        if not isinstance(options[key], list) or len(options[key]) != 2: raise ValueError("Invalid " + key)
        for value in options[key]: integer(value, key, 0 if key == "cell" else -100000000, 100000000)
    zero = number(options["vertical_zero_m"], "EGM2008 height at local zero", -10000, 10000)
    from pyproj.enums import TransformDirection
    side = size // spacing + 1
    # All sample positions are checked, not just an approximate geographic bbox.
    points = _grid_points(options, coordinates, denominator, size, spacing, side)
    if points is not None:
        west, south = math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points))
        return coordinates, side, points, [west, south], zero
    points = []
    for row in range(side):
        for col in range(side):
            local = [(options["map_min_cm"][i] + options["cell"][i] * size + (col if i == 0 else row) * spacing) / 100 for i in range(2)]
            dx, dy = [local[i] * denominator - coordinates.local[i] for i in range(2)]
            if math.hypot(dx, dy) > 20000: raise ValueError("DEM exceeds 20 km projection radius")
            lon, lat = coordinates.transformer.transform(coordinates.origin_xy[0]+dx, coordinates.origin_xy[1]+dy, direction=TransformDirection.INVERSE, errcheck=True)
            coordinates.point([lon, lat])  # same strip/hemisphere guard as vectors
            points.append((lon, lat))
    west, south = math.floor(min(p[0] for p in points)), math.floor(min(p[1] for p in points))
    return coordinates, side, points, [west, south], zero


def _grid_points(options, coordinates, denominator, size, spacing, side):
    """The scalar loop's exact arithmetic on arrays, or None to run that loop.

    Within a millimetre of a guard, or on any projection failure, the scalar loop
    runs instead so its first error and message stay exact."""
    try:
        import numpy as np
    except ImportError:
        return None
    from pyproj.enums import TransformDirection
    index = np.arange(side, dtype=np.float64)
    x = (options["map_min_cm"][0] + options["cell"][0] * size + index * spacing) / 100 * denominator - coordinates.local[0]
    y = (options["map_min_cm"][1] + options["cell"][1] * size + index * spacing) / 100 * denominator - coordinates.local[1]
    dx, dy = np.tile(x, side), np.repeat(y, side)
    if not (np.hypot(dx, dy) <= 20000 - 1e-3).all(): return None
    if not ((abs(dx + coordinates.local[0]) <= 100000 - 1e-3) & (abs(dy + coordinates.local[1]) <= 100000 - 1e-3)).all(): return None
    try:
        lon, lat = coordinates.transformer.transform(coordinates.origin_xy[0]+dx, coordinates.origin_xy[1]+dy, direction=TransformDirection.INVERSE, errcheck=True)
    except Exception:
        return None
    west = -180 + (coordinates.zone-1)*6
    if not (np.isfinite(lon) & np.isfinite(lat) & (lon >= west) & (lon <= west+6) & (lat >= -80) & (lat <= 84) & ((lat < 0) == coordinates.south)).all(): return None
    return list(zip(lon.tolist(), lat.tolist()))


def tile_filename(tile, resolution=30):
    lon, lat = tile
    name = f"Copernicus_DSM_COG_{'10' if resolution == 30 else '30'}_{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00_DEM"
    return name + ".tif"


def local_source(value, *, folder=False):
    path = Path(value)
    if not path.is_absolute(): raise ValueError("Select an absolute local COG path")
    # Validate before GDAL sees input; URI/VSI/virtual sources cannot trigger reads.
    if not (path.is_dir() if folder else path.is_file()):
        raise ValueError("Select an existing local COG folder" if folder else "Select an existing local COG file")
    return path


def identity(path):
    path = local_source(path)
    digest, count = hashlib.sha256(), 0
    with path.open("rb") as stream:
        while chunk := stream.read(65536):
            count += len(chunk)
            if count > SOURCE_CEILING: raise ValueError("DEM source exceeds 256 MiB" + KEEP_FLAT)
            digest.update(chunk)
    if not count: raise ValueError("Empty DEM")
    return {"bytes":count, "sha256":digest.hexdigest()}


def capture(review, partial, destination, progress):
    source = review["source"]
    expected = source["bytes"]
    digest, count = hashlib.sha256(), 0
    if set(source) != {"path", "bytes", "sha256", "decode"}: raise ValueError("Expected reviewed local DEM source")
    stream = local_source(source["path"]).open("rb")
    with stream:
        progress(0, expected)
        with partial.open("xb") as output:
            while chunk := stream.read(min(65536, expected+1-count)):
                count += len(chunk)
                if count > expected: raise ValueError("DEM exceeds reviewed bytes")
                output.write(chunk)
                digest.update(chunk)
                progress(count, expected)
            if count != expected or ("sha256" in source and digest.hexdigest() != source["sha256"]): raise ValueError("Truncated/changed DEM; review again")
            output.flush()
            os.fsync(output.fileno())
    os.link(partial, destination)  # exclusive; originals and completed captures survive errors
    return dict(source, captured_path=str(destination), sha256=digest.hexdigest(), bytes=count)


def raster_dependencies():
    try:
        import rasterio
        if rasterio.__version__ != "1.4.4": raise ImportError("version mismatch")
        import numpy as np
    except ImportError as exc:
        raise ValueError("DEM needs rasterio 1.4.4; install requirements-import.txt in selected Python") from exc
    return rasterio, np


def execute(request, scratch, progress):
    if request["mode"] == "dem-plan":
        progress("acquire", 0, 0)
        result = plan(request["options"])
        progress("sample", 0, 0)
        return result
    return execute_cells(request, scratch, progress)


MAX_MOSAIC_SAMPLES = 1025 * 1025  # Warn above.
MOSAIC_SAMPLES_CEILING = 4096 * 4096  # int64 heights: ~134 MB.
MAX_MOSAIC_SOURCES = 4  # Warn above.
MOSAIC_SOURCES_CEILING = 16
MAX_MOSAIC_CELLS = 256  # Warn above.
MOSAIC_CELLS_CEILING = 1024  # MapKit's 16,384-cell document limit stays separate.


def mosaic_grid(options):
    base = dict(options)
    counts = base.pop("cell_count")
    if not isinstance(counts, list) or len(counts) != 2:
        raise ValueError("DEM cell_count must be [columns, rows]")
    nx, ny = [integer(v, "cell count", 1, MOSAIC_CELLS_CEILING) for v in counts]
    if nx * ny > MOSAIC_CELLS_CEILING: raise ValueError("DEM exceeds 1024 candidate cells" + KEEP_FLAT)
    if nx * ny > MAX_MOSAIC_CELLS: soft_limit("dem_cells", nx * ny, MAX_MOSAIC_CELLS, "DEM covers many candidate cells; sampling takes longer")
    size = integer(base["cell_size_cm"], "cell size", 200, 102400)
    spacing = integer(base["spacing_cm"], "spacing", 200, size)
    sample_count = nx * ny * (size // spacing + 1) ** 2
    if sample_count > MOSAIC_SAMPLES_CEILING: raise ValueError("DEM mosaic exceeds 4096² samples" + KEEP_FLAT)
    if sample_count > MAX_MOSAIC_SAMPLES: soft_limit("dem_samples", sample_count, MAX_MOSAIC_SAMPLES, "DEM mosaic sample budget exceeded")
    cells, points, coordinates = [], [], None
    for y in range(ny):
        for x in range(nx):
            cell_options = dict(base, cell=[base["cell"][0]+x, base["cell"][1]+y])
            # Every cell shares one coordinate frame; build its transformer once.
            coordinates, side, cell_points, _, zero = grid(cell_options, coordinates)
            cells.append(cell_options["cell"])
            points.append(cell_points)
    # Conservative support envelope for the smallest admitted COG width (120).
    # Every listed source is reviewed; decoding later verifies exact support.
    flat = [p for group in points for p in group]
    west, east = math.floor(min(p[0] for p in flat)), math.floor(max(p[0] for p in flat)+1/120)
    south, north = math.floor(min(p[1] for p in flat)-1/1200), math.floor(max(p[1] for p in flat))
    tiles = [[x,y] for y in range(south,north+1) for x in range(west,east+1)]
    if len(tiles) > MOSAIC_SOURCES_CEILING: raise ValueError("DEM supports at most 16 source tiles including interpolation support" + KEEP_FLAT)
    if len(tiles) > MAX_MOSAIC_SOURCES: soft_limit("dem_tiles", len(tiles), MAX_MOSAIC_SOURCES, "DEM uses more than four source tiles")
    return coordinates, side, cells, points, tiles, zero


def plan(options):
    return _plan(options)[0]


def _plan(options):
    grid = mosaic_grid(options)
    coordinates, side, cells, groups, tiles, zero = grid
    selected = Path(options["source"])
    if not selected.is_absolute(): raise ValueError("Select an absolute local COG file or folder")
    folder = selected.is_dir()
    local_source(selected, folder=folder)
    if not folder and len(tiles) != 1:
        raise ValueError("Interpolation needs multiple source tiles; select a local folder")
    items, paths = [], []
    for tile in tiles:
        path = local_source(selected / tile_filename(tile) if folder else selected)
        size = path.stat().st_size
        if size > SOURCE_CEILING: raise ValueError("DEM source exceeds 256 MiB" + KEEP_FLAT)
        if size > MAX_SOURCE: soft_limit("dem_source_bytes", size, MAX_SOURCE, "DEM source tile exceeds 64 MiB")
        if not size: raise ValueError("Empty DEM")
        items.append(dict(tile=tile,resolution_m=30,fallback90=False))
        paths.append(path)
    # Only the blocks the reviewed samples touch count, never whole tile files.
    costs = decode_plan(paths, items, grid)
    decoded = sum(cost["decoded_bytes"] for cost in costs)
    if decoded > DECODE_CEILING:
        raise ValueError("DEM decode exceeds 512 MiB" + KEEP_FLAT)
    if decoded > MAX_DECODE: soft_limit("dem_decode_bytes", decoded, MAX_DECODE, "DEM decode budget exceeded")
    sources = []
    for item, path, cost in zip(items, paths, costs):
        source = dict(identity(path), path=str(path), decode=cost)
        sources.append(dict(item,source=source,notice=NOTICE.format(resolution=item["resolution_m"])))
    flat = [p for group in groups for p in group]
    return dict(adapter="copernicus-dem-v1",release="2021",license=LICENSE_URL,
                vertical_crs="EPSG:3855 / EGM2008 metres",surface="DSM including buildings and vegetation; not bare-earth DTM",
                projection=coordinates.metadata, bbox=[round(v,9) for v in [min(p[0] for p in flat),min(p[1] for p in flat),max(p[0] for p in flat),max(p[1] for p in flat)]],
                side=side,cells=cells,options=options,sources=sources,checked_at=int(time.time())), grid


def raster_env(rasterio):
    return rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_PAM_ENABLED="NO", GDAL_CACHEMAX=16*1024*1024)


def open_sources(stack, rasterio, paths, items):
    datasets = {}
    for path, item in zip(paths, items):
        ds = stack.enter_context(rasterio.open(local_source(path),driver="GTiff"))
        t = ds.transform
        h = 3600 if item["resolution_m"] == 30 else 1200
        tile = item["tile"]
        if ds.driver != "GTiff" or ds.crs != rasterio.crs.CRS.from_epsg(4326) or ds.count != 1 or ds.dtypes != ("float32",) or ds.height != h or not 120 <= ds.width <= h or t.b != 0 or t.d != 0 or t.a <= 0 or t.e >= 0 or ds.scales != (1.0,) or ds.offsets != (0.0,):
            raise ValueError("Expected unscaled north-up WGS84 float32 single-band 2021 COG")
        if abs(t.a*ds.width-1)>1e-8 or abs(-t.e*ds.height-1)>1e-8 or abs(t.c+t.a/2-tile[0])>1e-8 or abs(t.f+t.e/2-(tile[1]+1))>1e-8:
            raise ValueError("COG sample-centre/tile alignment mismatch")
        block = max(h*w for h,w in ds.block_shapes)
        if block>BLOCK_CEILING: raise ValueError("DEM decode block exceeds 4096²")
        if block>MAX_BLOCK: soft_limit("dem_block", block, MAX_BLOCK, "DEM decode block budget exceeded")
        datasets[tuple(tile)] = ds
    return datasets


def decode_cost(datasets, items, windows):
    """Distinct full-resolution blocks under the support windows, per source."""
    touched = {}
    for tx, ty, left, top, w, h in windows:
        bh, bw = datasets[(tx, ty)].block_shapes[0]
        blocks = touched.setdefault((tx, ty), set())
        for by in range(top//bh, (top+h-1)//bh+1):
            for bx in range(left//bw, (left+w-1)//bw+1): blocks.add((bx, by))
    costs = []
    for item in items:
        ds = datasets[tuple(item["tile"])]
        bh, bw = ds.block_shapes[0]
        size, compressed = os.stat(ds.name).st_size, 0
        for bx, by in sorted(touched.get(tuple(item["tile"]), ())):
            offset, length = ds.get_tag_item(f"BLOCK_OFFSET_{bx}_{by}","TIFF",bidx=1), ds.get_tag_item(f"BLOCK_SIZE_{bx}_{by}","TIFF",bidx=1)
            if offset is None or length is None or not offset.isdigit() or not length.isdigit() or int(offset) <= 0 or int(length) <= 0 or int(offset)+int(length) > size:
                raise ValueError("Invalid or sparse COG block layout")
            compressed += int(length)
        count = len(touched.get(tuple(item["tile"]), ()))
        costs.append(dict(block=[bw, bh], blocks=count, decoded_bytes=count*bw*bh*4, compressed_bytes=compressed))
    return costs


def decode_plan(paths, items, grid):
    from contextlib import ExitStack
    rasterio, np = raster_dependencies()
    with ExitStack() as stack:
        stack.enter_context(raster_env(rasterio))
        try:
            datasets = open_sources(stack, rasterio, paths, items)
        except rasterio.errors.RasterioIOError as exc:
            # Review reports a bounded message; local paths stay out of it.
            raise ValueError("Expected unscaled north-up WGS84 float32 single-band 2021 COG") from exc
        windows = []
        _sample(np, datasets, np.asarray([p for group in grid[3] for p in group],dtype=np.float64), windows, decode=False)
        return decode_cost(datasets, items, windows)


def _sample(np, datasets, flat, windows, decode=True):
    """Bilinear samples; without decode only the support windows are recorded."""
    from rasterio.windows import Window
    def union(tile, corners, depth):
        # One read for the four bilinear corners; per-corner guards still apply
        # and any corner that nodes() would refuse falls back to its own path.
        ds=datasets.get(tile)
        if depth>4 or ds is None: return None
        box=None
        for cols,rows in corners:
            if (cols<0).any() or (rows<0).any(): return None
            inside=(cols<ds.width)&(rows<ds.height)
            if not inside.any(): continue
            cc,rr=cols[inside],rows[inside]
            left,top,right,bottom=int(cc.min()),int(rr.min()),int(cc.max()),int(rr.max())
            if (right-left+1)*(bottom-top+1)>WINDOW_CEILING: return None
            box=(left,top,right,bottom) if box is None else (min(box[0],left),min(box[1],top),max(box[2],right),max(box[3],bottom))
        if box is None: return None
        window=Window(box[0],box[1],box[2]-box[0]+1,box[3]-box[1]+1)
        return box[0],box[1],ds.read(1,window=window),ds.read_masks(1,window=window)
    def nodes(tile, cols, rows, depth=0, block=None):
        if depth>4: raise ValueError("DEM interpolation support exceeds reviewed mosaic")
        ds=datasets.get(tile)
        if ds is None: raise ValueError("Missing DEM interpolation source")
        if (cols<0).any() or (rows<0).any(): raise ValueError("Invalid DEM interpolation index")
        out=np.empty(len(cols),dtype=np.float64)
        inside=(cols<ds.width)&(rows<ds.height)
        if inside.any():
            cc,rr=cols[inside],rows[inside]
            left,top=int(cc.min()),int(rr.min())
            w,h=int(cc.max()-left+1),int(rr.max()-top+1)
            if w*h>WINDOW_CEILING: raise ValueError("DEM decode window exceeds 4096²")
            if w*h>MAX_WINDOW: soft_limit("dem_window", w*h, MAX_WINDOW, "DEM decode window budget exceeded")
            if not decode:
                windows.append([*tile,left,top,w,h])
                out[inside]=0
            else:
                if block is None: block=(left,top,ds.read(1,window=Window(left,top,w,h)),ds.read_masks(1,window=Window(left,top,w,h)))
                x,y,data,valid=block
                windows.append([*tile,left,top,w,h])
                values=data[rr-y,cc-x]
                if not np.isfinite(values).all() or (valid[rr-y,cc-x]==0).any(): raise ValueError("Missing/non-finite DEM support; no zero filling")
                out[inside]=values
        # Across an edge, interpolate on the neighbor's own lattice. A
        # mixed-resolution corner can in turn require its south/east source;
        # recursion moves only east/south and never pads or wraps a tile.
        for ex,sy in [(1,0),(0,1),(1,1)]:
            selected=(cols//ds.width==ex)&(rows//ds.height==sy)
            if not selected.any(): continue
            neighbor=(tile[0]+ex,tile[1]-sy)
            nd=datasets.get(neighbor)
            if nd is None: raise ValueError("Missing DEM interpolation source")
            lon=tile[0]+cols[selected]/ds.width
            lat=tile[1]+1-rows[selected]/ds.height
            out[selected]=interpolate(neighbor,(lon-neighbor[0])*nd.width,(neighbor[1]+1-lat)*nd.height,depth+1)
        return out
    def interpolate(tile, cols, rows, depth=0):
        # Snap only floating reconstruction noise around an integer lattice
        # index (1e-8 pixel); retain all geographic sample precision.
        cols=np.where(abs(cols-np.rint(cols))<1e-8,np.rint(cols),cols)
        rows=np.where(abs(rows-np.rint(rows))<1e-8,np.rint(rows),rows)
        c0,r0=np.floor(cols).astype(int),np.floor(rows).astype(int)
        dx,dy=cols-c0,rows-r0
        c1=c0+(dx>0);r1=r0+(dy>0)
        corners=[(c0,r0),(c1,r0),(c0,r1),(c1,r1)]
        block=union(tile,corners,depth) if decode else None
        support=[nodes(tile,c,r,depth,block) for c,r in corners]
        return sum(v*w for v,w in zip(support,[(1-dx)*(1-dy),dx*(1-dy),(1-dx)*dy,dx*dy]))
    values = np.empty(len(flat),dtype=np.float64)
    for tile, ds in datasets.items():
        selected=np.flatnonzero((np.floor(flat[:,0])==tile[0])&(np.floor(flat[:,1])==tile[1]))
        if not len(selected): continue
        xy=flat[selected]
        values[selected]=interpolate(tile,(xy[:,0]-tile[0])*ds.width,(tile[1]+1-xy[:,1])*ds.height)
    return values


def mosaic_heights(paths, review, progress, grid=None):
    from contextlib import ExitStack
    paths = [local_source(path) for path in paths]
    rasterio, np = raster_dependencies()
    _, side, cells, groups, tiles, zero = mosaic_grid(review["options"]) if grid is None else grid
    with ExitStack() as stack:
        stack.enter_context(raster_env(rasterio))
        datasets = open_sources(stack, rasterio, paths, review["sources"])
        windows = []
        flat = np.asarray([p for group in groups for p in group],dtype=np.float64)
        values = _sample(np, datasets, flat, windows)
        if not np.isfinite(values).all() or (values < -1000).any() or (values > 10000).any(): raise ValueError("DEM elevation outside supported physical range")
        heights=np.rint((values-zero)*100 / review["options"].get("osm_denominator", 1)).astype(np.int64).reshape(len(cells),side,side)
        low,high=int(heights.min()),int(heights.max())
        step=max(1,math.ceil((high-low)/65535))
        if abs(low)>1000000 or high>1000000 or step>100: raise ValueError("Local height/PNG16 range exceeded")
        progress(len(flat),len(flat))
        return heights,dict(offset_cm=low,step_cm=step,source_accuracy_cm=None,vertical_zero_m=zero,
            resampling="bilinear across full-resolution COG sample centres; local rows +northing",
            quantization="shared nearest ties-to-even cm, then nearest PNG step",max_quantization_error_cm=0.5+step/2,
            source_windows=windows,rasterio=rasterio.__version__,gdal=rasterio.__gdal_version__)


def captured_cost(paths, items, windows):
    from contextlib import ExitStack
    rasterio, _ = raster_dependencies()
    with ExitStack() as stack:
        stack.enter_context(raster_env(rasterio))
        return decode_cost(open_sources(stack, rasterio, paths, items), items, windows)


def execute_cells(request,scratch,progress):
    review=request["plan"]
    age=time.time()-review["checked_at"]
    if age<0: raise ValueError("DEM review time is in the future; review again")
    current,grid=_plan(review["options"])
    # Re-planning and the source hash/decode checks bind the review, not its age.
    if age>MAX_REVIEW_AGE: soft_limit("dem_review_age", int(age), MAX_REVIEW_AGE, "DEM review is older than 10 minutes; sources were checked again")
    unbound=("checked_at","limit_warnings")
    if {k:v for k,v in current.items() if k not in unbound}!={k:v for k,v in review.items() if k not in unbound}: raise ValueError("DEM options/source changed; review again")
    current["checked_at"]=review["checked_at"]
    current.pop("limit_warnings",None)
    if "limit_warnings" in review: current["limit_warnings"]=review["limit_warnings"]
    review=current
    raster_dependencies()
    destination=Path(request["destination"])
    paths=[];captured=[];done=0;total=sum(s["source"]["bytes"] for s in review["sources"])
    for index,item in enumerate(review["sources"]):
        path=Path(str(destination)+f".source-{index}.tif")
        part=scratch/"source.tif.part"
        source=capture(item,part,path,lambda c,t:progress("acquire",done+c,total))
        part.unlink() # only this owned partial, completed hard link remains
        captured.append(dict(item,source=source));paths.append(path);done+=source["bytes"]
        with Path(str(path)+".json").open("x") as stream: json.dump(dict(review=review,source=captured[-1]),stream,sort_keys=True)
    receipt=dict(review,sources=captured)
    total=len(review["cells"])*review["side"]**2
    progress("sample",0,total)
    heights,metadata=mosaic_heights(paths,review,lambda c,t:progress("sample",c,t),grid)
    if captured_cost(paths,review["sources"],metadata["source_windows"])!=[s["source"]["decode"] for s in review["sources"]]:
        raise ValueError("DEM decode plan changed; review again")
    import numpy as np
    outputs=[]
    def chunk(kind,content): return struct.pack('>I',len(content))+kind+content+struct.pack('>I',zlib.crc32(kind+content))
    for index,cell in enumerate(review["cells"]):
        encoded=np.rint((heights[index]-metadata["offset_cm"])/metadata["step_cm"]).astype('>u2')
        raw=b"".join(b'\0'+row.tobytes() for row in encoded)
        side=review["side"]
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',side,side,16,0,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
        path=Path(str(destination)+f".cell-{index}.png")
        part=scratch/"dem.png.part"
        with part.open("xb") as stream:
            stream.write(png);stream.flush();os.fsync(stream.fileno())
        os.link(part,path);part.unlink()
        outputs.append(dict(cell=cell,png_path=str(path),png_sha256=hashlib.sha256(png).hexdigest(),png_bytes=len(png)))
    return dict(review=receipt,raster=metadata,outputs=outputs)

def main():
    from geojson import watch_parent_lifetime
    parser = argparse.ArgumentParser()
    parser.add_argument("request",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--layer-id",required=True)
    parser.add_argument("--watch-parent",action="store_true")
    args = parser.parse_args()
    if args.watch_parent: watch_parent_lifetime()
    request_size = args.request.stat().st_size
    if request_size > REQUEST_CEILING: raise ValueError("DEM request exceeds 1 MiB")
    if request_size > MAX_REQUEST: soft_limit("dem_request_bytes", request_size, MAX_REQUEST, "DEM request is large")
    request = strict_json(args.request.read_bytes())
    if request.get("mode") not in ("dem-plan","dem"): raise ValueError("Invalid DEM mode")
    progress = Progress(args.layer_id)
    def event(stage, completed, total, **extra):
        progress(stage, completed, total, "samples" if stage == "sample" else "bytes", **extra)
    result = execute(request,args.output.parent,event)
    if limit_entries():
        result["limit_warnings"] = [limit_text(entry) for entry in limit_entries()]
    encoded = json.dumps(result,sort_keys=True,allow_nan=False).encode()
    event("write",0,len(encoded))
    with args.output.open("xb") as stream: stream.write(encoded)
    event("write",len(encoded),len(encoded))
    event("complete",len(encoded),len(encoded),sha256=hashlib.sha256(encoded).hexdigest())


if __name__ == "__main__":
    try: main()
    except Exception as exc:
        print(json.dumps({"error":str(exc)[:1024]}),file=sys.stderr)
        sys.exit(1)
