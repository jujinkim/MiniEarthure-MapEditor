"""Synthetic source precedence, geometry, provenance and local-only composition."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pyproj
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box, mapping, Polygon, LineString
from shapely.ops import transform, unary_union
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import regional
import regional_composition as composition
from osm_generalize import Generalizer
from geojson import convert
from import_layer import reset_limits
from reference_maps import empty, road

SHA="a"*64

class Regional(unittest.TestCase):
    def setUp(self):
        reset_limits()
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.catalog=regional.catalogue()
        self.request=dict(version=1,profile=dict(architecture="korean_modern",climate="temperate",settlement="city",terrain="plain"))
        self.options=dict(mode="wgs84-utm",origin=[9,55],local_origin_m=[300,300])
        self.projection=pyproj.Transformer.from_crs(4326,32632,always_xy=True)
        x,y=self.projection.transform(9,55)
        self.inverse=lambda a,b,z=None:self.projection.transform(np.asarray(a)+x,np.asarray(b)+y,direction="INVERSE")
    def feature(self, identity, geometry, **properties):
        return dict(type="Feature",geometry=json.loads(json.dumps(mapping(transform(self.inverse,geometry)))),properties=dict(osm_source_id=f"way/{identity}",**properties))
    def collection(self,features):return dict(type="FeatureCollection",features=features)
    def annotate(self,features,request=None):return regional.annotate(self.collection(features),request or self.request,SHA,self.catalog)
    def snapshot(self, features):
        bbox=[8.99,54.99,9.01,55.01]
        value=dict(type="FeatureCollection",release="2026-10-21.0",bbox=bbox,features=features)
        path=self.root/"buildings.json";path.write_text(regional.canonical(value))
        return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),release=value["release"],bbox=bbox,source_url="https://example.invalid/synthetic",license="MIT synthetic")
    def test_overture_compact_osm_ids_keep_source_identity(self):
        self.assertEqual(regional.source_ids(dict(sources=[dict(record_id="w204720691@1"),dict(record_id="r123@8"),dict(record_id="https://www.openstreetmap.org/way/456")])), {"way/204720691", "relation/123", "way/456"})

    def test_acquisition_failure_and_existing_destination_preserve_outputs(self):
        from unittest.mock import patch
        import acquire_regional_sources as acquisition
        target=self.root/"snapshot"
        def first(bounds,directory):
            file=directory/"cover.tif";file.write_bytes(b"synthetic")
            return file,[]
        with patch.object(acquisition,"worldcover",first), patch.object(acquisition,"buildings",side_effect=ValueError("missing source")):
            with self.assertRaisesRegex(ValueError,"missing source"):acquisition.acquire([9,55,9.01,55.01],target,self.root/"cache")
        self.assertFalse(target.exists())
        target.mkdir();original=target/"keep";original.write_text("user data")
        with self.assertRaisesRegex(ValueError,"destination exists"):acquisition.acquire([9,55,9.01,55.01],target,self.root/"cache")
        self.assertEqual(original.read_text(),"user data")

    def test_source_roofs_and_blue_dome_require_matching_type(self):
        suffix, shape, evidence = regional.roof_style({"roof:shape":"dome","roof:colour":"blue"},{},{},"cycladic","religious",self.catalog)
        self.assertEqual((suffix,shape),("/dome/blue_tile","dome"))
        self.assertEqual(evidence["roof_shape"],"source:roof")
        suffix, _, _ = regional.roof_style({"roof:shape":"vault","roof:colour":"blue"},{},{},"cycladic","detached",self.catalog)
        self.assertEqual(suffix,"/vault/whitewash")
        suffix, _, evidence = regional.roof_style({"roof:shape":"gabled","roof:material":"roof_tiles"},{},{"roof_shape":"flat","roof_material":"metal"},"venetian","hotel",self.catalog)
        self.assertEqual(suffix,"/flat/metal")
        self.assertEqual(evidence["roof_shape"],"author")
        suffix, _, evidence = regional.roof_style({"roof:shape":"dome","roof:colour":"blue"},{},{"roof_material":"whitewash"},"cycladic","religious",self.catalog)
        self.assertEqual(suffix,"/dome/whitewash")
        self.assertEqual(evidence["roof_material"],"author")
        with self.assertRaisesRegex(ValueError,"religious dome"):
            regional.roof_style({}, {}, {"roof_shape":"flat","roof_material":"blue_tile"},"cycladic","detached",self.catalog)

    def test_source_vegetation_and_polar_scrub_survive_zone_conversion(self):
        from osm_generalize import city_zone
        f=self.feature(1,box(0,0,80,80),landuse="scrub",osm_region=True,_city_source_tags={"natural":"scrub"})
        request=deepcopy(self.request);request["profile"]["climate"]="polar"
        value,_=self.annotate([f],request)
        p=value["features"][0]["properties"]
        self.assertEqual(p["style_id"],"vegetation/polar_scrub")
        zone=city_zone(p,box(0,0,80,80),3)
        self.assertEqual(zone["tree"],dict(asset_id="builtin:shrub",radius_cm=42,clearance_cm=30))
        forest=self.feature(2,box(0,0,80,80),landuse="forest",_city_source_tags={"natural":"wood","leaf_type":"broadleaved"})
        value,_=self.annotate([forest],request)
        self.assertEqual(value["features"][0]["properties"]["style_id"],"vegetation/deciduous")

    def test_detailed_types_and_style_boundaries_keep_original_footprints(self):
        features=[self.feature(i+1,box(i*30,20,i*30+12,35),_city_building=kind,_city_source_tags={"building":kind},height_m=height) for i,(kind,height) in enumerate([( "school",7),("hospital",21),("apartments",55),("barn",5),("church",12)])]
        before=deepcopy(features)
        annotated,receipt=self.annotate(features)
        candidate,meta=Generalizer(annotated,self.options,scale=3).candidate(64)
        self.assertIsNotNone(candidate)
        buildings=[f for f in candidate["features"] if f["properties"].get("style_id","").startswith("building/")]
        self.assertEqual({f["properties"]["style_id"].split("/")[2] for f in buildings},{"school","hospital","residential_tower","barn","religious"})
        self.assertEqual(len(buildings),5)
        self.assertEqual(features,before)
        self.assertTrue(all(f["properties"]["height_m"] in (7,21,55,5,12) for f in buildings))
        layer=convert(candidate,"synthetic","MIT",coordinates=self.options,osm_graph=True,city=True,denominator=3)
        self.assertEqual({p["after"]["style_id"] for p in layer.patches if p["field"]=="buildings"},{f["properties"]["style_id"] for f in buildings})
    def test_pedestrian_paint_keeps_different_styles_with_shared_physics(self):
        features=[self.feature(1,LineString([(0,0),(30,0)]),width_m=2,surface="concrete",_city_refs=[1,2],_city_road_tags=dict(highway="footway",surface="concrete")),
                  self.feature(2,LineString([(30,0),(60,0)]),width_m=2,surface="concrete",_city_refs=[2,3],_city_road_tags=dict(highway="footway",surface="paving_stones"))]
        annotated,_=self.annotate(features)
        candidate,_=Generalizer(annotated,self.options,scale=3).candidate(0)
        paint=[f for f in candidate["features"] if f["properties"].get("_city_paint")]
        self.assertEqual({f["properties"]["style_id"] for f in paint},{"ground/concrete","ground/pavers"})
        self.assertEqual({f["properties"]["_city_paint"] for f in paint},{"concrete"})

    def test_author_source_auxiliary_context_precedence_and_hash_guard(self):
        geometry=box(10,10,25,25)
        feature=self.feature(1,geometry,_city_building="school",_city_source_tags={"building":"school","building:material":"brick"},height_m=7,_city_levels=20)
        aux=self.feature(9,geometry);aux["properties"]=dict(id="synthetic-gers",height=60,**{"class":"hospital"},facade_material="glass",sources=[])
        request=deepcopy(self.request);request["buildings"]=self.snapshot([aux])
        annotated,_=self.annotate([feature],request)
        p=annotated["features"][0]["properties"]
        self.assertEqual(p["height_m"],7);self.assertEqual(p["style_id"],"building/korean_modern/school/brick")
        candidate,_=Generalizer(annotated,self.options,scale=3).candidate(0)
        self.assertEqual(candidate["features"][0]["properties"]["height_m"],7,"explicit height wins over incompatible floor count")
        request["overrides"]=dict(osm_sha256=SHA,objects=[dict(source_id="way/1",height_m=9,building_type="university",material="stone")])
        p=self.annotate([feature],request)[0]["features"][0]["properties"]
        self.assertEqual(p["height_m"],9);self.assertEqual(p["style_id"],"building/korean_modern/university/stone")
        request["overrides"]["osm_sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"exact OSM"):self.annotate([feature],request)
        del request["overrides"]; del feature["properties"]["height_m"];del feature["properties"]["_city_levels"]
        self.assertEqual(self.annotate([feature],request)[0]["features"][0]["properties"]["height_m"],60)
        Path(request["buildings"]["path"]).write_text("damaged")
        with self.assertRaisesRegex(ValueError,"SHA-256"):self.annotate([feature],request)
    def test_ordered_regions_and_conservative_unknown_height(self):
        request=deepcopy(self.request)
        request["regions"]=[dict(id="farm",polygon=list(map(list,transform(self.inverse,box(-10,-10,50,50)).exterior.coords[:-1])),profile=dict(architecture="farm",settlement="rural"))]
        features=[self.feature(1,box(0,0,10,10),_city_building="yes"),self.feature(2,box(60,0,70,10),_city_building="yes")]
        a,_=self.annotate(features,request);b,_=self.annotate(list(reversed(features)),request)
        one,_=Generalizer(a,self.options,scale=3).candidate(64);two,_=Generalizer(b,self.options,scale=3).candidate(64)
        styles={f["properties"]["style_id"] for f in one["features"]}
        self.assertEqual(styles,{"building/farm/detached/wood","building/korean_modern/lowrise/concrete"})
        heights=[f["properties"]["height_m"] for f in one["features"]]
        self.assertEqual(heights,[6,6]);self.assertEqual(one,two)
    def document(self, request):
        doc=empty("regional-synthetic",20000,6400);doc["free_roam"]=True
        c=dict(mode="wgs84-utm",axis_order="longitude-latitude",origin=[9,55],local_origin_m=[300,300],target_crs="EPSG:32632",osm_city=dict(scale_denominator=3,source_ids=["way/1"]),osm_crop=dict(bbox=[8.998,54.998,9.002,55.002]),regional=dict(request=regional.input_receipt(request)))
        doc["attributions"].append(dict(source="synthetic OSM",license="MIT",notice=json.dumps(dict(adapter="osm-extract-v1",source=dict(sha256=SHA),coordinates=c))))
        road(doc,"road",[[0,0,10000],[20000,0,10000]],width=500)
        doc["buildings"]=[dict(id="building",footprint=[[5000,5000],[6000,5000],[6000,6000],[5000,6000]],base_cm=0,height_cm=300,usage="residential",material="concrete",roof="flat")]
        doc["surface_areas"]=[dict(id="park",polygon=[[12000,5000],[15000,5000],[15000,8000],[12000,8000]],surface="grass",style_id="ground/managed_lawn")]
        doc["barriers"]=[dict(id="fence",kind="fence",line=[[7000,10500],[9000,10500]],height_cm=100,thickness_cm=10)]
        doc["water_bodies"]=[dict(id="water",polygon=[[5000,13000],[8000,13000],[8000,15000],[5000,15000]],islands=[],surface_cm=0,bottom_cm=-100,flow_cm_s=[0,0])]
        return doc
    def cover(self, request, code=50):
        path=self.root/"cover.tif"
        with rasterio.open(path,"w",driver="GTiff",width=120,height=120,count=1,dtype="uint8",crs="EPSG:4326",transform=from_origin(8.995,55.005,1/12000,1/12000)) as dst:dst.write(np.full((120,120),code,dtype="uint8"),1)
        request["worldcover"]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),release="2021-v200",bbox=[8.995,54.995,9.005,55.005],source_url="https://example.invalid/synthetic",license="MIT synthetic")
    def test_cover_preserves_park_water_roads_and_buildings_deterministically(self):
        request=deepcopy(self.request);self.cover(request)
        doc=self.document(request);before=deepcopy(doc)
        out,report=composition.compose(doc,request,self.catalog)
        again,other=composition.compose(doc,request,self.catalog)
        self.assertEqual(out,again);self.assertEqual(report,other);self.assertEqual(doc,before)
        generated=unary_union([Polygon(p["polygon"]) for p in out["surface_areas"] if p["id"].startswith("regional-")])
        for geometry in (box(12000,5000,15000,8000),box(5000,5000,6000,6000),box(5000,13000,8000,15000),box(0,9750,20000,10250)):
            self.assertLess(generated.intersection(geometry).area,1)
        self.assertGreater(generated.area,100000000)
        self.assertTrue(all(p["style_id"]=="ground/pavers" for p in out["surface_areas"] if p["id"].startswith("regional-")))
        self.assertGreater(report["diagnostics"]["regional"]["counts"]["sidewalk_candidate_m2"],0)
        with self.assertRaisesRegex(ValueError,"already applied"):composition.compose(out,request,self.catalog)
    def test_duplicate_by_source_id_and_overlap_and_missing_parts_fail_atomically(self):
        request=deepcopy(self.request)
        base=self.document(request);notice=composition.osm_notice(base);frame=composition.Frame(notice)
        def geo(local):
            return json.loads(json.dumps(mapping(transform(self.inverse,shapely_scale(local,3/100,-300,-300)))))
        shapes=[box(5000,5000,6000,6000),box(10000,15000,11000,16000),box(1000,15000,2000,16000)]
        features=[dict(type="Feature",geometry=geo(g),properties=dict(id="synthetic-"+str(i),height=9,sources=[dict(dataset="OpenStreetMap",record_id="way/1")] if i==1 else [],**{"class":"school"})) for i,g in enumerate(shapes)]
        request["buildings"]=self.snapshot(features);doc=self.document(request)
        out,report=composition.compose(doc,request,self.catalog)
        counts=report["diagnostics"]["regional"]["counts"]
        self.assertEqual(counts["building_duplicate_source_id"],1);self.assertEqual(counts["building_duplicate_overlap"],1);self.assertEqual(counts["building_added"],1)
        self.assertEqual(len(out["buildings"]),2)
        features[-1]["properties"]["has_parts"]=True
        request["buildings"]=self.snapshot(features);doc=self.document(request);before=deepcopy(doc)
        with self.assertRaisesRegex(ValueError,"parts missing"):composition.compose(doc,request,self.catalog)
        self.assertEqual(doc,before)
    def test_coarse_natural_cover_creates_no_sidewalk_and_bad_classes_fail(self):
        request=deepcopy(self.request);self.cover(request,30)
        doc=self.document(request);out,report=composition.compose(doc,request,self.catalog)
        self.assertEqual(report["diagnostics"]["regional"]["counts"]["sidewalk_candidate_m2"],0)
        self.cover(request,0);doc=self.document(request)
        with self.assertRaisesRegex(ValueError,"missing or unsupported"):composition.compose(doc,request,self.catalog)


def shapely_scale(g, scale,x,y):
    from shapely.affinity import scale as scaling, translate
    return translate(scaling(g,xfact=scale,yfact=scale,origin=(0,0)),xoff=x,yoff=y)

if __name__=="__main__":unittest.main()
