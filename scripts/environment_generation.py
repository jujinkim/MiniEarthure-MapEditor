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
from environment_assets import library as module_library, support_module
from environment_composition import Composition
from environment_layout import digest, rng, polygons, lines, xy, rings, polygon
from environment_metrics import measure
from reference_maps import canonical, empty, road
from driving_features import place as driving_feature

OWNER = "mapeditor-environment-v1"
HISTORY_BYTES = 16 * 1024 * 1024
MAX_OBJECTS = 18000
TILE_METRES = 128
FIELDS = ("nodes", "roads", "buildings", "zones", "placements", "surface_areas", "water_bodies", "gimmicks", "heightmaps", "assets")




def fingerprint():
    files = [Path(__file__).with_name(name) for name in ("environment_generation.py","environment_profiles.py","environment_assets.py","environment_layout.py","environment_composition.py","environment_metrics.py","asset_derivatives.py","city_assets.py","driving_school_map.py","driving_features.py")]
    return digest(b"".join(p.read_bytes() for p in files) + shapely.__version__.encode())














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


class Generator(Composition):
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
        self.prior_metadata = []
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
        self.road_ground_grid = {}

    def _retire_owned(self):
        for attribution in self.doc.get("attributions", []):
            if not attribution.get("source", "").startswith(self.family + ":"): continue
            try: meta = json.loads(attribution["notice"])
            except ValueError: continue
            self.prior_metadata.append(meta)
            # A facility is the ownership unit. Boundary crossings, any manual
            # member edit and member deletion preserve the entire assembly.
            frozen=set()
            for site in meta.get('sites',[]):
                if not site.get('boundaries'): continue
                area=unary_union([polygon(p) for p in site['boundaries']])
                members=[o for o in meta.get('owned',[]) if o['id'].startswith(site['id']+'-')]
                changed=False
                for member in members:
                    current=next((r for r in self.doc.get(member['field'],[]) if record_id(member['field'],r)==member['id']),None)
                    if current is None or digest(stable_record(current))!=member['sha256']: changed=True;break
                if changed or not self.window.buffer(-64*self.scale).covers(area):
                    frozen.update((o['field'],o['id']) for o in members)
                    retained={k:v for k,v in site.items() if k not in ('boundaries','entrances')}
                    retained.update(geometry=area,entrance=unary_union([polygon(p) for p in site.get('entrances',[])]),retained=True)
                    self.sites.append(retained)
            # Ownership survives source edits to the algorithm, not user edits to
            # its objects. Global stable IDs prevent reexecution duplicates.
            self.new_layout |= meta.get("new_layout", meta.get("request", {}).get("mode") == "new")
            for owned in meta.get("owned", []):
                field, identity = owned["field"], owned["id"]
                current = next((r for r in self.doc.get(field,[]) if record_id(field,r)==identity),None)
                if current is None:
                    self.preserved_ids.add((field,identity)) # user deletion is an edit
                    self.owned.append(owned) # Keep the tombstone through later reruns.
                    continue
                position = owned.get("anchor_cm")
                selected = (field,identity) not in frozen and field in ("placements", "surface_areas") and "-pier-" not in identity and position is not None and self.window.buffer(-64*self.scale).covers(Point(position[0]/100,position[1]/100))
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
        # Cut/fill the generated ground to the slope-limited road profile. Infill
        # returned above and never changes imported terrain or source roads.
        key=(math.floor(x/(32*self.scale)),math.floor(y/(32*self.scale)))
        nearby=self.road_ground_grid.get(key,[])
        if nearby:
            edge,a,b,width=min(nearby,key=lambda e:e[0].distance(p))
            distance=edge.distance(p)
            if distance<width+12:
                t=edge.project(p)/max(.01,edge.length)
                level=a+(b-a)*t
                blend=max(0,min(1,(distance-width-1)/11))
                result=level+(result-level)*blend
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


    def asset(self,identity):
        key=identity+"-env-"+str(self.context.source_denominator if self.request.mode=="fill" else 1)+"-"+str(self.request.texture_profile)
        existing=next((a for a in self.doc["assets"] if a["id"]==key),None)
        if existing: return existing
        if identity.startswith('environment-pier-h') and identity not in self.modules:
            self.modules[identity]=support_module(int(identity.split('-h')[-1]))
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
            # Aprons can join a ramp to a local street at the same final level.
            # Node identity follows the emitted 3D geometry, not pre-apron height.
            nodes={}
            for record in self.doc['roads']:
                for end,point in (('from',record['points'][0]),('to',record['points'][-1])):
                    identity='env-node-'+digest(point)[:14]
                    record[end]=identity;nodes[identity]=dict(id=identity,position=point,level=0 if point[1]==0 else 1)
            self.doc['nodes']=sorted(nodes.values(),key=lambda n:n['id'])
        self.diagnostics.append(dict(stage='approaches',level_aprons=len(aprons)))

    def footprint(self,record,position,yaw,foliage=True):
        points=[]
        for proxy in record.get("collision",[]):
            c,s=proxy["center"],proxy["size_cm"]
            points.extend((c[0]+a*s[0]/2,c[2]+b*s[2]/2) for a in (-1,1) for b in (-1,1))
        for convex in record.get("convex_collision",[]): points.extend((p[0],p[2]) for p in convex["vertices"])
        # Canopies have narrow trunk proxies; reserve their visual footprint too.
        if foliage and any(k in record["id"] for k in ("canopy","pine","grove")):
            r=(8 if 'mature' in record['id'] else 5 if record["id"].startswith("environment-canopy") else 4 if "grove" not in record["id"] else 2)*self.scale
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
        if self.surface_polys: area = area.difference(unary_union(self.surface_polys).buffer(.03,join_style=2))
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
            emitted=shapely.affinity.scale(snapped,.01,.01,origin=(0,0))
            # Acute triangulation tips can move outward under centimetre rounding.
            # Reject only that residual ground sliver, never a facility/collider.
            if any(emitted.intersection(existing).area>1e-9 for existing in self.surface_polys): continue
            if self.add("surface_areas",dict(id=identity+"-"+str(index),polygon=outer,surface=material),anchor): self.surface_polys.append(emitted)

    def place(self,identity,model,point,yaw=0,plot=None,natural=False,clearance=.8):
        if ("placements",identity) in self.preserved_ids: return False
        point=(round(point[0]*100)/100,round(point[1]*100)/100)
        yaw=round(yaw*1000)/1000
        asset=self.asset(model);area=self.footprint(asset,point,yaw)
        # Closed woodland may interlock soft crowns, while every solid trunk
        # keeps its full collision proxy. Roads, water and facility lots still
        # reserve the visual canopy envelope.
        occupied=self.footprint(asset,point,yaw,False) if natural and any(k in model for k in ('canopy','pine','sapling')) else area
        if not self.window.covers(area.buffer(.1*self.scale)) or (plot is not None and not plot.covers(area)):
            return False
        gap=max(.025,clearance*self.scale)
        if area.intersects(self.forbidden) or any(occupied.intersection(p).area>1e-8 or occupied.distance(p)<gap for p in self.nearby(occupied.buffer(gap))): return False
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
        self.occupied.append(occupied)
        self.index_occupied(occupied)
        return True

    def footing_limit(self, area):
        return max((4 if self.request.mode=='new' else 2)*self.scale,math.sqrt(area.area)*(.25 if self.request.mode=='new' else .12))



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
                for i in range(1,int(line.length/4)):
                    p=line.interpolate(i*4);q=line.interpolate(min(line.length,i*4+1))
                    angle=math.atan2(q.y-p.y,q.x-p.x)
                    self.place(record['id']+'-guard-'+str(i),'environment-guardrail',(p.x-math.sin(angle)*5,p.y+math.cos(angle)*5),math.degrees(angle),clearance=0)
        if self.request.mode!='new': return
        # Shared native roads supply deck collision; explicit piers supply the
        # load-bearing structure. They stop below decks and keep ground roads clear.
        for record,line in zip(self.doc['roads'],self.road_lines):
            if record['kind'] not in ('elevated','bridge'): continue
            if line.length<12: continue
            samples=[line.length/2] if line.length<80 else list(range(40,int(line.length),40))
            for i,distance in enumerate(samples):
                chosen=None
                for candidate in (distance,line.length*.25,line.length*.75):
                    p=line.interpolate(candidate);q=line.interpolate(min(line.length,candidate+1))
                    yaw=math.degrees(math.atan2(q.y-p.y,q.x-p.x))
                    footing=self.footprint(self.asset('environment-pier'),(p.x,p.y),yaw)
                    if not any(footing.intersects(buffer) for r,buffer in zip(self.doc['roads'],self.road_buffers) if r['kind']=='ground'):
                        chosen=(p,yaw);break
                # A crossing is spanned from adjacent deck supports; a pier may
                # never obstruct the ground road beneath it.
                if chosen is None: continue
                p,yaw=chosen
                deck=min(point[1] for point in record['points'])/100
                ground=min(self.height(p.x+dx,p.y+dy) for dx,dy in ((0,0),(-3,-1),(3,1)))-.25
                if deck-ground<2: continue
                height_cm=math.ceil((deck-ground-.12)*100)
                a=self.asset('environment-pier-h'+str(height_cm))
                level=deck-height_cm/100-.12
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
                if length>1000 and grade<.10: candidates.append((r,a,b))
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
        if self.doc['roads']: present.update(r.id for r in self.profile.rules if r.landuse=='transport' and not r.objects and r.id not in ('bridge','elevated-walkways'))
        if not self.water.is_empty: present.update(r.id for r in self.profile.rules if r.landuse=="water")
        if self.profile.id=='neon-harbor' and any(r['kind']=='bridge' for r in self.doc['roads']): present.add('bridge')
        if self.profile.id=='sky-park' and any(r['kind']=='elevated' for r in self.doc['roads']): present.add('elevated-walkways')
        missing=sorted(required-present) if self.request.mode=="new" else []
        # Facilities that cannot be placed are visible blocking diagnostics.
        errors=["Missing required group: "+name for name in missing]
        errors.extend(d['error']+': '+d['id'] for d in self.diagnostics if d.get('required_failure'))
        for site in self.sites:
            if site["access"]>150*self.scale: errors.append("Facility access too far: "+site["id"])
            if site["entrance"].intersects(self.protected) or site["entrance"].intersects(self.water): errors.append("Blocked facility access: "+site["id"])
            rule=next(r for r in self.profile.rules if r.id==site['group'])
            if self.request.mode=='new' and site['id'].startswith('env-facility-') and len(site['objects'])<len(rule.objects): errors.append('Incomplete facility objects: '+site['id'])
        metrics,composition_errors,issues=measure(self)
        errors.extend(composition_errors);self.diagnostics.extend(issues)
        return dict(errors=errors,stages=self.diagnostics,metrics=metrics,required=sorted(required),present=sorted(present),
            counts={f:len(self.doc.get(f,[])) for f in FIELDS},facilities=len(self.sites),
            texture_memory_bytes=sum(r["texture_memory_bytes"] for r in self.asset_reports.values()),
            payload_bytes=sum(map(len,self.payloads.values())),assets=self.asset_reports,
            inferred_game_environment=True,source_denominator=self.context.source_denominator if self.request.mode=="fill" else 1)

    def run(self):
        self.water_stage();self.districts_stage();self.road_stage();self.approaches_stage();self.driving_stage();self.fixed_stage();self.facilities_stage();self.details_stage();self.nature_stage();self.terrain_stage()
        self.sites.sort(key=lambda s:s['id'])
        diagnostics=self.quality_stage()
        self.owned.sort(key=lambda r:(r['field'],r['id']))
        metadata=dict(version=1,owner=OWNER,new_layout=self.new_layout,algorithm=fingerprint(),request={k:v for k,v in asdict(self.request).items() if k not in ('mode','bounds_cm')},owned=self.owned,
            inference="Estimated game environment; not surveyed source data",**self.composition_metadata())
        metadata["metrics"]=diagnostics["metrics"]
        diagnostics["composition"]=self.composition_metadata()
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
