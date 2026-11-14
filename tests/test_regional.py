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
from shapely.geometry import box, mapping, Polygon, LineString, Point, MultiPolygon
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
    def test_public_amenity_overrides_generic_building_in_sparse_region(self):
        request=deepcopy(self.request);request["profile"].update(settlement="sparse",architecture="modern")
        features=[self.feature(i+1,box(i*30,0,i*30+12,15),_city_building="yes",_city_source_tags={"building":"yes","amenity":amenity}) for i,amenity in enumerate(("ranger_station","bus_station"))]
        annotated,_=self.annotate(features,request)
        properties=[f["properties"] for f in annotated["features"]]
        self.assertEqual([p["style_id"].split("/")[2] for p in properties],["civic","station"])
        self.assertTrue(all(p["_city_regional"]["evidence"]["type"]=="source:amenity" for p in properties))

    def test_authorized_carriageway_cut_preserves_other_geometry_and_discloses_extent(self):
        request=deepcopy(self.request);request["road_conflicts"]="trim_buildings"
        features=[self.feature(1,LineString([(0,0),(40,0)]),width_m=4,_city_refs=[1,2],_city_road_tags={"highway":"residential","width":"4","sidewalk":"both"}),
                  self.feature(2,box(10,1,20,8),_city_building="school",height_m=9,_city_source_tags={"building":"school"}),
                  self.feature(3,box(25,4,35,10),_city_building="hospital",height_m=18,_city_source_tags={"building":"hospital"})]
        original=deepcopy(features)
        annotated,_=self.annotate(features,request);worker=Generalizer(annotated,self.options,scale=3)
        out,meta=worker.candidate(64)
        edits=meta["road_footprint_corrections"]
        self.assertEqual(len(edits),1)
        self.assertEqual(edits[0]["source_ids"],["way/2"]);self.assertEqual(edits[0]["road_sources"],["way/1"])
        self.assertAlmostEqual(edits[0]["removed_area_m2"],11.2,places=3)
        self.assertEqual(edits[0]["clearance_map_cm"],4)
        self.assertGreater(Polygon(edits[0]["removed_wgs84"]["coordinates"][0]).area,0)
        buildings=[f for f in out["features"] if f["properties"].get("style_id","").startswith("building/")]
        self.assertEqual({f["properties"]["height_m"] for f in buildings},{9,18})
        self.assertEqual({f["properties"]["style_id"].split("/")[2] for f in buildings},{"school","hospital"})
        self.assertEqual(worker.candidate(64)[1]["road_footprint_corrections"],edits)
        self.assertEqual(features,original)
        # A missing policy keeps the original footprint, including a source conflict.
        strict,_=self.annotate(features);_,strict_meta=Generalizer(strict,self.options,scale=3).candidate(64)
        self.assertEqual(strict_meta["road_footprint_corrections"],[])
        covered=self.feature(4,box(10,-1,20,1),_city_building="yes")
        annotated,_=self.annotate([features[0],covered],request)
        with self.assertRaisesRegex(ValueError,"entirely inside the carriageway"):
            Generalizer(annotated,self.options,scale=3).candidate(64)

    def test_narrow_right_angle_reserves_quantized_inner_fillet(self):
        from regional_road_conflicts import corridors, trim
        road = dict(properties=dict(width_m=3.75, _city_point_refs=[1,2,3]))
        index = corridors([(road,LineString([(30,0),(0,0),(0,30)]))],3,lambda f:["way/1"])
        # Coincident rounded mouths expose the full concave corner fillet;
        # treating its tiny pre-rounding edge as a tangent misses this area.
        building = box(2.01,2.01,6,6)
        result, sources, removed = trim(building,index)
        self.assertEqual(sources,["way/1"])
        self.assertGreater(removed.area,0)
        self.assertFalse(result.covers(Point(2.01,2.01)))
        self.assertTrue(result.covers(Point(6,6)))

    def test_road_corner_rounding_is_translation_invariant_on_map_lattice(self):
        from regional_road_conflicts import corridors, trim
        from shapely.affinity import translate
        # Odd map-centimetre widths put mouth offsets on half-centimetres.
        # Rounding absolute negative positions would hide a concave fillet.
        road = {"properties":{"width_m":3.75}}
        line = LineString([(4.86,0),(0,0),(0,27.72)])
        building = box(-2.01,-2.85,-1.41,-.12)
        reference = None
        for dx,dy in [(0,0),(27.12,-1263.45),(1563.12,272.55),(-100.02,100.02)]:
            index=corridors([(road,translate(line,dx,dy))],3,lambda f:["way/1"])
            result,ids,removed=trim(translate(building,dx,dy),index)
            self.assertEqual(ids,["way/1"])
            self.assertGreater(removed.area,.8)
            local=translate(result,-dx,-dy)
            if reference is None:reference=local
            else:self.assertLess(reference.symmetric_difference(local).area,1e-8)

    def test_bridge_collision_edge_keeps_buildings_below_the_deck(self):
        from regional_road_conflicts import corridors, trim
        road=dict(properties=dict(width_m=2,road_kind="bridge",elevations_m=[10,10]))
        index=corridors([(road,LineString([(0,0),(30,0)]))],3,lambda f:["way/1"])
        building=box(10,1.2,20,5)
        low,ids,_=trim(building,index,6)
        self.assertTrue(low.equals(building));self.assertEqual(ids,[])
        tall,ids,removed=trim(building,index,12)
        self.assertEqual(ids,["way/1"]);self.assertGreater(removed.area,0)
        self.assertTrue(tall.covers(Point(15,5)))

    def test_tunnel_ceiling_clearance_preserves_buried_parts_and_cuts_shallow_portal(self):
        from regional_road_conflicts import corridors, trim
        road=dict(properties=dict(width_m=2,road_kind="tunnel",elevations_m=[-6,-6],clearance_m=4.5))
        building=box(10,-2,20,5)
        index=corridors([(road,LineString([(0,0),(30,0)]))],3,lambda f:["way/1"])
        retained,ids,_=trim(building,index,9,0)
        self.assertTrue(retained.equals(building));self.assertEqual(ids,[])
        road["properties"]["elevations_m"]=[-6,0]
        index=corridors([(road,LineString([(0,0),(30,0)]))],3,lambda f:["way/1"])
        cut,ids,removed=trim(building,index,9,0)
        self.assertEqual(ids,["way/1"]);self.assertGreater(removed.area,0)
        self.assertGreater(cut.area,0);self.assertTrue(cut.covers(Point(15,5)))

    def test_tunnel_bend_fan_uses_the_sloping_neighbour_ceiling(self):
        from regional_road_conflicts import corridors, trim
        # A buried bend whose next segment climbs to a portal: MapKit's fan at the
        # bend interpolates toward the shallower neighbour, so it is cut.
        road=dict(properties=dict(width_m=2,road_kind="tunnel",elevations_m=[-6,-6,-2],clearance_m=4.5))
        index=corridors([(road,LineString([(0,0),(30,0),(30,30)]))],3,lambda f:["way/1"])
        beside_bend=box(25,-3,35,-1.05)
        cut,ids,removed=trim(beside_bend,index,9,0)
        self.assertEqual(ids,["way/1"]);self.assertGreater(removed.area,0)
        beside_flat=box(10,-3,20,-1.05)
        kept,ids,_=trim(beside_flat,index,9,0)
        self.assertTrue(kept.equals(beside_flat));self.assertEqual(ids,[])

    def test_one_conflicting_tunnel_piece_cuts_every_overlap_of_that_road(self):
        from regional_road_conflicts import corridors, trim
        # MapKit's exemption is all-or-nothing per building and road: a footprint
        # over both the buried stretch and the climbing ramp loses both overlaps,
        # never keeping a notch wrapped around the exempt part.
        road=dict(properties=dict(width_m=2,road_kind="tunnel",elevations_m=[-6,-6,0],clearance_m=4.5))
        index=corridors([(road,LineString([(0,0),(20,0),(40,0)]))],3,lambda f:["way/1"])
        building=box(5,-4,30,4)
        cut,ids,removed=trim(building,index,9,0)
        self.assertEqual(ids,["way/1"])
        self.assertEqual(cut.geom_type,"MultiPolygon")
        self.assertFalse(cut.intersects(box(6,-.5,7,.5)))
        buried=box(5,-4,12,4)  # clear of the bend fan at x=20
        kept,ids,_=trim(buried,index,9,0)
        self.assertTrue(kept.equals(buried));self.assertEqual(ids,[])

    def test_road_sidewalks_follow_the_architecture_at_the_road(self):
        road=lambda:[self.feature(1,LineString([(0,0),(40,0)]),width_m=4,_city_refs=[1,2],_city_road_tags={"highway":"residential"})]
        for architecture,ground in (("european_stone","stone_paving"),("parisian","asphalt"),("korean_modern","pavers")):
            request=deepcopy(self.request);request["profile"]["architecture"]=architecture
            out,_=self.annotate(road(),request)
            self.assertEqual(out["features"][0]["properties"]["sidewalk_style_id"],"ground/"+ground)

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
        heights={f["properties"]["style_id"]:f["properties"]["height_m"] for f in one["features"]}
        # A rural house is one storey under its pitched display roof.
        self.assertEqual(heights,{"building/farm/detached/wood":5,"building/korean_modern/lowrise/concrete":6});self.assertEqual(one,two)
    def test_rural_houses_and_sheds_take_their_use_defaults(self):
        request=deepcopy(self.request);request["profile"].update(settlement="rural")
        features=[self.feature(1,box(0,0,10,10),_city_building="yes"),self.feature(2,box(60,0,80,20),_city_building="yes"),
            self.feature(3,box(120,0,130,10),_city_building="yes",_city_source_tags={"building":"yes","shop":"convenience"})]
        annotated,_=self.annotate(features)
        self.assertEqual([f["properties"]["style_id"] for f in annotated["features"]],["building/korean_modern/lowrise/concrete"]*2+["building/korean_modern/shop/concrete"])
        annotated,_=self.annotate(features,request)
        candidate,_=Generalizer(annotated,self.options,scale=3).candidate(64)
        result={f["properties"]["osm_source_id"]:(f["properties"]["style_id"],f["properties"]["height_m"]) for f in candidate["features"]}
        self.assertEqual(result,{"way/1":("building/korean_modern/detached/plaster",5),"way/2":("building/korean_modern/warehouse/metal",6),
            "way/3":("building/korean_modern/shop/concrete",6)})
        self.assertEqual(regional.use_style(self.catalog,"korean_modern","detached")["roof"],"hipped")
        self.assertEqual(regional.use_style(self.catalog,"korean_modern","shop")["modules"],self.catalog["architectures"]["korean_modern"]["modules"])
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
        attribution=next(a for a in out["attributions"] if a["notice"].startswith("{") and json.loads(a["notice"]).get("adapter")==composition.OWNER)
        self.assertIn("ESA WorldCover",attribution["source"])
        self.assertIn(request["worldcover"]["license"],attribution["license"])
        with self.assertRaisesRegex(ValueError,"already applied"):composition.compose(out,request,self.catalog)
    def test_validation_cells_use_the_document_origin(self):
        request=deepcopy(self.request)
        doc=self.document(request)
        doc["bounds"]={"min":[4000,4000],"max":[20000,20000]}
        doc["cell_size_cm"]=8000
        _,report=composition.compose(doc,request,self.catalog)
        self.assertEqual(report["diagnostics"]["metrics"]["cost_cells"],[dict(x=0,y=0)])

    def test_oblique_source_paint_and_partitioned_cover_never_overlap(self):
        from shapely.strtree import STRtree
        request=deepcopy(self.request);self.cover(request)
        doc=self.document(request)
        doc["surface_areas"][0]["polygon"]=[[12000,5001],[15001,5113],[14777,8179],[12223,8007]]
        out,_=composition.compose(doc,request,self.catalog)
        polygons=[Polygon(p["polygon"]) for p in out["surface_areas"]]
        tree=STRtree(polygons)
        for i,p in enumerate(polygons):
            for j in tree.query(p):
                if j>i:self.assertEqual(p.intersection(polygons[j]).area,0)

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
    def test_auxiliary_building_cannot_replace_retained_road_space(self):
        request=deepcopy(self.request)
        # The source origin maps to [10000,10000], on the existing road.
        geometry=json.loads(json.dumps(mapping(transform(self.inverse,box(-3,-3,3,3)))))
        request["buildings"]=self.snapshot([dict(type="Feature",geometry=geometry,properties=dict(id="road-conflict",height=6,sources=[]))])
        doc=self.document(request);before=deepcopy(doc)
        out,report=composition.compose(doc,request,self.catalog)
        self.assertEqual(out["buildings"],doc["buildings"])
        self.assertEqual(doc,before)
        receipt=report["diagnostics"]["regional"]
        self.assertEqual(receipt["counts"]["building_road_conflict"],1)
        self.assertEqual(receipt["objects"][0]["source_id"],"road-conflict")
        self.assertEqual(receipt["objects"][0]["road_ids"],["road"])

    def test_small_nonzero_boundary_building_keeps_its_integer_area(self):
        request=deepcopy(self.request)
        local=Polygon([[1000,15000],[1006,14997],[1006,14998]])
        geographic=mapping(transform(self.inverse,shapely_scale(local,3/100,-300,-300)))
        request["buildings"]=self.snapshot([dict(type="Feature",geometry=geographic,properties=dict(id="boundary-tip",height=6,sources=[]))])
        out,_=composition.compose(self.document(request),request,self.catalog)
        building=next(b for b in out["buildings"] if b["id"].startswith("regional-"))
        self.assertEqual(Polygon(building["footprint"]).area,3)

    def test_point_touching_auxiliary_components_keep_one_source_owner(self):
        request=deepcopy(self.request)
        local=MultiPolygon([box(1000,15000,2000,16000),box(2000,16000,3000,17000)])
        geographic=mapping(transform(self.inverse,shapely_scale(local,3/100,-300,-300)))
        request["buildings"]=self.snapshot([dict(type="Feature",geometry=geographic,properties=dict(id="multipart",height=6,sources=[]))])
        out,report=composition.compose(self.document(request),request,self.catalog)
        buildings=[b for b in out["buildings"] if b["id"].startswith("regional-")]
        self.assertEqual(len(buildings),1)
        self.assertEqual(len(buildings[0]["parts"]),1)
        self.assertEqual(Polygon(buildings[0]["footprint"]).area+Polygon(buildings[0]["parts"][0]["footprint"]).area,local.area)
        self.assertEqual(report["diagnostics"]["regional"]["counts"]["building_added"],1)

    def test_touching_courtyard_partition_preserves_exact_outline_and_void(self):
        local=Polygon([(0,0),(2000,0),(2000,2000),(0,2000)],
                      [[(0,1000),(1000,500),(1000,1500)]])
        result=composition.building_parts(local)
        self.assertGreater(len(result),1)
        self.assertTrue(all(not p.interiors and p.area>0 for p in result))
        self.assertEqual(sum(p.area for p in result),local.area)
        self.assertEqual(unary_union(result).symmetric_difference(local).area,0)
        self.assertEqual([p.wkb for p in result],[p.wkb for p in composition.building_parts(local)])

    def test_source_receipt_compression_is_lossless_bounded_and_hash_checked(self):
        rows=[dict(source_id=f"way/{i}",evidence=dict(height="source:height"),label="학교") for i in range(1500)]
        packed=dict(objects=deepcopy(rows));regional.pack_rows(packed,"objects")
        self.assertNotIn("objects",packed)
        self.assertEqual(regional.receipt_rows(packed,"objects"),rows)
        second=dict(objects=deepcopy(rows));regional.pack_rows(second,"objects")
        self.assertEqual(packed,second)
        for field,value in (("bytes",33*1024*1024),("bytes",1),("sha256","0"*64),("codec","unknown")):
            bad=deepcopy(packed);bad["objects_blob"][field]=value
            with self.assertRaises(ValueError):regional.receipt_rows(bad,"objects")
        bad=deepcopy(packed);bad["objects"]=[]
        with self.assertRaises(ValueError):regional.receipt_rows(bad,"objects")

    def test_auxiliary_buildings_respect_rounded_junctions_and_bridge_edges(self):
        def request_for(local):
            request=deepcopy(self.request)
            geometry=mapping(transform(self.inverse,shapely_scale(local,3/100,-300,-300)))
            request["buildings"]=self.snapshot([dict(type="Feature",geometry=geometry,properties=dict(id="edge-building",height=6,sources=[]))])
            return request
        request=request_for(box(10185,9775,10235,9825))
        doc=self.document(request);road=doc["roads"][0]
        road["points"]=[[0,0,10000],[10000,0,10000],[10000,0,20000]]
        road["widths_cm"]=[500,500];road["surfaces"]=["asphalt","asphalt"]
        out,report=composition.compose(doc,request,self.catalog)
        self.assertEqual(out["buildings"],doc["buildings"])
        self.assertEqual(report["diagnostics"]["regional"]["counts"]["building_road_conflict"],1)
        request=request_for(box(10000,10260,10050,10265))
        doc=self.document(request);doc["roads"][0]["kind"]="bridge"
        _,report=composition.compose(doc,request,self.catalog)
        self.assertEqual(report["diagnostics"]["regional"]["counts"]["building_road_conflict"],1)
        for point in doc["roads"][0]["points"]:point[1]=400
        out,report=composition.compose(doc,request,self.catalog)
        self.assertEqual(report["diagnostics"]["regional"]["counts"]["building_added"],1)

    def test_auxiliary_envelopes_reserve_generated_furniture_space(self):
        from osm_furniture import Furniture
        request=deepcopy(self.request)
        request["buildings"]=self.snapshot([dict(type="Feature",geometry=mapping(transform(self.inverse,box(0,0,10,10))),properties=dict(id="reserved",sources=[]))])
        result,_=self.annotate([self.feature(1,box(30,0,40,10),_city_building="yes")],request)
        self.assertEqual(len(result["regional_building_blockers"]),1)
        furniture=Furniture([],{},3,dict(driving_side="right",signal_style="horizontal"),[box(0,0,1000,1000)])
        self.assertFalse(furniture.place("test","builtin:bus_shelter",500,500,0,"node/1",steps=0))
        self.assertTrue(furniture.place("test","builtin:bus_shelter",2500,500,0,"node/2",steps=0))

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
