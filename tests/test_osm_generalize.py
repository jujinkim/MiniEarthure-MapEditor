"""Synthetic city layouts only; no user geographic data is published."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
import math
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
import pyproj
from shapely.geometry import shape, box, LineString, mapping, Polygon, MultiPolygon
from shapely.ops import transform
from osm_generalize import Generalizer
from polygon_geometry import Budget, SpatialBudget, group_rings


class City(unittest.TestCase):
    def setup_city(self, origin=(9,55)):
        self.options = dict(mode="wgs84-utm", origin=list(origin), local_origin_m=[1000,1000])
        epsg = (32700 if origin[1] < 0 else 32600) + min(60, int((origin[0]+180)//6)+1)
        projection = pyproj.Transformer.from_crs(4326, epsg, always_xy=True)
        x0,y0 = projection.transform(*origin)
        def inverse(x,y,z=None):
            return projection.transform(x+x0,y+y0,direction="INVERSE")
        self.inverse = inverse
        self.features = []

    def add(self, identity, geometry, **properties):
        p = dict(osm_source_id=f"way/{identity}", **properties)
        self.features.append(dict(type="Feature", properties=p, geometry=json.loads(json.dumps(mapping(transform(self.inverse, geometry))))))

    def worker(self):
        return Generalizer(dict(type="FeatureCollection", features=self.features), self.options)

    def test_dense_buildings_merge_with_complete_sources_in_multiple_cities(self):
        for origin in [(9,55),(127.03,37.27),(18.5,-33.9)]:
            self.setup_city(origin)
            for i in range(20):
                self.add(i+1,box(i*12,10,i*12+10,20))
            original = deepcopy(self.features)
            worker = self.worker()
            candidate, meta = worker.candidate(4)
            self.assertLess(meta["after"]["buildings"],20)
            self.assertEqual(meta["source_ids"],sorted(f"way/{i+1}" for i in range(20)))
            self.assertEqual({s for group in meta["groups"] for s in group["source_ids"]},set(meta["source_ids"]))
            self.assertEqual(self.features,original)
            self.assertTrue(any(group["estimated_height"] for group in meta["groups"]))

    def test_road_corridor_prevents_merging_across_street(self):
        self.setup_city()
        self.add(1,box(10,10,20,20))
        self.add(2,box(24,10,34,20))
        self.add(3,LineString([(22,0),(22,30)]),width_m=2,_city_refs=[1,2])
        worker=self.worker()
        output,meta=worker.candidate(16)
        self.assertEqual(meta["after"]["buildings"],2)
        originals=[g for f,g in worker.features if g.geom_type=="Polygon"]
        for f in output["features"]:
            if f["geometry"]["type"]!="Polygon": continue
            projected=transform(worker.project,shape(f["geometry"]))
            self.assertLess(projected.intersection(box(21.1,0,22.9,30)).area,0.001)

    def test_names_tall_buildings_holes_and_heights_are_protected(self):
        self.setup_city()
        self.add(1,box(10,10,20,20),_city_name="작은도서관")
        self.add(2,box(22,10,32,20))
        self.add(3,box(34,10,44,20),height_m=80)
        courtyard=Polygon([(60,0),(90,0),(90,30),(60,30),(60,0)],holes=[[(65,5),(85,5),(85,25),(65,25),(65,5)]])
        self.add(4,courtyard)
        self.add(5,box(92,0,100,30))
        worker=self.worker()
        value,meta=worker.candidate(16)
        mappings={s:group for group in meta["groups"] for s in group["source_ids"]}
        self.assertEqual(mappings["way/1"]["source_ids"],["way/1"])
        self.assertEqual(mappings["way/3"]["source_ids"],["way/3"])
        for feature in value["features"]:
            g=transform(worker.project,shape(feature["geometry"]))
            self.assertLess(g.intersection(box(65.1,5.1,84.9,24.9)).area,0.001)

    def test_compatible_chains_join_without_erasing_junctions_or_semantic_breaks(self):
        self.setup_city()
        self.add(1,LineString([(0,0),(10,0)]),_city_refs=[1,2])
        self.add(2,LineString([(10,0),(20,0)]),_city_refs=[2,3])
        self.add(3,LineString([(20,0),(30,0)]),_city_refs=[3,4])
        self.add(4,LineString([(20,0),(20,10)]),_city_refs=[3,5])
        self.add(5,LineString([(30,0),(40,0)]),_city_refs=[4,6],width_m=4)
        value,meta=self.worker().candidate(8)
        self.assertEqual(meta["after"]["roads"],4)
        groups=[set(g["source_ids"]) for g in meta["groups"]]
        self.assertIn({"way/1","way/2"},groups)
        self.assertIn({"way/3"},groups)
        self.assertIn({"way/5"},groups)

    def test_equal_positions_without_source_identity_never_join(self):
        self.setup_city()
        self.add(1,LineString([(0,0),(10,0)]),_city_refs=[1,2])
        self.add(2,LineString([(10,0),(20,0)]),_city_refs=[3,4])
        self.assertEqual(self.worker().candidate(16)[1]["after"]["roads"],2)

    def test_fully_covered_source_requires_explicit_review_and_excludes_all_its_parts(self):
        from osm_review import Review
        self.setup_city()
        self.add(1,LineString([(0,0),(50,0)]),width_m=8,_city_refs=[1,2])
        self.add(2,box(10,1,11,2),_city_name="작은 시설")
        self.add(2,box(10,20,20,30),_city_name="작은 시설")
        self.add(3,box(30,20,40,30))
        original = deepcopy(self.features)
        with self.assertRaisesRegex(ValueError,"Explicit source exclusion"):
            self.worker().candidate(4)
        review = Review(True)
        worker = Generalizer(dict(type="FeatureCollection",features=self.features),self.options,review)
        for gap in [0,4]:
            value,meta = worker.candidate(gap)
            self.assertEqual(meta["source_ids"],["way/1","way/3"])
            self.assertEqual(meta["after"]["buildings"],1)
            self.assertNotIn("way/2",meta["trimmed_building_sources"])
        self.assertEqual(list(review.excluded),["way/2"])
        self.assertIn("Road widths may be estimates",review.excluded["way/2"]["reason"])
        self.assertEqual(self.features,original)

    def test_matching_vegetation_unions_but_keeps_other_landuse(self):
        self.setup_city()
        self.add(1,box(0,0,20,20),landuse="forest")
        self.add(2,box(10,0,30,20),landuse="forest")
        self.add(3,box(25,0,40,20),landuse="orchard")
        value,meta=self.worker().candidate(4)
        self.assertEqual(meta["after"]["areas"],2)
        self.assertEqual({f["properties"]["landuse"] for f in value["features"]},{"forest","orchard"})

    def test_invalid_source_is_not_repaired_and_output_is_deterministic(self):
        self.setup_city()
        self.add(1,box(1,1,11,11))
        self.add(2,box(13,1,23,11))
        first=self.worker().candidate(8)
        self.features.reverse()
        self.assertEqual(first,self.worker().candidate(8))
        self.add(3,Polygon([(0,0),(20,20),(0,20),(20,0),(0,0)]))
        with self.assertRaisesRegex(ValueError,"valid original"):
            self.worker()

    def test_more_than_twenty_thousand_original_buildings_fit_after_aggregation(self):
        self.setup_city()
        for i in range(20100):
            x,y=(i%150)*12,(i//150)*12
            self.add(i+1,box(x+1,y+1,x+11,y+11))
        meta=self.worker().candidate(4)[1]
        self.assertEqual(meta["before"]["features"],20100)
        self.assertLess(meta["after"]["features"],2000)
        self.assertLess(meta["after"]["positions"],200000)
        self.assertEqual(len(meta["source_ids"]),20100)

    def test_spatial_topology_keeps_strict_rules_without_quadratic_edge_work(self):
        ring=[[100*math.cos(i*2*math.pi/3000),100*math.sin(i*2*math.pi/3000)] for i in range(3000)]
        ring.append(ring[0])
        self.assertEqual(group_rings([ring],[],SpatialBudget()),[[ring]])
        with self.assertRaisesRegex(ValueError,"budget"):
            group_rings([ring],[],Budget())
        outer=[[0,0],[10,0],[10,10],[0,10],[0,0]]
        inner=[[2,2],[8,2],[8,8],[2,8],[2,2]]
        island=[[3,3],[4,3],[4,4],[3,4],[3,3]]
        self.assertEqual(group_rings([outer,island],[inner],SpatialBudget()),group_rings([outer,island],[inner],Budget()))
        for rings,holes in [([outer,inner],[]),([outer],[[[0,2],[2,2],[2,4],[0,4],[0,2]]]),([[[0,0],[5,5],[0,5],[5,0],[0,0]]],[])]:
            with self.assertRaises(ValueError): group_rings(rings,holes,SpatialBudget())

    def test_ground_loops_merge_only_between_original_junctions(self):
        from osm_loops_fixture import xml
        from osm_extract import parse
        self.setup_city()
        collection,_=parse(xml().encode(),"osm")
        worker=Generalizer(collection,self.options)
        output,meta=worker.candidate(0)
        self.assertLess(meta["after"]["roads"],meta["before"]["roads"])
        def edges(value):
            return sorted((p["osm_way_id"],str(a),str(b)) for f in value["features"] if "osm_node_refs" in (p:=f["properties"]) for a,b in zip(p["osm_node_refs"],p["osm_node_refs"][1:]))
        self.assertEqual(edges(collection),edges(output))
        for f in output["features"]:
            p=f["properties"]
            if "osm_node_refs" in p: self.assertNotEqual(p["osm_node_refs"][0],p["osm_node_refs"][-1])

    def test_park_area_stops_building_gap_filling(self):
        self.setup_city()
        self.add(1,box(10,10,20,20))
        self.add(2,box(30,10,40,20))
        self.add(3,box(21,0,29,30),osm_region=True,landuse="park",protected=False)
        self.assertEqual(self.worker().candidate(64)[1]["after"]["buildings"],2)

    def test_ground_bends_simplify_with_exact_source_positions_and_structure_protection(self):
        self.setup_city()
        line=LineString([(0,0),(10,0.1),(20,0),(30,0.1),(40,0)])
        self.add(1,line,osm_way_id=1,osm_node_refs=[1,2,3,4,5],osm_loop_range=[0,4],road_kind="ground")
        self.add(2,LineString([(0,20),(10,20.1),(20,20)]),osm_way_id=2,osm_node_refs=[6,7,8],osm_loop_range=[0,2],road_kind="bridge",elevations_m=[4,4,4])
        original=deepcopy(self.features)
        output,meta=self.worker().candidate(4)
        ground=next(f for f in output["features"] if f["properties"]["osm_way_id"]==1)
        bridge=next(f for f in output["features"] if f["properties"]["osm_way_id"]==2)
        self.assertEqual(ground["properties"]["_city_loop_positions"],[0,4])
        self.assertEqual(ground["properties"]["osm_node_refs"],[1,5])
        self.assertEqual(len(ground["geometry"]["coordinates"]),2)
        self.assertNotIn("_city_loop_positions",bridge["properties"])
        self.assertEqual(len(bridge["geometry"]["coordinates"]),3)
        self.assertEqual(self.features,original)

    def test_coincident_distinct_endpoints_split_without_welding_or_losing_edges(self):
        self.setup_city()
        self.add(1,LineString([(0,0),(10,0),(10,10),(0,0)]),_city_refs=[1,2,3,4])
        output,meta=self.worker().candidate(0)
        self.assertEqual(meta["after"]["roads"],2)
        self.assertEqual(len(meta["source_ids"]),1)
        self.assertTrue(all(shape(f["geometry"]).is_simple for f in output["features"]))
        self.assertEqual(sum(len(f["geometry"]["coordinates"])-1 for f in output["features"]),3)

    def test_physical_material_and_minimum_width_approximations_are_disclosed(self):
        self.setup_city()
        self.add(1,LineString([(0,0),(10,0)]),surface="paving_stones",width_m=1,_city_refs=[1,2])
        self.add(2,LineString([(10,0),(20,0)]),surface="unmapped_material",_city_refs=[2,3])
        output,meta=self.worker().candidate(0)
        self.assertEqual(meta["widened_roads"],1)
        self.assertEqual(meta["surface_mappings"],[dict(source="paving_stones",target="concrete",features=1),dict(source="unmapped_material",target="asphalt",features=1)])
        first=next(f for f in output["features"] if f["properties"]["osm_source_id"]=="way/1")
        self.assertEqual(first["properties"]["width_m"],1.6)

    def test_overlap_partition_preserves_names_sources_and_tall_envelope(self):
        self.setup_city()
        self.add(1,box(0,0,20,20),height_m=60,_city_name="중앙동")
        self.add(2,box(2,2,10,10),height_m=12,_city_name="작은도서관")
        self.add(3,box(15,0,30,20),height_m=20,_city_name="상가")
        worker=self.worker();output,meta=worker.candidate(0)
        polygons=[transform(worker.project,shape(f["geometry"])) for f in output["features"]]
        self.assertEqual(len(polygons),2)
        self.assertFalse(polygons[0].intersects(polygons[1]))
        self.assertEqual({s for group in meta["groups"] for s in group["source_ids"]},set(meta["source_ids"]))
        self.assertIn("작은도서관",{n for group in meta["groups"] for n in group["names"]})
        self.assertEqual(meta["overlap_adjusted_sources"],["way/2","way/3"])

    def test_road_clearance_cut_is_disclosed_and_complex_named_building_partitions(self):
        self.setup_city()
        self.add(1,box(0,0,20,20),_city_name="별관")
        self.add(2,LineString([(-10,1),(30,1)]),width_m=4,_city_refs=[1,2])
        worker=self.worker();out,meta=worker.candidate(4)
        polygon=next(shape(f["geometry"]) for f in out["features"] if f["geometry"]["type"]=="Polygon")
        self.assertGreater(transform(worker.project,polygon).bounds[1],3.5)
        self.assertEqual(meta["trimmed_building_sources"],["way/1"])
        self.setup_city()
        ring=[(100*math.cos(i*2*math.pi/700),100*math.sin(i*2*math.pi/700)) for i in range(700)]
        self.add(1,Polygon(ring),height_m=80,_city_name="전시장")
        out,meta=self.worker().candidate(0)
        self.assertGreater(meta["after"]["buildings"],1)
        self.assertTrue(all(len(f["geometry"]["coordinates"][0])<=512 for f in out["features"]))


    def test_pedestrian_ways_become_disjoint_hole_free_ground_paint(self):
        from geojson import convert
        self.setup_city()
        walk = lambda kind: dict(_city_road_tags=dict(highway=kind))
        self.add(1,LineString([(0,0),(300,0)]),_city_refs=[1,2],**walk("residential"))
        self.add(2,LineString([(10,10),(290,10)]),_city_refs=[3,4],**walk("footway"))
        self.add(3,LineString([(50,10),(50,60)]),_city_refs=[3,5],surface="dirt",**walk("footway"))
        self.add(4,LineString([(100,30),(140,30),(140,70),(100,70),(100,30)]),_city_refs=[6,7,8,9,6],**walk("path"))
        loop=lambda identity,line,refs,**extra:self.add(identity,line,osm_way_id=identity,osm_node_refs=refs,osm_loop_range=[0,1],**extra,**walk("footway"))
        loop(5,LineString([(200,30),(230,30)]),[20,21],road_kind="ground")
        loop(6,LineString([(200,80),(230,80)]),[30,31],road_kind="ground")
        self.add(7,LineString([(230,80),(260,80)]),osm_way_id=7,osm_node_refs=[31,32],osm_loop_range=[0,1],road_kind="bridge",elevations_m=[0.0,0.0],**walk("footway"))
        worker=self.worker();out,meta=worker.candidate(0)
        kept={f["properties"]["osm_source_id"] for f in out["features"] if f["geometry"]["type"]=="LineString"}
        self.assertEqual(kept,{"way/1","way/6","way/7"},"loops joined to a pedestrian structure stay roads")
        self.assertGreater(meta["painted_pedestrian_ways"],0)
        self.assertEqual({s for group in meta["groups"] for s in group["source_ids"]},set(meta["source_ids"]))
        lattice=lambda x,y,z=None:((x+1000)*12.5,(y+1000)*12.5)
        paint=[(f["properties"]["_city_paint"],transform(lattice,transform(worker.project,shape(f["geometry"])))) for f in out["features"] if "_city_paint" in f["properties"]]
        self.assertGreater(len(paint),2,"the footway spanning a native cell boundary is cut there")
        for i,(surface,piece) in enumerate(paint):
            self.assertEqual(len(piece.interiors),0)
            self.assertLessEqual(len(piece.exterior.coords),257)
            self.assertTrue(all(abs(v-round(v))<1e-6 for point in piece.exterior.coords for v in point),"whole 1:8 map centimetres")
            self.assertTrue(all(piece.intersection(other).area<1e-6 for _,other in paint[i+1:]))
        covered=lambda x,y:[surface for surface,piece in paint if piece.buffer(0.01).contains(shapely.Point(lattice(x,y)))]
        self.assertEqual(covered(50,40),["dirt"])
        self.assertEqual(covered(200,10),["concrete"])
        self.assertEqual(covered(100,50),["concrete"],"the loop path is painted")
        self.assertEqual(covered(120,50),[],"the loop interior stays unpainted terrain")
        self.assertEqual(covered(200,0),[],"vehicle roads stay roads")
        self.assertEqual(covered(215,30),["concrete"],"a free ground loop is painted")
        layer=convert(out,"synthetic","ODbL-1.0",coordinates=self.options,osm_graph=True,city=True)
        areas=[p["after"] for p in layer.patches if p["field"]=="surface_areas"]
        self.assertEqual(len(areas),len(paint))
        self.assertEqual(len([p for p in layer.patches if p["field"]=="roads"]),3)
        self.assertTrue(all(v%8==0 for area in areas for point in area["polygon"] for v in point),"1:8 adoption keeps exact vertices")


    def test_gaps_sharing_road_space_reuse_it_exactly(self):
        from osm_review import Review
        self.setup_city()
        walk = lambda kind: dict(_city_road_tags=dict(highway=kind))
        self.add(1,LineString([(0,0),(150,3),(300,0)]),width_m=8,_city_refs=[1,2,3],**walk("residential"))
        self.add(2,LineString([(10,40),(290,40)]),_city_refs=[4,5],**walk("footway"))
        self.add(3,box(20,2,22,4))  # Inside the road: excluded by review.
        self.add(4,box(40,8,60,30),_city_name="도서관")
        self.add(5,box(240,4,260,24))  # Trimmed by the road.
        for i in range(12):
            self.add(10+i,box(70+i*14,8,80+i*14,30),height_m=9)
        self.add(30,box(0,50,80,90),landuse="forest")
        workers = lambda: Generalizer(dict(type="FeatureCollection",features=self.features),self.options,Review(True))
        original = deepcopy(self.features)
        reused = workers()
        runs = {gap: reused.candidate(gap)+(reused.remaining,) for gap in (16,32,64)}
        for gap in (32,64):
            fresh = workers()
            self.assertEqual(runs[gap],fresh.candidate(gap)+(fresh.remaining,),f"gap {gap} equals a fresh build")
        paint = lambda gap:[f["properties"]["_city_sources"] for f in runs[gap][0]["features"] if "_city_paint" in f["properties"]]
        self.assertTrue(all(a is not b for a,b in zip(paint(32),paint(64))),"each candidate owns its paint source lists")
        self.assertGreater(runs[64][1]["painted_pedestrian_ways"],0)
        self.assertIn("way/5",runs[64][1]["trimmed_building_sources"])
        self.assertEqual(runs[64][1]["source_ids"],sorted(f"way/{i}" for i in [1,2,4,5,30,*range(10,22)]))
        self.assertEqual(self.features,original)

    def test_candidates_start_from_the_largest_gap_and_drop_exclusions_of_a_replaced_road_space(self):
        from osm_generalize import candidates
        from osm_review import Review
        self.setup_city()
        self.add(1,LineString([(0,0),(150,3),(300,0)]),width_m=6,_city_refs=[1,2,3],_city_road_tags=dict(highway="residential"))
        self.add(2,box(146,-3.6,154,-1.2))  # Inside the straightened (4 m tolerance) road only.
        for i in range(12):
            self.add(10+i,box(20+i*14,40,30+i*14,60),height_m=9)
        collection = lambda: dict(type="FeatureCollection",features=deepcopy(self.features))
        review = Review(True)
        review.reject("way/99","excluded while streaming")
        gaps, excluded = [], []
        for candidate, meta in candidates(collection(),self.options,review):
            gaps.append(meta["gap_m"])
            excluded.append(list(review.excluded))
        self.assertEqual(gaps,[64,32,16,8,4,2,0])
        self.assertEqual(excluded[0],["way/99","way/2"],"the straightened road space covers the building")
        self.assertEqual(excluded[-1],["way/99"],"a bent road space keeps it")
        fresh = Review(True)
        fresh.reject("way/99","excluded while streaming")
        worker = Generalizer(collection(),self.options,fresh)
        self.assertEqual(worker.candidate(4)[1]["source_ids"],meta["source_ids"])
        self.assertEqual(fresh.metadata(),review.metadata())
        self.assertEqual(review.bytes,fresh.bytes)
        # Without exclusion review the straightened road space is a failed candidate,
        # not a failed import; the next tolerance keeps the building.
        built = list(candidates(collection(),self.options,Review(False)))
        self.assertEqual([meta["gap_m"] for candidate,meta in built],[64,32,16,8,4,2,0])
        self.assertTrue(all(candidate is None and "way/2" in meta["failure"] for candidate,meta in built[:3]))
        self.assertIn("way/2",built[3][1]["source_ids"])

    def test_area_invalid_after_projection_retains_the_group(self):
        # Valid in lon/lat; the spike vertex crosses the projected chord of the
        # long bottom edge, so overlays with it fail inside the building group.
        self.setup_city()
        water = Polygon([(8.9917,55),(9.0083,55),(9.0083,55.002),(9.0002,55.002),(9.0,55.0000001),(8.9998,55.002),(8.9917,55.002)])
        self.features.append(dict(type="Feature",properties=dict(osm_source_id="way/1",osm_region=True,landuse="water"),geometry=mapping(water)))
        worker = self.worker()
        vertex = transform(worker.project,shapely.Point(9.0,55.0000001))
        self.assertFalse(transform(worker.project,water).is_valid)
        self.add(2,box(vertex.x-5,-12,vertex.x+5,-3))
        self.assertEqual(self.worker().candidate(4)[1]["unmerged_numeric_groups"],2)

    def test_parts_of_one_building_never_touch(self):
        # A trimmed building can split into parts that meet at one corner.
        self.setup_city()
        self.add(1,box(0,0,1,1))
        worker=self.worker()
        pinched=MultiPolygon([box(0,0,10,10),box(10,10,20,20)])
        self.assertTrue(pinched.is_valid)
        polygons=worker.separated_parts(pinched)
        self.assertEqual(len(polygons),2)
        self.assertFalse(polygons[0].intersects(polygons[1]),"a corner contact is separated")
        self.assertGreater(polygons[1].area,99)

    def test_gap_filling_never_regrows_into_a_junction_surface(self):
        self.setup_city()
        self.add(1,LineString([(70,10),(100,10)]),width_m=8,_city_refs=[1,2])
        self.add(2,LineString([(100,10),(130,10)]),width_m=8,_city_refs=[2,3])
        self.add(3,LineString([(100,10),(100,-20)]),width_m=8,_city_refs=[2,4])
        self.add(4,box(90,15,99,25))
        self.add(5,box(101,15,110,25))
        worker=self.worker();out,meta=worker.candidate(16)
        buildings=[transform(worker.project,shape(f["geometry"])) for f in out["features"] if f["geometry"]["type"]=="Polygon"]
        self.assertEqual(meta["after"]["buildings"],1,"the gap above the junction is still filled")
        self.assertGreater(min(b.distance(shapely.Point(100,10)) for b in buildings),6.2,"buildings stay outside the junction disk")

    def test_erased_source_returns_trimmed_on_the_map_lattice(self):
        self.setup_city()
        self.add(1,box(10.03,10.03,20.01,20.01))
        self.add(2,LineString([(0,9),(40,9)]),width_m=2,_city_refs=[1,2])
        worker=self.worker()
        worker.polygon_group=lambda group,gap,buildings:[]  # A merge that erased every member.
        out,meta=worker.candidate(0)
        building=next(transform(worker.project,shape(f["geometry"])) for f in out["features"] if f["geometry"]["type"]=="Polygon")
        self.assertEqual(meta["unmerged_numeric_groups"],1)
        self.assertGreater(building.bounds[1],9+1+0.8-0.05,"road clearance trim is kept")
        self.assertTrue(all(abs((v+1000)*12.5-round((v+1000)*12.5))<1e-6 for point in building.exterior.coords for v in point))

if __name__=="__main__": unittest.main()
