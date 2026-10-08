#!/usr/bin/env python3
"""Editor-owned deterministic environment generation and semantic infill (MIT).

The input/output are authoring data. No layout code is needed by consumers.
Independent tensor-field implementation informed by Chen et al. 2008 and the
ProbableTrain overview; no third-party implementation code is incorporated.
"""
import argparse
import copy
from dataclasses import asdict, dataclass, field
import hashlib
import io
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import threading
import time

from PIL import Image
import shapely
import shapely.affinity
from shapely.geometry import LineString, MultiPoint, Point, Polygon, box, mapping, shape
from shapely.ops import nearest_points, polygonize_full, unary_union
from shapely.strtree import STRtree

from asset_derivatives import asset as derive_asset
from environment_profiles import PROFILES, model_scale
from environment_assets import library as module_library
from reference_maps import canonical, empty, road
from special_driving_maps import place as driving_feature

OWNER = "mapeditor-environment-v1"
HISTORY_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 18000
TILE_METRES = 128
FIELDS = ("nodes", "roads", "buildings", "zones", "placements", "surface_areas", "water_bodies", "gimmicks", "heightmaps", "assets")


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def fingerprint():
    files = [Path(__file__).with_name(name) for name in ("environment_generation.py","environment_profiles.py","environment_assets.py","asset_derivatives.py","city_assets.py","driving_school_map.py","special_driving_maps.py")]
    return digest(b"".join(p.read_bytes() for p in files) + shapely.__version__.encode())


def rng(seed, *keys):
    return random.Random(int(digest([seed, *keys])[:16], 16))


def polygons(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == "Polygon": return [geometry]
    return [p for child in getattr(geometry, "geoms", []) for p in polygons(child)]


def lines(geometry):
    if geometry.is_empty: return []
    if geometry.geom_type == "LineString": return [geometry]
    return [p for child in getattr(geometry, "geoms", []) for p in lines(child)]


def xy(point): return [round(point[0] * 100), round(point[1] * 100)]


def rings(poly):
    return [xy(p) for p in list(poly.exterior.coords)[:-1]], [[xy(p) for p in list(h.coords)[:-1]] for h in poly.interiors]


def polygon(record, key="polygon", holes="holes"):
    return Polygon([(p[0]/100, p[1]/100) for p in record[key]],
                   [[(p[0]/100,p[1]/100) for p in h] for h in record.get(holes, [])])


def stable_record(value):
    """Ignore native empty defaults; retain every meaningful user edit."""
    if isinstance(value, dict):
        return {k: stable_record(v) for k,v in value.items() if v is not None and v != [] and not (k in ("yaw_offset_mdeg",) and v == 0)}
    if isinstance(value, list): return [stable_record(v) for v in value]
    if isinstance(value, float) and value.is_integer(): return int(value)
    return value


@dataclass
class GenerationContext:
    document: dict
    project: str = ""
    selection_cm: list = field(default_factory=list)
    regions: list = field(default_factory=list)
    protected: list = field(default_factory=list)
    source_denominator: int = 1

    @classmethod
    def from_document(cls, document, project="", selection_cm=None):
        regions, denominator = [], 1
        for attribution in document.get("attributions", []):
            try: meta = json.loads(attribution.get("notice", ""))
            except (ValueError, TypeError): continue
            if isinstance(meta,dict) and meta.get("adapter") == "osm-extract-v1":
                if meta.get("authored_units",{}).get("source_denominator") != 8:
                    raise ValueError("OSM provenance must declare the current 1:8 authored units")
                denominator = 8
                regions.extend(meta.get("authored_regions", []))
        return cls(copy.deepcopy(document), project, selection_cm or [], regions,
                   [r for r in regions if r.get("protected") or r.get("landuse") in ("water","wetland","nature_reserve")], denominator)


@dataclass(frozen=True)
class GenerationRequest:
    mode: str
    theme: str
    seed: int
    bounds_cm: list
    density: float = 1.0
    texture_profile: int = 256

    def validate(self):
        if self.mode not in ("new", "fill") or self.theme not in PROFILES:
            raise ValueError("Choose new/fill and a supported theme")
        if type(self.seed) is not int or not 0 <= self.seed < 2**53:
            raise ValueError("Seed must be an integer in [0,2^53)")
        if len(self.bounds_cm) != 4 or any(type(v) is not int or abs(v)>10000000 for v in self.bounds_cm):
            raise ValueError("Select finite integer-centimetre bounds")
        x,y,X,Y = self.bounds_cm
        if not 0 < X-x <= 400000 or not 0 < Y-y <= 400000 or (X-x)*(Y-y)>160000000000:
            raise ValueError("Selection must be nonempty and at most 4 km per side")
        if not .1 <= self.density <= 2 or self.texture_profile not in (128,256,512):
            raise ValueError("Density must be 0.1–2 and texture profile 128/256/512")


@dataclass
class GenerationResult:
    document: dict
    patches: list
    assets: dict
    owned: list
    diagnostics: dict
    metadata: dict
    input_sha256: str
    algorithm: str


class Generator:
    def __init__(self, request, context, kit):
        request.validate()
        self.request, self.context, self.kit = request, context, Path(kit)
        self.profile = PROFILES[request.theme]
        self.scale = 1 / context.source_denominator if request.mode == "fill" else 1
        self.original = copy.deepcopy(context.document)
        self.doc = copy.deepcopy(context.document)
        self.window = box(*(v/100 for v in request.bounds_cm))
        self.world = box(*(context.document["bounds"]["min"] + context.document["bounds"]["max"]))
        self.world = shapely.affinity.scale(self.world, xfact=.01,yfact=.01,origin=(0,0))
        if not self.world.covers(self.window): raise ValueError("Selection exceeds document bounds")
        self.payloads, self.asset_reports, self.library = {}, {}, {}
        self.owned, self.sites, self.pads, self.diagnostics = [], [], [], []
        self.pad_grid = {}
        self.owned_before, self.preserved_ids = {}, set()
        self.family = OWNER + ":" + self.profile.id
        self.previous_meta = []
        self.new_layout = request.mode == "new"
        self._retire_owned()
        self.identities={field:{record_id(field,r) for r in self.doc.get(field,[])} for field in FIELDS}
        for lib in ("richer-library", "arcade-library"):
            root = self.kit / "assets" / lib
            for record in json.loads((root / "library.json").read_text())["assets"]:
                self.library[record["id"]] = (record, root)
        self.modules = module_library()
        self.occupied = []
        self.occupied_grid = {}
        self.road_lines, self.road_buffers = [], []
        self.water = unary_union([polygon(w,holes="islands") for w in self.doc.get("water_bodies", [])])
        self.protected = unary_union([polygon(r) for r in context.protected])
        self.images = {}
        self.height_records = {(r["cell"]["x"],r["cell"]["y"]):r for r in self.doc.get("heightmaps",[])}
        self.graph = []
        self.surface_polys = [polygon(r) for r in self.doc.get("surface_areas",[])]
        self.districts = []

    def _retire_owned(self):
        for attribution in self.doc.get("attributions", []):
            if not attribution.get("source", "").startswith(self.family + ":"): continue
            try: meta = json.loads(attribution["notice"])
            except ValueError: continue
            # Ownership survives source edits to the algorithm, not user edits to
            # its objects. Global stable IDs prevent reexecution duplicates.
            self.new_layout |= meta.get("new_layout", meta.get("request", {}).get("mode") == "new")
            for owned in meta.get("owned", []):
                field, identity = owned["field"], owned["id"]
                current = next((r for r in self.doc.get(field,[]) if record_id(field,r)==identity),None)
                if current is None:
                    self.preserved_ids.add((field,identity)) # user deletion is an edit
                    continue
                position = owned.get("anchor_cm")
                selected = field in ("placements", "surface_areas") and "-pier-" not in identity and position is not None and self.window.buffer(-64*self.scale).covers(Point(position[0]/100,position[1]/100))
                if selected and digest(stable_record(current)) == owned["sha256"]:
                    self.doc[field].remove(current)
                    self.owned_before[(field,identity)] = current
                else:
                    self.preserved_ids.add((field,identity))
                    self.owned.append(owned)
            self.previous_meta.append(attribution)
        for entry in self.previous_meta: self.doc["attributions"].remove(entry)

    def add(self, field, record, anchor=None):
        identity = record_id(field, record)
        if (field,identity) in self.preserved_ids: return False
        if identity in self.identities.setdefault(field,set()): return False
        self.doc.setdefault(field,[]).append(record)
        self.identities[field].add(identity)
        if field in ("placements", "surface_areas"):
            self.owned.append(dict(field=field,id=identity,sha256=digest(stable_record(record)),anchor_cm=xy(anchor) if anchor else None))
        if len(self.owned) > MAX_OBJECTS: raise ValueError("Generation exceeds 18000 objects; reduce density/area")
        return True

    def raw_height(self,x,y):
        x0,y0,x1,y1=self.world.bounds;u=(x-x0)/(x1-x0);v=(y-y0)/(y1-y0)
        relief=self.profile.relief_m
        if self.profile.id=="snow-mountain": return 4+relief*(1-v)**2*(.7+.3*math.sin(x/260)**2)
        if self.profile.id=="red-canyon": return 4+relief*(.5+.5*math.sin(y/150+x/600))**4
        return 4+relief*(.55*math.sin(x/190+y/250)**2+.25*math.sin(y/120)**2)

    def height(self,x,y):
        if self.request.mode=="fill":
            cell_size=self.doc["cell_size_cm"]/100
            # Cell indices are relative to the document's lower bound.
            ox,oy=(v/100 for v in self.doc["bounds"]["min"])
            cell=(math.floor((x-ox)/cell_size),math.floor((y-oy)/cell_size))
            record=self.height_records.get(cell)
            if record:
                if record["path"] not in self.images:
                    path=Path(self.context.project)/record["path"]
                    with Image.open(path) as im: self.images[record["path"]]=(im.size,list(im.getdata()))
                (w,h),values=self.images[record["path"]]
                step=record["spacing_cm"]/100
                fx=max(0,min(w-1,(x-ox-cell[0]*cell_size)/step));fy=max(0,min(h-1,(y-oy-cell[1]*cell_size)/step))
                ix,iy=int(fx),int(fy);jx,jy=min(w-1,ix+1),min(h-1,iy+1)
                a=values[iy*w+ix]*(1-(fx-ix))+values[iy*w+jx]*(fx-ix)
                b=values[jy*w+ix]*(1-(fx-ix))+values[jy*w+jx]*(fx-ix)
                return (record["offset_cm"]+(a*(1-(fy-iy))+b*(fy-iy))*record["step_cm"])/100
            return self.doc.get("terrain_base_cm",0)/100
        result=self.raw_height(x,y)
        p=Point(x,y)
        if not self.water.is_empty:
            distance=self.water.distance(p)
            if self.water.covers(p): return -2
            if distance<18: result=2+(result-2)*min(1,distance/18)
        # Flatten facilities and blend their verges into the landscape. Trees
        # and rocks use sampled natural terrain, not floating level platforms.
        pad_key=(math.floor(x/(32*self.scale)),math.floor(y/(32*self.scale)))
        for area,level in self.pad_grid.get(pad_key,[]):
            d=area.distance(p)
            if d<5: result=level+(result-level)*min(1,d/5)
        return result

    def water_stage(self):
        if self.request.mode!="new": return
        x,y,X,Y=self.window.bounds;w,h=X-x,Y-y
        if self.profile.id in ("village","deep-forest","neon-harbor"):
            if self.profile.id=="neon-harbor":
                area=box(x+w*.80,y+24,X-24,Y-24)
            elif self.profile.id=="deep-forest":
                area=Point(x+w*.73,y+h*.66).buffer(min(w,h)*.10,quad_segs=12)
            else:
                path=LineString([(x+w*.74+math.sin(i*.8)*w*.025,y+24+(h-48)*i/12) for i in range(13)])
                area=path.buffer(3,cap_style=2).simplify(.1)
            outer,holes=rings(area)
            self.add("water_bodies",dict(id="env-water",polygon=outer,islands=holes,surface_cm=100,bottom_cm=-500,flow_cm_s=[0,10]),area.centroid.coords[0])
            self.water=area

    def districts_stage(self):
        """Reserve semantic neighbourhoods before tracing their access network."""
        x,y,X,Y=self.world.bounds;w,h=X-x,Y-y
        urban=self.profile.urban
        uses=("residential","commercial","farmland","park") if self.profile.id=="village" else ("commercial","residential","industrial","industrial") if self.profile.id=="neon-harbor" else ("commercial","industrial","industrial","industrial") if self.profile.id=="machine-factory" else ("commercial","recreation_ground","recreation_ground","park") if urban else ("forest","bare_rock","recreation_ground","forest")
        for i,use in enumerate(uses):
            a=x+(i%2)*w/2;b=y+(i//2)*h/2
            area=box(a,b,a+w/2,b+h/2).difference(self.water)
            self.districts.append(dict(id="district-"+str(i),landuse=use,geometry=area))

    def road_height(self,x,y):
        level=self.raw_height(x,y)
        if self.profile.id=="sky-park":
            a,b,A,B=self.world.bounds
            # An 8 m elevated outer promenade with 1:12 sloping approaches.
            edge=min(x-a,y-b,A-x,B-y)
            level+=max(0,8-(max(0,edge-32)/12))
        if self.profile.id=="neon-harbor" and not self.water.is_empty:
            d=Point(x,y).distance(self.water)
            level=max(level,6-max(0,d-10)/12)
        return level

    def tensor(self,x,y,minor=False):
        x0,y0,x1,y1=self.world.bounds;cx=(x0+x1)/2;cy=(y0+y1)/2
        theta=math.atan2(y-cy,x-cx)+math.pi/2
        radial=.16*math.exp(-((x-cx)**2+(y-cy)**2)/(.22*max(x1-x0,y1-y0))**2)
        shore=.10 if self.profile.id=="neon-harbor" else 0
        angle=.5*math.atan2(radial*math.sin(2*theta),1-radial+radial*math.cos(2*theta)+shore)
        if not self.profile.urban:
            # Prefer contour-following directions where grade is costly.
            gx=(self.raw_height(x+2,y)-self.raw_height(x-2,y))/4
            gy=(self.raw_height(x,y+2)-self.raw_height(x,y-2))/4
            contour=math.atan2(gx,-gy)
            weight=min(.35,math.hypot(gx,gy))
            angle=.5*math.atan2(math.sin(2*angle)+weight*math.sin(2*contour), math.cos(2*angle)+weight*math.cos(2*contour))
        return angle+(math.pi/2 if minor else 0)

    def road_stage(self):
        if self.request.mode=="new":
            x,y,X,Y=self.window.bounds;margin=32
            boundary=box(x+margin,y+margin,X-margin,Y-margin)
            spacing=self.profile.road_spacing_m
            paths=[LineString(boundary.exterior.coords)]
            def trace(seed,minor):
                halves=[]
                for direction in (-1,1):
                    p=seed;points=[p]
                    for _ in range(400):
                        angle=self.tensor(*p,minor)
                        mid=(p[0]+direction*12*math.cos(angle),p[1]+direction*12*math.sin(angle))
                        angle=self.tensor(*mid,minor)
                        p=(p[0]+direction*24*math.cos(angle),p[1]+direction*24*math.sin(angle))
                        points.append(p)
                        if not boundary.covers(Point(p)): break
                    halves.append(points)
                return LineString(list(reversed(halves[0]))+halves[1][1:]).intersection(boundary)
            for yy in range(math.ceil((y+margin+spacing)/spacing)*spacing,int(Y-margin),spacing): paths.extend(lines(trace(((x+X)/2,yy),False)))
            for xx in range(math.ceil((x+margin+spacing)/spacing)*spacing,int(X-margin),spacing): paths.extend(lines(trace((xx,(y+Y)/2),True)))
            # Water is an explicit exclusion. A single cross-water bridge is
            # planned before noding so its two approaches share exact nodes.
            if not self.water.is_empty:
                paths=[line for path in paths for line in lines(path.difference(self.water.buffer(10)))]
                if self.profile.id=="neon-harbor":
                    # Harbor bridge spans a dock basin, with dry approaches.
                    bx=x+(X-x)*.80
                    paths.append(LineString([(x+32,y+90),(bx+35,y+90),(bx+35,Y-90),(x+32,Y-90)]))
            network=shapely.set_precision(unary_union(paths),.01)
            self.graph=lines(network)
            if self.profile.id=='sky-park':
                # Bound elevated authoring spans so a support is certified
                # against its local deck, including all deck footprint corners.
                divided=[]
                for line in self.graph:
                    if any(self.road_height(*p)-self.raw_height(*p)>.05 for p in line.coords):
                        points=list(line.segmentize(40).coords)
                        divided.extend(LineString([a,b]) for a,b in zip(points,points[1:]))
                    else: divided.append(line)
                self.graph=divided
            for index,line in enumerate(sorted(self.graph,key=lambda g:g.wkb_hex)):
                if line.length<2: continue
                coordinates=list(line.segmentize(24).coords)
                points=[[round(a*100),round(self.road_height(a,b)*100),round(b*100)] for a,b in coordinates]
                wet=not self.water.is_empty and line.intersects(self.water)
                elevated=self.profile.id=="sky-park" and any(self.road_height(a,b)-self.raw_height(a,b)>.05 for a,b in coordinates)
                name="env-road-"+digest([xy(p) for p in coordinates])[:14]
                def node(p): return "env-node-"+digest(p)[:14]
                # Ground endpoints are keyed by horizontal point, including
                # bridge approaches; all heights use the same terrain function.
                road(self.doc,name,points,"bridge" if wet else "elevated" if elevated else "ground",800 if self.profile.urban else 600,
                     "dirt" if self.profile.id=="deep-forest" else "asphalt",node(points[0]),node(points[-1]))
                self.doc["roads"][-1]["sidewalk_cm"]=180 if self.profile.urban else 0
        for record in self.doc.get("roads",[]):
            line=LineString([(p[0]/100,p[2]/100) for p in record["points"]])
            self.road_lines.append(line)
            width=max(record["widths_cm"])/100
            self.road_buffers.append(line.buffer(width/2+2*self.scale,cap_style=2))
        self.road_union=unary_union(self.road_lines)
        self.road_space=unary_union(self.road_buffers)
        self.road_tree=STRtree(self.road_lines)
        blocks,cuts,dangles,invalid=polygonize_full(unary_union(self.road_lines))
        self.blocks=polygons(blocks)
        self.diagnostics.append(dict(stage="blocks",blocks=len(self.blocks),dead_ends=len(getattr(dangles,"geoms",[])),
            cut_edges=len(getattr(cuts,"geoms",[])),invalid_rings=len(getattr(invalid,"geoms",[]))))
        if not invalid.is_empty: raise ValueError("Road graph has invalid rings")

    def asset(self,identity):
        key=identity+"-env-"+str(self.context.source_denominator if self.request.mode=="fill" else 1)+"-"+str(self.request.texture_profile)
        existing=next((a for a in self.doc["assets"] if a["id"]==key),None)
        if existing: return existing
        if identity in self.modules: original,source=self.modules[identity]
        else:
            original,root=self.library[identity];source=(root/original["path"]).read_bytes()
        record,data,report=derive_asset(original,source,self.request.texture_profile,model_scale(identity)*self.scale)
        record["id"]=key
        self.doc["assets"].append(record);self.payloads[record["path"]]=data;self.asset_reports[key]=report
        return record

    def approaches_stage(self):
        if self.request.mode!='new': return
        incidence={}
        for r in self.doc['roads']:
            for node in (r['from'],r['to']): incidence.setdefault(node,set()).add(r['kind'])
        aprons=[]
        for node in self.doc['nodes']:
            kinds=incidence.get(node['id'],set())
            if 'ground' not in kinds or not kinds.intersection(('bridge','elevated')): continue
            x,h,y=[v/100 for v in node['position']]
            area=box(x-20,y-20,x+20,y+20)
            pad=(area,h);self.pads.append(pad)
            for key in self.grid_keys(area.buffer(5)): self.pad_grid.setdefault(key,[]).append(pad)
            aprons.append(pad)
        for record in [*self.doc['nodes'],*self.doc['roads']]:
            for point in record.get('points',[record.get('position')]):
                p=Point(point[0]/100,point[2]/100)
                for area,level in aprons:
                    if area.covers(p): point[1]=round(level*100)
        if aprons:
            # Keep foundations and prop planting outside level transition pads.
            self.road_space=unary_union([self.road_space,*[a.buffer(5) for a,_ in aprons]])
        self.diagnostics.append(dict(stage='approaches',level_aprons=len(aprons)))

    def footprint(self,record,position,yaw):
        points=[]
        for proxy in record.get("collision",[]):
            c,s=proxy["center"],proxy["size_cm"]
            points.extend((c[0]+a*s[0]/2,c[2]+b*s[2]/2) for a in (-1,1) for b in (-1,1))
        for convex in record.get("convex_collision",[]): points.extend((p[0],p[2]) for p in convex["vertices"])
        # Canopies have narrow trunk proxies; reserve their visual footprint too.
        if any(k in record["id"] for k in ("canopy","pine","grove")):
            r=(5 if record["id"].startswith("environment-canopy") else 4 if "grove" not in record["id"] else 2)*self.scale
            points.extend((a*r*100,b*r*100) for a in (-1,1) for b in (-1,1))
        if not points: points=[(-50,-50),(50,-50),(50,50),(-50,50)]
        angle=math.radians(yaw);c,s=math.cos(angle),math.sin(angle)
        return MultiPoint([(position[0]+(x*c-y*s)/100,position[1]+(x*s+y*c)/100) for x,y in points]).convex_hull

    def fixed_stage(self):
        assets={a["id"]:a for a in self.doc.get("assets",[])}
        for record in self.doc.get("buildings",[]):
            self.occupied.append(polygon(record,"footprint").buffer(self.scale))
            for entrance in record.get("entrances",[]): self.occupied.append(Polygon([(p[0]/100,p[1]/100) for p in entrance]))
        for record in self.doc.get("placements",[]):
            p=record["position"];yaw=record.get("quarter_turns",0)*90+record.get("yaw_offset_mdeg",0)/1000
            if record["asset_id"] in assets: area=self.footprint(assets[record["asset_id"]],(p[0]/100,p[2]/100),yaw)
            else: area=Point(p[0]/100,p[2]/100).buffer(3*self.scale)
            self.occupied.append(area.buffer(self.scale))
        for gimmick in self.doc.get("gimmicks",[]):
            a,b=gimmick["safety_min_cm"],gimmick["safety_max_cm"]
            self.occupied.append(box(a[0]/100,a[2]/100,b[0]/100,b[2]/100))
        # Authored open space is meaningful, not vacant. Imported zones and
        # manual surfaces stay protected from blanket parcel filling.
        for record in self.doc.get("surface_areas",[]): self.occupied.append(polygon(record))
        for occupied in self.occupied: self.index_occupied(occupied)
        self.fixed=unary_union(self.occupied)
        self.forbidden=unary_union([self.fixed,self.road_space,self.water.buffer(self.scale),self.protected])

    def grid_keys(self, area):
        step=32*self.scale;x,y,X,Y=area.bounds
        return [(ix,iy) for ix in range(math.floor(x/step),math.floor(X/step)+1) for iy in range(math.floor(y/step),math.floor(Y/step)+1)]

    def index_occupied(self, area):
        for key in self.grid_keys(area): self.occupied_grid.setdefault(key,[]).append(area)

    def nearby(self, area):
        return [p for key in self.grid_keys(area) for p in self.occupied_grid.get(key,[])]

    def surface(self,identity,area,material,anchor):
        if self.surface_polys: area = area.difference(unary_union(self.surface_polys))
        pieces=[]
        for poly in polygons(area):
            if poly.area<.05*self.scale**2: continue
            poly=shapely.set_precision(poly,.01).simplify(.02*self.scale,preserve_topology=True)
            # Current MapKit ground polygons have no holes. Constrained
            # triangulation preserves every exclusion rather than filling it.
            pieces.extend(polygons(shapely.constrained_delaunay_triangles(poly)) if poly.interiors else [poly])
        for index,poly in enumerate(pieces):
            poly = poly.buffer(-.02, join_style=2)
            if poly.is_empty or poly.geom_type != "Polygon": continue
            outer,_=rings(poly)
            snapped=Polygon(outer)
            if len(outer)<3 or len(outer)>512 or not snapped.is_valid or snapped.area<100 or len(set(map(tuple,outer)))!=len(outer): continue
            if self.add("surface_areas",dict(id=identity+"-"+str(index),polygon=outer,surface=material),anchor): self.surface_polys.append(poly)

    def place(self,identity,model,point,yaw=0,plot=None,natural=False,clearance=.8):
        if ("placements",identity) in self.preserved_ids: return False
        asset=self.asset(model);area=self.footprint(asset,point,yaw)
        if not self.window.covers(area.buffer(.1*self.scale)) or (plot is not None and not plot.covers(area)):
            return False
        if area.intersects(self.forbidden) or any(area.distance(p)<clearance*self.scale for p in self.nearby(area.buffer(clearance*self.scale))): return False
        if not natural:
            corners=list(area.exterior.coords)
            heights=[self.height(*p) for p in corners]
            if max(heights)-min(heights)>self.footing_limit(area): return False
            level=min(heights)
            if self.request.mode=="new":
                pad=(area.buffer(1*self.scale),level)
                self.pads.append(pad)
                for key in self.grid_keys(pad[0].buffer(5)): self.pad_grid.setdefault(key,[]).append(pad)
        else:
            level=self.height(*point)
            if model in ('environment-strata','environment-butte'):
                level=min(self.height(*p) for p in area.exterior.coords)
        record=dict(id=identity,asset_id=asset["id"],position=[round(point[0]*100),round(level*100),round(point[1]*100)],quarter_turns=0,yaw_offset_mdeg=round(yaw*1000))
        previous=self.owned_before.get(("placements",identity))
        if previous and all(record.get(k,0)==previous.get(k,0) for k in ("asset_id","quarter_turns","yaw_offset_mdeg")) and record["position"][::2]==previous["position"][::2] and abs(record["position"][1]-previous["position"][1])<=5:
            # PNG16 round-trip interpolation must not drift a level footing.
            record["position"][1]=previous["position"][1]
        if not self.add("placements",record,point): return False
        self.occupied.append(area)
        self.index_occupied(area)
        return True

    def footing_limit(self, area):
        return max((4 if self.request.mode=='new' else 2)*self.scale,math.sqrt(area.area)*(.25 if self.request.mode=='new' else .12))

    def parcel(self,rule,target,identity,region=None):
        if not self.road_lines:
            self.diagnostics.append(dict(stage="facility",id=identity,error="No road access"));return False
        centre=Point(target);nearest=self.road_lines[int(self.road_tree.nearest(centre))]
        along=max(10*self.scale,min(nearest.length-10*self.scale,nearest.project(centre)))
        p=nearest.interpolate(along);q=nearest.interpolate(min(nearest.length,along+1*self.scale))
        if p.equals(q): q=nearest.interpolate(max(0,along-1*self.scale))
        angle=math.atan2(q.y-p.y,q.x-p.x)
        width=max(36,math.sqrt(rule.area_m2[0]))*self.scale
        depth=max(40,rule.area_m2[0]/(width/self.scale))*self.scale
        columns=2 if len(rule.objects)>1 else 1
        if rule.objects:
            sizes=[self.footprint(self.asset(model),(0,0),0).bounds for model in rule.objects]
            width=max(width,columns*(max(p[2]-p[0] for p in sizes)+4*self.scale))
            depth=max(depth,math.ceil(len(rule.objects)/columns)*(max(p[3]-p[1] for p in sizes)+4*self.scale)+12*self.scale)
        for attempt in range(12):
            side=1 if attempt%2==0 else -1
            offset=(attempt//2-2)*width*.45
            tangent=(math.cos(angle),math.sin(angle));normal=(-tangent[1]*side,tangent[0]*side)
            near=(p.x+tangent[0]*offset+normal[0]*9*self.scale,p.y+tangent[1]*offset+normal[1]*9*self.scale)
            points=[(near[0]+tangent[0]*a+normal[0]*b,near[1]+tangent[1]*a+normal[1]*b) for a,b in [(-width/2,0),(width/2,0),(width/2,depth),(-width/2,depth)]]
            plot=Polygon(points)
            if not self.window.covers(plot) or plot.intersects(self.forbidden) or any(plot.intersects(site["geometry"]) for site in self.sites): continue
            if region is not None and not region.covers(plot): continue
            anchor=(near[0]+normal[0]*depth/2,near[1]+normal[1]*depth/2)
            placed=[]
            candidates=[]
            for index,model in enumerate(rule.objects):
                a=(index%columns-(columns-1)/2)*width*.43
                b=depth*(.48 if index<columns else .78)
                pos=(near[0]+tangent[0]*a+normal[0]*b,near[1]+tangent[1]*a+normal[1]*b)
                yaw=math.degrees(angle)+(180 if side<0 else 0)
                area=self.footprint(self.asset(model),pos,yaw)
                candidates.append((model,pos,yaw,area))
            if self.request.mode=='new':
                blocked=False
                for model,pos,yaw,area in candidates:
                    levels=[self.height(*p) for p in area.exterior.coords]
                    if not plot.covers(area) or area.intersects(self.forbidden) or any(area.distance(p)<.8*self.scale for p in self.nearby(area.buffer(.8*self.scale))) or (rule.access and max(levels)-min(levels)>self.footing_limit(area)):
                        blocked=True;break
                if blocked: continue
            # Frontage and service yard are explicit open polygons. Keep a
            # through entrance wide enough for vehicle access to the road.
            for index,(model,pos,yaw,area) in enumerate(candidates):
                if self.place(identity+"-object-"+str(index),model,pos,yaw,plot,natural=not rule.access): placed.append(identity+"-object-"+str(index))
            if rule.objects and not placed: continue
            if rule.id=='fields':
                # Tilled parcels are productive open space: repeat crop modules
                # across the usable interior, retaining turning room at each end.
                spacing=8*self.scale
                for row in range(1,int(depth/spacing)-1):
                    for column in range(1,int(width/spacing)):
                        a=-width/2+column*spacing;b=(row+1)*spacing
                        pos=(near[0]+tangent[0]*a+normal[0]*b,near[1]+tangent[1]*a+normal[1]*b)
                        model=rule.objects[(row+column)%len(rule.objects)]
                        crop=identity+'-crop-'+str(row)+'-'+str(column)
                        if self.place(crop,model,pos,math.degrees(angle),plot): placed.append(crop)
            front=(near[0]+normal[0]*depth*.20,near[1]+normal[1]*depth*.20)
            entrance=LineString([(p.x+tangent[0]*offset,p.y+tangent[1]*offset),front]).buffer(2*self.scale,cap_style=2)
            if rule.access and rule.id!='fields':
                branches=[entrance]
                for model,pos,yaw,area in candidates:
                    if any(name in model for name in ('house','shop','shed','school','farm','nord','tower','courtyard')):
                        door=nearest_points(Point(front),area)[1]
                        branches.append(LineString([front,(door.x,door.y)]).buffer(1.5*self.scale,cap_style=2))
                entrance=unary_union(branches)
            yard=plot
            self.surface(identity+"-entry",entrance.difference(self.road_space),"concrete" if self.profile.urban else "gravel",anchor)
            self.surface(identity+"-yard",yard,rule.surface,anchor)
            self.sites.append(dict(id=identity,group=rule.id,landuse=rule.landuse,geometry=plot,anchor=anchor,
                                   objects=placed,entrance=entrance,access=nearest.distance(Point(anchor)),required=True))
            return True
        self.diagnostics.append(dict(stage="facility",id=identity,error="No clear road-facing parcel after 12 attempts"))
        return False

    def facilities_stage(self):
        x,y,X,Y=self.world.bounds
        rules=self.profile.rules
        if self.new_layout:
            columns=math.ceil(math.sqrt(len(rules)))
            for index,rule in enumerate(rules):
                if rule.landuse=="water": continue
                if rule.id in ('bridge','elevated-walkways'): continue
                target=(x+(X-x)*(.15+.65*(index%columns)/max(1,columns-1)),y+(Y-y)*(.17+.62*(index//columns)/max(1,math.ceil(len(rules)/columns)-1)))
                neighbor=next((site for site in self.sites if site["group"] in rule.adjacent),None)
                if neighbor: target=(neighbor["anchor"][0]+75,neighbor["anchor"][1]+40)
                if rule.id in ('docks','waterfront') and self.profile.id=='neon-harbor': target=(x+(X-x)*.76,y+(Y-y)*(.28 if rule.id=='docks' else .72))
                if not self.parcel(rule,target,"env-facility-"+rule.id):
                    alternatives=sorted(self.blocks,key=lambda p:p.centroid.distance(Point(target)))
                    for block in alternatives[:24]:
                        if self.parcel(rule,block.centroid.coords[0],"env-facility-"+rule.id): break
            # Build the surrounding neighbourhoods from road-frontage parcels.
            # The required sites above reserve their access/service space first.
            if self.profile.id in ("village","neon-harbor","machine-factory","sky-park"):
                for line in self.road_lines:
                    key=digest([xy(p) for p in line.coords])[:12]
                    for slot in range(1,math.floor(line.length/88)):
                        p=line.interpolate(slot*88)
                        u,v=(p.x-x)/(X-x),(p.y-y)/(Y-y)
                        use=next((d["landuse"] for d in self.districts if d["geometry"].covers(p)),"park")
                        choices=[r for r in rules if r.landuse==use and r.objects]
                        if not choices: continue
                        random=rng(self.request.seed,"parcel",key,slot)
                        if random.random()>min(1,self.request.density*.8): continue
                        selected=random.choice(choices)
                        self.parcel(selected,(p.x,p.y),"env-parcel-"+key+"-"+str(slot))
        else:
            for region in sorted(self.context.regions,key=lambda r:r["id"]):
                if region.get("protected") or region.get("landuse") in ("water","wetland"): continue
                area=polygon(region).intersection(self.window).difference(self.forbidden)
                matching=[r for r in rules if r.landuse==region.get("landuse") and r.objects]
                for part in polygons(area):
                    if matching:
                        # Stable global lattice: region-local random draws never
                        # shift after edits elsewhere or a smaller selection.
                        step=64*self.scale
                        a,b,A,B=part.bounds
                        for ix in range(math.floor(a/step),math.ceil(A/step)):
                            for iy in range(math.floor(b/step),math.ceil(B/step)):
                                key="env-infill-"+digest([region["source_id"],ix,iy])[:16]
                                target=((ix+.5)*step,(iy+.5)*step)
                                if not part.covers(Point(target)): continue
                                rule=matching[int(digest(key)[:6],16)%len(matching)]
                                self.parcel(rule,target,key,part)
                    else:
                        # Unknown land use never guesses a building. Low-impact
                        # ground cover still records intentional open space.
                        self.surface("env-open-"+digest([region["id"],part.wkb_hex])[:16],part,"grass",part.centroid.coords[0])
            if not self.context.regions:
                # Respect existing buildings/access/water; unknown space gets
                # sparse grass patches below, no fabricated residential lots.
                self.diagnostics.append(dict(stage="semantics",warning="No land-use evidence; only low-intensity ground cover"))

    def details_stage(self):
        for site in list(self.sites):
            if site['landuse'] not in ('industrial','residential','farmland'): continue
            exterior=LineString(site['geometry'].exterior.coords)
            spacing=4.2*self.scale
            for i in range(1,int(exterior.length/spacing)):
                p=exterior.interpolate(i*spacing);q=exterior.interpolate(min(exterior.length,i*spacing+self.scale))
                if p.distance(site['entrance'])<4*self.scale: continue
                yaw=math.degrees(math.atan2(q.y-p.y,q.x-p.x))
                if self.profile.id=='machine-factory' or site['landuse']=='farmland':
                    self.place(site['id']+'-fence-'+str(i),'environment-fence',(p.x,p.y),yaw,clearance=.02)
        if self.profile.id=='snow-mountain':
            for record,line in zip(self.doc['roads'],self.road_lines):
                for i in range(1,int(line.length/32)):
                    p=line.interpolate(i*32);q=line.interpolate(min(line.length,i*32+1))
                    angle=math.atan2(q.y-p.y,q.x-p.x)
                    self.place(record['id']+'-guard-'+str(i),'environment-guardrail',(p.x-math.sin(angle)*7,p.y+math.cos(angle)*7),math.degrees(angle))
        if self.request.mode!='new': return
        # Shared native roads supply deck collision; explicit piers supply the
        # load-bearing structure. They stop below decks and keep ground roads clear.
        for record,line in zip(self.doc['roads'],self.road_lines):
            if record['kind'] not in ('elevated','bridge'): continue
            if line.length<12: continue
            samples=[line.length/2] if line.length<80 else list(range(40,int(line.length),40))
            for i,distance in enumerate(samples):
                p=line.interpolate(distance)
                if self.road_height(p.x,p.y)-self.raw_height(p.x,p.y)<7.8: continue
                q=line.interpolate(min(line.length,distance+1));yaw=math.degrees(math.atan2(q.y-p.y,q.x-p.x))
                a=self.asset('environment-pier')
                level=min(p[1] for p in record['points'])/100-8.1
                self.add('placements',dict(id=record['id']+'-pier-'+str(i),asset_id=a['id'],position=[round(p.x*100),round(level*100),round(p.y*100)],quarter_turns=0,yaw_offset_mdeg=round(yaw*1000)),(p.x,p.y))

    def driving_stage(self):
        if self.request.mode!='new': return
        templates=json.loads((self.kit/'godot/driving_templates.json').read_text())
        candidates=[]
        for r in self.doc['roads']:
            if r['kind']!='ground': continue
            for a,b in zip(r['points'],r['points'][1:]):
                length=math.hypot(b[0]-a[0],b[2]-a[2])
                grade=abs(b[1]-a[1])/max(1,length)
                if length>1800 and grade<.10: candidates.append((r,a,b))
        for index,kind in enumerate(('target_speed','jump_height')):
            if len(candidates)<=index: break
            r,a,b=candidates[len(candidates)*(index+1)//3]
            yaw=math.degrees(math.atan2(b[0]-a[0],b[2]-a[2]));p=[(a[k]+b[k])/2 for k in range(3)]
            # Narrow roadside pad leaves a normal driving bypass.
            p[0]+=math.cos(math.radians(yaw))*180;p[2]-=math.sin(math.radians(yaw))*180
            g=driving_feature(templates,kind,p,yaw,65);g['id']='env-driving-'+kind;g['scale_per_mille'][0]=600
            for part,source in zip(g['parts'],templates[kind]['parts']):
                for vertex,original in zip(part['vertices'],source['vertices']): vertex[1]=1 if original[1]>=0 else -1
            g['rotation_mdeg'][0]=round(-math.degrees(math.atan2(b[1]-a[1],math.hypot(b[0]-a[0],b[2]-a[2])))*1000)
            self.add('gimmicks',g,(p[0]/100,p[2]/100))

    def nature_stage(self):
        scale=self.scale;step=(14 if self.profile.id=="deep-forest" else 18 if self.profile.id=="snow-mountain" else 32)*scale
        x,y,X,Y=self.window.bounds
        sites=unary_union([s["geometry"] for s in self.sites])
        # Use full existing context for exclusions, not just selected objects.
        for ix in range(math.floor(x/step),math.ceil(X/step)):
            for iy in range(math.floor(y/step),math.ceil(Y/step)):
                random=rng(self.request.seed,"nature",ix,iy)
                p=((ix+.2+.6*random.random())*step,(iy+.2+.6*random.random())*step)
                if not self.window.covers(Point(p)) or sites.covers(Point(p)): continue
                if self.request.mode=="fill" and not self.new_layout:
                    regions=[r for r in self.context.regions if polygon(r).covers(Point(p))]
                    if not regions or not any(r["landuse"] in ("forest","orchard","park","scrub","grassland") for r in regions):
                        if random.random()<.12 and not Point(p).buffer(2*scale).intersects(self.forbidden):
                            self.surface("env-cover-%d-%d"%(ix,iy),Point(p).buffer(1.5*scale,quad_segs=3),"grass",p)
                        continue
                # Correlated habitat density plus independent jitter yields
                # groves with enforced spacing rather than a uniform point fog.
                cluster=.45+.3*math.sin(p[0]/(85*scale))*math.cos(p[1]/(100*scale))
                if self.profile.id=="snow-mountain": cluster*=max(.15,1-self.height(*p)/180)
                if random.random()>cluster*self.request.density: continue
                model=random.choice(self.profile.natural_assets)
                if self.profile.id=='deep-forest' and random.random()<.20:
                    model=random.choice(('richer-grove-0','richer-grove-1','richer-rock-0'))
                self.place("env-nature-%d-%d"%(ix,iy),model,p,random.randrange(360),natural=True)

    def terrain_stage(self):
        if self.request.mode!="new": return
        x,y,X,Y=self.window.bounds
        for cy in range(math.ceil((Y-y)/32)):
            for cx in range(math.ceil((X-x)/32)):
                values=[round(self.height(x+cx*32+i*2,y+cy*32+j*2)*100)+10000 for j in range(17) for i in range(17)]
                if not all(0<=v<=65535 for v in values): raise ValueError("Terrain exceeds 16-bit height profile")
                picture=Image.new("I",(17,17));picture.putdata(values)
                stream=io.BytesIO();picture.convert("I;16").save(stream,format="PNG",compress_level=9)
                data=stream.getvalue();path="terrain/"+digest(data)+".png";self.payloads[path]=data
                self.add("heightmaps",dict(cell=dict(x=cx,y=cy),path=path,spacing_cm=200,offset_cm=-10000,step_cm=1,source_accuracy_cm=None),(x+cx*32+16,y+cy*32+16))

    def quality_stage(self):
        required={r.id for r in self.profile.rules};present={s["group"] for s in self.sites}
        if not self.water.is_empty: present.update(r.id for r in self.profile.rules if r.landuse=="water")
        if self.profile.id=='neon-harbor' and any(r['kind']=='bridge' for r in self.doc['roads']): present.add('bridge')
        if self.profile.id=='sky-park' and any(r['kind']=='elevated' for r in self.doc['roads']): present.add('elevated-walkways')
        missing=sorted(required-present) if self.request.mode=="new" else []
        # Facilities that cannot be placed are visible blocking diagnostics.
        errors=["Missing required group: "+name for name in missing]
        for site in self.sites:
            if site["access"]>150*self.scale: errors.append("Facility access too far: "+site["id"])
            if site["entrance"].intersects(self.protected) or site["entrance"].intersects(self.water): errors.append("Blocked facility access: "+site["id"])
            rule=next(r for r in self.profile.rules if r.id==site['group'])
            if self.request.mode=='new' and site['id'].startswith('env-facility-') and not all(site['id']+'-object-'+str(i) in site['objects'] for i in range(len(rule.objects))): errors.append('Incomplete facility objects: '+site['id'])
        return dict(errors=errors,stages=self.diagnostics,required=sorted(required),present=sorted(present),
            counts={f:len(self.doc.get(f,[])) for f in FIELDS},facilities=len(self.sites),
            texture_memory_bytes=sum(r["texture_memory_bytes"] for r in self.asset_reports.values()),
            payload_bytes=sum(map(len,self.payloads.values())),assets=self.asset_reports,
            inferred_game_environment=True,source_denominator=self.context.source_denominator if self.request.mode=="fill" else 1)

    def run(self):
        self.water_stage();self.districts_stage();self.road_stage();self.approaches_stage();self.driving_stage();self.fixed_stage();self.facilities_stage();self.details_stage();self.nature_stage();self.terrain_stage()
        diagnostics=self.quality_stage()
        self.owned.sort(key=lambda r:(r['field'],r['id']))
        metadata=dict(version=1,owner=OWNER,new_layout=self.new_layout,algorithm=fingerprint(),request={k:v for k,v in asdict(self.request).items() if k not in ('mode','bounds_cm')},owned=self.owned,
            inference="Estimated game environment; not surveyed source data",sites=[{k:v for k,v in s.items() if k not in ("geometry","entrance")} for s in self.sites])
        attribution=dict(source=self.family+":"+digest(self.doc['bounds'])[:12],license="MIT",notice=canonical(metadata).decode())
        self.doc["attributions"].append(attribution)
        patches=diff(self.original,self.doc)
        history=len(canonical(dict(label="Generate environment",patches=patches)))+sum(map(len,self.payloads.values()))
        diagnostics["history_bytes"]=history
        if self.request.mode=="fill" and history>HISTORY_BYTES:
            diagnostics["errors"].append("Exceeds 16 MiB Undo budget; reduce the selected area")
        return GenerationResult(self.doc,patches,self.payloads,self.owned,diagnostics,metadata,digest(self.original),fingerprint())


def record_id(field,record):
    if field=="heightmaps": return json.dumps(record["cell"],sort_keys=True,separators=(",",":"))
    if field=="attributions": return json.dumps([record["source"],record["license"],record["notice"]],ensure_ascii=False,separators=(",",":"))
    return record["id"]


def diff(before,after):
    result=[]
    for field in (*FIELDS,"attributions"):
        a={record_id(field,r):r for r in before.get(field,[])};b={record_id(field,r):r for r in after.get(field,[])}
        for identity in sorted(a.keys()|b.keys()):
            if a.get(identity)!=b.get(identity): result.append(dict(field=field,id=identity,before=a.get(identity),after=b.get(identity)))
    return result


def generate(request,context,kit): return Generator(request,context,kit).run()


def new_context(request):
    x,y,X,Y=request.bounds_cm
    document=empty("environment-"+request.theme+"-"+str(request.seed),X-x,3200)
    document.update(free_roam=True,bounds=dict(min=[x,y],max=[X,Y]),seed=request.seed,water_bodies=[],surface_areas=[],gimmicks=[],courses=[])
    p=PROFILES[request.theme]
    document["theme"]="urban" if p.urban else "rural"
    document["provenance"].update(tool_id=OWNER,build_id="environment-v1",fingerprint=fingerprint(),first_created="2026-10-08T00:00:00Z",last_edited="2026-10-08T00:00:00Z")
    document["environment"]=dict(version=1,start_minutes=1260 if request.theme=="neon-harbor" else 720,
        concept="polar" if request.theme=="snow-mountain" else "desert" if request.theme=="red-canyon" else "metropolis" if p.urban else "countryside",
        architecture="modern" if p.urban else "rural",climate="polar" if request.theme=="snow-mountain" else "arid" if request.theme=="red-canyon" else "temperate",
        settlement="urban" if p.urban else "wilderness" if request.theme=="deep-forest" else "village",
        latitude_mdeg=37000,longitude_mdeg=127000,utc_offset_minutes=540,sunrise_minutes=360,sunset_minutes=1080,regions=[],lights=[],ground_color=list(p.ground_color))
    return GenerationContext(document)


def write_result(result,directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=False)
    for path,data in result.assets.items():
        target=directory/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    (directory/"document.json").write_bytes(canonical(result.document))
    report={k:v for k,v in asdict(result).items() if k not in ("assets","document")}
    report["payloads"]={p:digest(data) for p,data in result.assets.items()}
    (directory/"generation.json").write_bytes(canonical(report))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request",type=Path);parser.add_argument("destination",type=Path);parser.add_argument("--kit",type=Path,required=True)
    args=parser.parse_args()
    if args.request.stat().st_size>24*1024*1024: raise ValueError("Generation request exceeds 24 MiB")
    raw=json.loads(args.request.read_text());request=GenerationRequest(**raw["generation"])
    if raw.get("kind")=="environment":
        parent=os.getppid()
        def watch():
            deadline=time.monotonic()+600
            while os.getppid()==parent and time.monotonic()<deadline: time.sleep(.1)
            os._exit(3)
        threading.Thread(target=watch,daemon=True).start()
    context=new_context(request) if request.mode=="new" else GenerationContext.from_document(raw["document"],raw.get("project",""),request.bounds_cm)
    result=generate(request,context,args.kit)
    write_result(result,args.destination)
    print(json.dumps(result.diagnostics,sort_keys=True))


if __name__=="__main__": main()
