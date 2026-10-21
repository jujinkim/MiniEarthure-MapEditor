"""Synthetic city layouts only; no user geographic data is published."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import math
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
import pyproj
from shapely.geometry import shape, box, LineString, mapping, Polygon, MultiPolygon
from shapely.ops import transform, unary_union
from collections import Counter
from osm_generalize import Generalizer
from polygon_geometry import Budget, SpatialBudget, group_rings


class City(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

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

    def worker(self, scale=8):
        return Generalizer(dict(type="FeatureCollection", features=self.features), self.options, scale=scale)

    def test_scale_derives_the_lattice_and_clearances_in_whole_map_centimetres(self):
        from osm_generalize import candidates
        self.setup_city()
        self.add(1,box(10,10,20,20))
        self.add(2,LineString([(0,0),(40,0)]),width_m=4,_city_refs=[1,2])
        for scale in (8, 3, 1):
            with self.subTest(scale=scale):
                out,meta=self.worker(scale).candidate(0)
                self.assertEqual(meta["scale_denominator"],scale)
                expected=dict(grid_m=1,minimum_road_width_m=20,road_clearance_m=10,building_clearance_m=2,polygon_partition_gap_m=4)
                for key,cm in expected.items():
                    self.assertEqual(meta[key],cm*scale/100,key)
                    self.assertAlmostEqual(meta[key]/meta["grid_m"],cm,places=9,msg="a multiple of the lattice")
                self.assertEqual(meta["vegetation_spacing_m"],32,"vegetation spacing stays in source metres")
        self.assertEqual(next(iter(candidates(dict(type="FeatureCollection",features=self.features),self.options,scale=3)))[1]["scale_denominator"],3)
        for bad in (0, 9, 2.0, True, "3"):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError,"integer denominator"):
                self.worker(bad)
        # 1:8 keeps the original literal lattice and clearances exactly.
        meta=self.worker(8).candidate(0)[1]
        self.assertEqual((meta["grid_m"],meta["minimum_road_width_m"],meta["road_clearance_m"],meta["building_clearance_m"],meta["polygon_partition_gap_m"]),(0.08,1.6,0.8,0.16,0.32))

    def solids(self, worker, value):
        """Projected solids of every building record (footprint first, then parts)."""
        out = []
        for f in value["features"]:
            if f["geometry"]["type"] in ("Polygon", "MultiPolygon") and not f["properties"].get("_city_paint") and not f["properties"].get("osm_region"):
                g = transform(worker.project, shape(f["geometry"]))
                out.append((f, list(g.geoms) if g.geom_type == "MultiPolygon" else [g]))
        return out

    def test_dense_buildings_group_as_separate_parts_with_complete_sources_in_multiple_cities(self):
        for origin in [(9,55),(127.03,37.27),(18.5,-33.9)]:
            self.setup_city(origin)
            for i in range(20):
                self.add(i+1,box(i*12,10,i*12+10,20),height_m=6+i)
            original = deepcopy(self.features)
            worker = self.worker()
            candidate, meta = worker.candidate(64)
            self.assertEqual(meta["after"]["buildings"],1,"one record groups the tile's buildings")
            self.assertEqual(meta["source_ids"],sorted(f"way/{i+1}" for i in range(20)))
            self.assertEqual({s for group in meta["groups"] for s in group["source_ids"]},set(meta["source_ids"]))
            self.assertEqual(self.features,original)
            self.assertFalse(any(group["estimated_height"] for group in meta["groups"]),"each part keeps its source height")
            [(feature, solids)] = self.solids(worker, candidate)
            self.assertEqual(len(solids),20,"every footprint stays its own solid: never fused across the 2 m gaps")
            for k, solid in enumerate(sorted(solids, key=lambda g: g.bounds[0])):
                self.assertAlmostEqual(solid.area,100,delta=0.5)
                self.assertEqual(len(solid.exterior.coords),5,"a rectangle stays a rectangle")
            self.assertEqual(sorted(p["height_m"] for p in feature["properties"]["_city_parts"]),[6+i for i in range(20)])
            self.assertEqual(meta["building_records"],dict(grouped_records=1,records=1,solids=20))

    def test_road_corridor_prevents_merging_across_street(self):
        self.setup_city()
        self.add(1,box(10,10,20,20))
        self.add(2,box(24,10,34,20))
        self.add(3,LineString([(22,0),(22,30)]),width_m=2,_city_refs=[1,2])
        worker=self.worker()
        output,meta=worker.candidate(16)
        [(feature, solids)]=self.solids(worker,output)
        self.assertEqual(len(solids),2,"one record, two separate solids")
        for projected in solids:
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
        # A surface change still breaks a chain; width changes no longer do.
        self.add(5,LineString([(30,0),(40,0)]),_city_refs=[4,6],surface="concrete")
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
        import import_layer, polygon_geometry
        self.addCleanup(import_layer.reset_limits)
        import_layer.reset_limits()
        # Quadratic work above the former budget warns; the raised ceiling refuses.
        self.assertEqual(group_rings([ring],[],Budget()),[[ring]])
        self.assertIn("topology_checks",{e["code"] for e in import_layer.limit_entries()})
        with patch.object(polygon_geometry,"TOPOLOGY_CEILING",polygon_geometry.MAX_TOPOLOGY_CHECKS),self.assertRaisesRegex(ValueError,"ceiling"):
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

    def test_buildings_beside_a_park_stay_separate_solids(self):
        self.setup_city()
        self.add(1,box(10,10,20,20))
        self.add(2,box(30,10,40,20))
        self.add(3,box(21,0,29,30),osm_region=True,landuse="park",protected=False)
        worker=self.worker()
        out,meta=worker.candidate(64)
        [(feature, solids)]=self.solids(worker,out)
        self.assertEqual(len(solids),2)
        self.assertTrue(all(g.intersection(box(21,0,29,30)).area<0.001 for g in solids))

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
        for scale, width in ((8, 1), (3, 0.5)):
            with self.subTest(scale=scale):
                self.setup_city()
                self.add(1,LineString([(0,0),(10,0)]),surface="paving_stones",width_m=width,_city_refs=[1,2])
                self.add(2,LineString([(10,0),(20,0)]),surface="unmapped_material",_city_refs=[2,3])
                output,meta=self.worker(scale).candidate(0)
                self.assertEqual(meta["widened_roads"],1)
                self.assertEqual(meta["surface_mappings"],[dict(source="paving_stones",target="concrete",features=1),dict(source="unmapped_material",target="asphalt",features=1)])
                first=next(f for f in output["features"] if f["properties"]["osm_source_id"]=="way/1")
                self.assertEqual(first["properties"]["width_m"],20*scale/100,"20 map cm")

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
        worker=self.worker()
        out,meta=worker.candidate(0)
        [(feature, solids)]=self.solids(worker,out)
        self.assertEqual(meta["after"]["buildings"],1,"a protected source's native pieces stay one record")
        self.assertGreater(len(solids),1)
        self.assertTrue(all(len(g.exterior.coords)<=512 for g in solids))


    def test_pedestrian_ways_become_disjoint_hole_free_ground_paint(self):
        for scale in (8, 3):
            with self.subTest(scale=scale):
                self.pedestrian_paint(scale)

    def pedestrian_paint(self, scale):
        from geojson import convert
        import import_layer
        import_layer.reset_limits()
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
        worker=self.worker(scale);out,meta=worker.candidate(0)
        kept={f["properties"]["osm_source_id"] for f in out["features"] if f["geometry"]["type"]=="LineString"}
        self.assertEqual(kept,{"way/1","way/6","way/7"},"loops joined to a pedestrian structure stay roads")
        self.assertGreater(meta["painted_pedestrian_ways"],0)
        self.assertEqual({s for group in meta["groups"] for s in group["source_ids"]},set(meta["source_ids"]))
        lx,ly=worker.local  # The local origin, less its remainder off the 1:D lattice.
        lattice=lambda x,y,z=None:((x+lx)*100/scale,(y+ly)*100/scale)
        paint=[(f["properties"]["_city_paint"],transform(lattice,transform(worker.project,shape(f["geometry"])))) for f in out["features"] if "_city_paint" in f["properties"]]
        self.assertGreater(len(paint),2,"the footway spanning a native cell boundary is cut there")
        for i,(surface,piece) in enumerate(paint):
            self.assertEqual(len(piece.interiors),0)
            self.assertLessEqual(len(piece.exterior.coords),257)
            self.assertTrue(all(abs(v-round(v))<1e-6 for point in piece.exterior.coords for v in point),"whole 1:D map centimetres")
            self.assertTrue(all(piece.intersection(other).area<1e-6 for _,other in paint[i+1:]))
        covered=lambda x,y:[surface for surface,piece in paint if piece.buffer(0.01).contains(shapely.Point(lattice(x,y)))]
        # A piece that holds only the dirt footway: above the native cell line
        # (y = 24 source m at 1:8, 56 at 1:3) it no longer meets the long footway.
        self.assertEqual(covered(50,40 if scale==8 else 58),["dirt"])
        self.assertEqual(covered(200,10),["concrete"])
        self.assertEqual(covered(100,50),["concrete"],"the loop path is painted")
        self.assertEqual(covered(120,50),[],"the loop interior stays unpainted terrain")
        self.assertEqual(covered(200,0),[],"vehicle roads stay roads")
        self.assertEqual(covered(215,30),["concrete"],"a free ground loop is painted")
        layer=convert(out,"synthetic","ODbL-1.0",coordinates=self.options,osm_graph=True,city=True)
        areas=[p["after"] for p in layer.patches if p["field"]=="surface_areas"]
        self.assertEqual(len(areas),len(paint))
        self.assertEqual(len([p for p in layer.patches if p["field"]=="roads"]),3)
        self.assertTrue(all(v%scale==0 for area in areas for point in area["polygon"] for v in point),"1:D adoption keeps exact vertices")


    def test_city_steps_are_painted_at_walking_width(self):
        self.setup_city()
        self.add(1,LineString([(0,0),(100,0)]),_city_refs=[1,2],_city_road_tags=dict(highway="residential"))
        self.add(2,LineString([(50,20),(50,80)]),_city_refs=[3,4],_city_road_tags=dict(highway="steps"))
        worker=self.worker();out,meta=worker.candidate(0)
        self.assertEqual({f["properties"]["osm_source_id"] for f in out["features"] if f["geometry"]["type"]=="LineString"},{"way/1"})
        steps=[f for f in out["features"] if f["properties"].get("_city_sources")==["way/2"]]
        self.assertEqual(meta["painted_pedestrian_ways"],1)
        self.assertEqual(sum(1 for f in out["features"] if "_city_paint" in f["properties"]),len(steps))
        self.assertTrue(steps)
        area=sum(transform(worker.project,shape(f["geometry"])).area for f in steps)
        self.assertAlmostEqual(area/(60*1.6),1.0,delta=0.08,msg="footway width, not the 8 m default")

    def test_lifted_layer_buildings_keep_clear_of_source_height_structures(self):
        from osm_review import Review
        for kind in ("bridge", "tunnel"):
            with self.subTest(kind=kind):
                self.setup_city()
                structure = dict(road_kind=kind, elevations_m=[6.0 if kind == "bridge" else -6.0]*2, osm_way_id=1, osm_node_refs=[1, 2], width_m=6, _city_road_tags=dict(highway="residential"))
                self.add(1, LineString([(0, 0), (100, 0)]), **structure)
                self.add(2, box(20, 4.5, 40, 20), height_m=12, _city_layer_building=True)  # Within 3 + 1.6 + 0.8 m.
                self.add(3, box(60, 4.5, 80, 20), height_m=12)
                self.add(4, box(45, -3, 55, 3), height_m=12, _city_layer_building=True)
                review = Review(True)
                out, meta = Generalizer(dict(type="FeatureCollection", features=self.features), self.options, review).candidate(0)
                self.assertEqual(meta["layered_buildings"], 1, "the excluded lifted building is not counted as standing")
                self.assertIn("way/2", meta["trimmed_building_sources"], "cut back to the structure's safety corridor")
                self.assertNotIn("way/3", meta["trimmed_building_sources"], "ordinary buildings keep the explicit-structure rule")
                self.assertEqual([r["source_id"] for r in review.excluded.values()], ["way/4"])
                self.assertIn("positive layer", review.excluded["way/4"]["reason"])

    def test_simplified_lifted_buildings_stay_out_of_a_bent_structure_corridor(self):
        self.setup_city()
        self.add(1, LineString([(0, 0), (50, 0), (100, -8)]), road_kind="bridge", elevations_m=[6.0]*3, osm_way_id=1, osm_node_refs=[1, 2, 3], width_m=6,
                 _city_road_tags=dict(highway="residential"))
        self.add(2, Polygon([(30, 1), (70, 1), (70, 30), (30, 30)]), height_m=12, _city_layer_building=True)
        worker = self.worker(); out, meta = worker.candidate(64)
        bridge = LineString([(0, 0), (50, 0), (100, -8)])
        building = [transform(worker.project, shape(f["geometry"])) for f in out["features"] if f["properties"].get("osm_source_id") == "way/2" or "way/2" in f["properties"].get("_city_sources", [])]
        self.assertTrue(building)
        corridor = bridge.buffer(3 + 1.6, cap_style="flat")
        self.assertTrue(all(b.intersection(corridor).area < 1e-6 for b in building), "growth never re-enters the safety strip")

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

    def test_cached_stages_replay_their_limit_warnings_for_every_gap_sharing_the_tolerance(self):
        import import_layer
        from osm_generalize import candidates
        from osm_review import Review
        self.setup_city()
        walk = lambda kind: dict(_city_road_tags=dict(highway=kind))
        self.add(1,LineString([(0,0),(150,3),(300,0)]),width_m=8,_city_refs=[1,2,3],**walk("residential"))
        self.add(2,LineString([(10,40),(290,40)]),_city_refs=[4,5],**walk("footway"))
        for i in range(12):
            self.add(10+i,box(70+i*14,8,80+i*14,30),height_m=9)
        stages = dict(road_space="test_road_stage", prepare="test_prepare_stage", paint="test_paint_stage")
        def injected(name, code):
            original = getattr(Generalizer, name)
            def run(worker, *args):
                import_layer.soft_limit(code, 2, 1, "Injected stage limit")
                return original(worker, *args)
            return patch.object(Generalizer, name, run)
        seen = {}
        with injected("road_space", stages["road_space"]), injected("prepare", stages["prepare"]), injected("paint", stages["paint"]):
            for candidate, meta in candidates(dict(type="FeatureCollection",features=deepcopy(self.features)),self.options,Review(True)):
                self.assertIsNotNone(candidate, meta)
                seen[meta["gap_m"]] = {e["code"] for e in import_layer.limit_entries()}
        shared = [gap for gap in seen if min(4.0, gap/4) == 4.0]
        self.assertEqual(sorted(shared),[16,64],"16 and 64 m gaps reuse the cached stages; 32 m repeats 64 m and is not built")
        for gap, codes in seen.items():
            self.assertTrue(set(stages.values()) <= codes, f"gap {gap}: {codes}")

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
        self.assertEqual(gaps,[64,16,8,4,2,0])
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
        self.assertEqual([meta["gap_m"] for candidate,meta in built],[64,16,8,4,2,0])
        self.assertTrue(all(candidate is None and "way/2" in meta["failure"] for candidate,meta in built[:2]))
        self.assertIn("way/2",built[2][1]["source_ids"])

    def test_area_invalid_after_projection_retains_the_group(self):
        # Valid in lon/lat; the spike vertex crosses the projected chord of the
        # long bottom edge, so overlays with it fail inside the building group.
        self.setup_city()
        water = Polygon([(8.9917,55),(9.0083,55),(9.0083,55.002),(9.0002,55.002),(9.0,55.0000001),(8.9998,55.002),(8.9917,55.002)])
        self.features.append(dict(type="Feature",properties=dict(osm_source_id="way/1",osm_region=True,landuse="water"),geometry=mapping(water)))
        worker = self.worker()
        vertex = transform(worker.project,shapely.Point(9.0,55.0000001))
        self.assertFalse(transform(worker.project,water).is_valid)
        self.add(2,box(vertex.x-5,-12,vertex.x+5,-0.6))  # Within the 1 m building tolerance + clearance.
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
        [(feature, buildings)]=self.solids(worker,out)
        self.assertEqual(len(buildings),2,"the gap above the junction is never filled")
        self.assertGreater(min(b.distance(shapely.Point(100,10)) for b in buildings),6.2,"buildings stay outside the junction disk")

    def test_buildings_keep_clear_of_mapkit_inside_corner_fillets(self):
        # Suwon 1:3 regression: a 267 map cm T-junction; MapKit's curb fillet
        # (R = clamp(0.15 w, 20, 100) cm) bulges 0.29 R into the block corner,
        # beyond the straight corridor and the √2 × half width junction disk.
        from osm_generalize import corner_radius_cm
        self.setup_city()
        w = 8.01
        self.add(1, LineString([(0, 0), (60, 0)]), width_m=w, _city_refs=[1, 2])
        self.add(2, LineString([(0, 0), (-60, 0)]), width_m=w, _city_refs=[1, 3])
        self.add(3, LineString([(0, 0), (0, 60)]), width_m=w, _city_refs=[1, 4])
        h = w / 2
        self.add(4, box(h + 0.3, h + 0.3, h + 12, h + 12))
        worker = self.worker(3)
        out, meta = worker.candidate(0)
        [(feature, [building])] = self.solids(worker, out)
        r = corner_radius_cm(round(w * 100 / 3)) * 3 / 100
        fillet = box(h, h, h + r, h + r).difference(shapely.Point(h + r, h + r).buffer(r, quad_segs=64))
        self.assertGreater(building.distance(fillet), 0.25, "the building keeps the road clearance from the curb fillet")
        self.assertLess(building.area, 11.7**2, "only the corner is trimmed")
        self.assertGreater(building.area, 11.7**2 - 2)

    def test_erased_source_returns_trimmed_on_the_map_lattice(self):
        for scale in (8, 3):
            with self.subTest(scale=scale):
                self.setup_city()
                self.add(1,box(10.03,10.03,20.01,20.01))
                self.add(2,LineString([(0,9),(40,9)]),width_m=2,_city_refs=[1,2])
                worker=self.worker(scale)
                worker.polygon_group=lambda group,gap,buildings:[]  # A merge that erased every member.
                out,meta=worker.candidate(0)
                building=next(transform(worker.project,shape(f["geometry"])) for f in out["features"] if f["geometry"]["type"]=="Polygon")
                self.assertEqual(meta["unmerged_numeric_groups"],1)
                self.assertGreater(building.bounds[1],9+1+0.1*scale-0.05,"road clearance trim is kept")
                self.assertTrue(all(abs((v+local)*100/scale-round((v+local)*100/scale))<1e-6 for point in building.exterior.coords for v,local in zip(point,worker.local)))

    def run_city_cli(self, directory, layer_id, extra=()):
        import geojson
        from osm_city_fixture import xml as city_xml
        from osm_fixture import pbf
        from osm_extract import LICENSE
        source=Path(directory)/(layer_id+".pbf");pbf(source,city_xml())
        output=Path(directory)/(layer_id+".json")
        argv=["geojson.py",str(source),str(output),"--input-format","pbf","--coordinates","wgs84-utm","--origin","9","55",
              "--local-origin","512","512","--license",LICENSE,"--layer-id",layer_id,"--osm-bbox","8.9999","54.9999","9.002","55.002",
              "--osm-stream","--osm-city",*extra]
        events=[]
        with patch.object(sys,"argv",argv),patch("builtins.print",lambda *a,**k:events.append(a)):
            geojson.main()
        return json.loads(output.read_bytes())

    def test_city_ladder_adopts_the_largest_gap_with_warnings_when_no_gap_meets_targets(self):
        import import_layer, tempfile
        with tempfile.TemporaryDirectory() as directory:
            fitting=self.run_city_cli(directory,"a"*32)
            self.assertFalse(any(w.startswith("Limit warning: ") for w in fitting["warnings"]))
            import_layer.reset_limits()
            # No gap can meet a one-feature target: the largest gap (smallest
            # output) is adopted, every source is kept and the overrun warns.
            with patch.object(import_layer,"CITY_FEATURES",1),patch.object(import_layer,"CITY_POINTS",1):
                warned=self.run_city_cli(directory,"b"*32)
        meta=warned["coordinates"]["osm_city"]
        self.assertEqual(meta["gap_m"],max(json.loads(json.dumps(__import__("osm_generalize").LEVELS))))
        self.assertEqual(meta["source_ids"],fitting["coordinates"]["osm_city"]["source_ids"])
        self.assertEqual(len(warned["patches"]),len(fitting["patches"]))
        texts=[w for w in warned["warnings"] if w.startswith("Limit warning: ")]
        self.assertTrue(any("feature target" in w for w in texts) and any("position target" in w for w in texts),texts)
        self.assertLessEqual(len(warned["warnings"]),50)
        self.assertTrue(all(len(w)<=512 for w in warned["warnings"]))


    def test_city_cli_scale_is_recorded_and_requires_city_optimization(self):
        import import_layer, tempfile
        with tempfile.TemporaryDirectory() as directory:
            default=self.run_city_cli(directory,"c"*32)
            import_layer.reset_limits()
            eighth=self.run_city_cli(directory,"d"*32,("--osm-scale","8"))
            import_layer.reset_limits()
            third=self.run_city_cli(directory,"e"*32,("--osm-scale","3"))
        self.assertEqual(default["coordinates"]["osm_city"]["scale_denominator"],8,"the CLI default stays 1:8")
        self.assertEqual(json.dumps(eighth["patches"]).replace("d"*32,"c"*32),json.dumps(default["patches"]))
        meta=third["coordinates"]["osm_city"]
        self.assertEqual((meta["scale_denominator"],meta["grid_m"]),(3,0.03))
        self.assertTrue(any(w.startswith("Automatic city optimization at 1:3:") for w in third["warnings"]))
        self.assertEqual(meta["source_ids"],default["coordinates"]["osm_city"]["source_ids"])
        for argv in (["--osm-scale","3"],["--osm-city","--osm-scale","9"]):
            with self.subTest(argv=argv), patch.object(sys,"argv",["geojson.py","in.pbf","out.json","--coordinates","wgs84-utm","--license","x","--layer-id","f"*32,"--input-format","pbf",*argv]):
                import geojson
                with self.assertRaises((ValueError, SystemExit)), patch("sys.stderr",new=__import__("io").StringIO()):
                    geojson.main()


class CityRules(unittest.TestCase):
    """Building records, urban ground paint and barriers (synthetic layouts)."""
    setUp, setup_city, add, worker, solids = City.setUp, City.setup_city, City.add, City.worker, City.solids

    def site(self, identity, geometry, site, **properties):
        landuse = site if site in ("residential", "commercial", "retail", "industrial") else site
        outline = [list(map(list, transform(self.inverse, geometry).exterior.coords))]
        self.add(identity, geometry, osm_region=True, landuse=landuse, protected=False, _city_site=site, _city_outline=outline, **properties)

    def barrier_feature(self, identity, line, value, gates=(), **tags):
        from osm_extract import city_barrier
        p = dict(osm_source_id=f"way/{identity}", _city_barrier=city_barrier(dict(barrier=value, **tags)))
        if gates: p["_city_gates"] = [[*self.inverse(x, y), w] for x, y, w in gates]
        self.features.append(dict(type="Feature", properties=p, geometry=json.loads(json.dumps(mapping(transform(self.inverse, line))))))

    def records(self, worker, value):
        return {tuple(f["properties"]["_city_sources"]): solids for f, solids in self.solids(worker, value)}

    def barriers(self, worker, value):
        return [(f["properties"]["_city_barrier"], transform(worker.project, shape(f["geometry"]))) for f in value["features"] if "_city_barrier" in f["properties"]]

    def test_separate_footprints_are_never_fused_or_reshaped(self):
        self.setup_city()
        # Touching, 0.5 m and 3 m apart: every source stays its own recognisable solid.
        self.add(1, box(0, 0, 10, 10))
        self.add(2, box(10, 0, 20, 10))
        self.add(3, box(20.5, 0, 30, 10))
        self.add(4, box(33, 0, 43, 10))
        self.add(5, Polygon([(50, 0), (60, 0), (60, 4), (55, 4), (55, 10), (50, 10)]))  # An L keeps its notch.
        for gap in (64, 16, 0):
            with self.subTest(gap=gap):
                worker = self.worker(3)
                out, meta = worker.candidate(gap)
                [(sources, solids)] = self.records(worker, out).items()
                self.assertEqual(sources, tuple(f"way/{i}" for i in range(1, 6)))
                self.assertEqual(len(solids), 5, "five sources, five solids")
                for solid in solids:
                    owners = [i for i, g in enumerate((box(0,0,10,10), box(10,0,20,10), box(20.5,0,30,10), box(33,0,43,10))) if solid.intersection(g).area > 1]
                    self.assertLessEqual(len(owners), 1, "no solid spans two sources")
                l = max(solids, key=lambda g: g.bounds[0])
                self.assertLess(l.area, 75, "the L-shaped footprint is not filled to its bounding box")
                self.assertTrue(all(a.intersection(b).area < 1e-6 for i, a in enumerate(solids) for b in solids[i+1:]))

    def test_records_group_by_site_and_category_with_landmarks_alone(self):
        self.setup_city()
        self.site(100, box(0, 0, 100, 100), "residential")
        self.site(101, box(120, 0, 220, 100), "residential")
        self.add(1, box(10, 10, 30, 30), usage="apartments", _city_name="101동")
        self.add(2, box(40, 10, 60, 30), usage="apartments", _city_name="102동")
        self.add(3, box(10, 50, 30, 70), usage="commercial")
        self.add(4, box(130, 10, 150, 30), usage="apartments")
        self.add(5, box(160, 10, 180, 30), usage="apartments", _city_landmark=True)
        self.add(6, box(70, 70, 80, 80), usage="apartments", height_m=45)
        self.add(7, box(300, 10, 310, 20), _city_name="Shop")  # Named outside any site.
        self.add(8, box(320, 10, 330, 20))
        self.add(9, box(340, 10, 350, 20))
        self.add(10, box(600, 10, 610, 20), usage="shed", _city_site_relation="relation/9")
        self.add(11, box(900, 10, 910, 20), usage="shed", _city_site_relation="relation/9")
        worker = self.worker(3)
        out, meta = worker.candidate(64)
        records = self.records(worker, out)
        self.assertEqual(sorted(records), sorted([("way/1", "way/2"), ("way/3",), ("way/4",), ("way/5",), ("way/6",), ("way/7",), ("way/8", "way/9"), ("way/10", "way/11")]))
        named = next(f for f, solids in self.solids(worker, out) if f["properties"]["_city_sources"] == ["way/1", "way/2"])
        self.assertEqual(named["properties"]["_city_names"], ["101동", "102동"], "names of grouped buildings are kept")
        group = next(g for g in meta["groups"] if g["source_ids"] == ["way/1", "way/2"])
        self.assertEqual(group["names"], ["101동", "102동"])
        self.assertEqual(len(records[("way/10", "way/11")]), 2, "a type=site relation groups across 256 m tiles")
        self.assertEqual(meta["after"]["buildings"], 8)

    def test_record_parts_convert_to_one_building_with_its_own_heights(self):
        from geojson import convert
        self.setup_city()
        self.add(1, box(0, 0, 10, 10), height_m=9)
        self.add(2, box(20, 0, 30, 10), height_m=30)
        self.add(3, box(40, 0, 50, 10))
        worker = self.worker(3)
        out, meta = worker.candidate(16)
        layer = convert(out, "synthetic", "ODbL-1.0", coordinates=self.options, osm_graph=True, city=True)
        [building] = [p["after"] for p in layer.patches if p["field"] == "buildings"]
        self.assertEqual(len(building["parts"]), 2)
        heights = [building["height_cm"]] + [part.get("height_cm", building["height_cm"]) for part in building["parts"]]
        self.assertEqual(sorted(heights), [900, 1200, 3000], "every solid keeps its own source height")
        self.assertTrue(all("base_cm" not in part for part in building["parts"]), "equal bases are inherited")

    def test_ground_paint_grass_parking_and_water(self):
        self.setup_city()
        walk = lambda kind: dict(_city_road_tags=dict(highway=kind))
        self.add(1, box(0, 0, 200, 150), osm_region=True, landuse="park", protected=False, _city_ground=dict(kind="green", surface=None))
        self.add(2, box(40, 40, 80, 80), osm_region=True, landuse="water", protected=False)
        self.add(3, box(150, 20, 180, 40), osm_region=True, landuse="parking", protected=False, _city_ground=dict(kind="parking", surface=None))
        self.add(4, box(300, 0, 330, 30), osm_region=True, landuse="pitch", protected=False, _city_ground=dict(kind="green", surface="asphalt"))
        self.add(5, LineString([(10, 100), (190, 100)]), _city_refs=[1, 2], **walk("footway"))
        import random
        rng = random.Random(7)
        for k in range(40):  # Oblique footways cut the grass off the lattice.
            self.add(10 + k, LineString([(rng.uniform(1, 199), rng.uniform(1, 149)), (rng.uniform(1, 199), rng.uniform(1, 149))]), _city_refs=[100 + 2*k, 101 + 2*k], **walk("footway"))
        worker = self.worker(3)
        out, meta = worker.candidate(0)
        paint = [(f["properties"]["_city_paint"], f["properties"]["_city_sources"], transform(worker.project, shape(f["geometry"]))) for f in out["features"] if "_city_paint" in f["properties"]]
        surfaces = Counter(s for s, _, _ in paint)
        self.assertEqual(set(surfaces), {"grass", "asphalt", "concrete"})
        pond = box(40.2, 40.2, 79.8, 79.8)
        self.assertTrue(all(g.intersection(pond).area < 0.01 for s, _, g in paint if s != "concrete"), "water is never painted with area paint")
        lx, ly = worker.local
        lattice = [transform(lambda x, y, z=None: ((x+lx)*100/3, (y+ly)*100/3), g) for _, _, g in paint]
        self.assertTrue(all(abs(v-round(v)) < 1e-6 for g in lattice for point in g.exterior.coords for v in point), "whole map centimetres")
        snapped = [shapely.set_precision(g, 1) for g in lattice]
        self.assertTrue(all(a.intersection(b).area == 0 for i, a in enumerate(snapped) for b in snapped[i+1:]), "pieces never overlap on the map lattice")
        grass = unary_union([g for s, _, g in paint if s == "grass"])
        self.assertLess(grass.area, 200*150 - 40*40 - 30*20 - 180*1.6, "grass minus pond, parking and footways")
        self.assertTrue(any(s == "asphalt" and src == ["way/3"] for s, src, _ in paint), "parking is asphalt")
        self.assertTrue(any(s == "asphalt" and src == ["way/4"] for s, src, _ in paint), "a tagged hard pitch surface wins over grass")
        self.assertEqual(meta["ground_paint"]["grass"] + meta["ground_paint"]["asphalt"] + meta["ground_paint"]["pedestrian"], meta["ground_paint"]["pieces"])

    def test_explicit_barrier_kinds_and_heights_follow_the_scale(self):
        for scale in (3, 8):
            with self.subTest(scale=scale):
                self.setup_city()
                self.add(1, LineString([(0, -50), (400, -50)]), width_m=6, _city_refs=[1, 2], _city_road_tags=dict(highway="residential"))
                self.barrier_feature(2, LineString([(0, 0), (40, 0)]), "hedge")
                self.barrier_feature(3, LineString([(0, 10), (40, 10)]), "wall")
                self.barrier_feature(4, LineString([(0, 20), (40, 20)]), "retaining_wall")
                self.barrier_feature(5, LineString([(0, 30), (40, 30)]), "fence", fence_type="chain_link")
                self.barrier_feature(6, LineString([(0, 40), (40, 40)]), "fence", height="1.8")
                self.barrier_feature(7, LineString([(0, 50), (40, 50), (40, 90), (0, 90), (0, 50)]), "fence")
                worker = self.worker(scale)
                out, meta = worker.candidate(16)
                found = {f["properties"]["osm_source_id"]: f["properties"]["_city_barrier"] for f in out["features"] if "_city_barrier" in f["properties"]}
                cm = lambda m: round(m * 100 / scale)
                expected = {"way/2": ("hedge", 0.8, 0.6), "way/3": ("wall", 2.0, 0.3), "way/4": ("wall", 2.0, 0.3), "way/5": ("fence", 1.2, 0.1), "way/6": ("fence", 1.8, 0.1), "way/7": ("fence", 1.2, 0.1)}
                for source, (kind, height, thickness) in expected.items():
                    b = found[source]
                    self.assertEqual(b["kind"], kind)
                    self.assertEqual(round(b["height_m"] * 100 / scale), cm(height), "height in source metres ÷D")
                    self.assertEqual(round(b["thickness_m"] * 100 / scale), min(100, max(5, cm(thickness))), "thickness ÷D within 5..100 map cm")
                closed = next(g for b, g in self.barriers(worker, out) if g.length > 150)
                self.assertEqual(closed.coords[0], closed.coords[-1], "a closed perimeter repeats its first point")
                self.assertEqual(meta["after"]["barriers"], 6)
                self.assertIn("way/7", meta["source_ids"])

    def test_explicit_barriers_open_at_paths_painted_driveways_and_gate_nodes(self):
        from osm_extract import gate_points
        self.setup_city()
        walk = lambda kind, **extra: dict(_city_road_tags=dict(highway=kind, **extra))
        self.add(1, LineString([(0, -60), (200, -60)]), width_m=6, _city_refs=[1, 2], _city_road_tags=dict(highway="residential"))
        self.add(2, LineString([(30, -40), (30, 40)]), _city_refs=[3, 4], **walk("footway"))
        self.add(3, LineString([(80, -60), (80, 30)]), width_m=3, _city_refs=[2, 5], **walk("service", service="driveway"))
        self.barrier_feature(4, LineString([(0, 0), (200, 0)]), "fence", gates=[(140, 0, 3.0), (180, 0, 1.5)])
        worker = self.worker(3)
        out, meta = worker.candidate(16)
        pieces = sorted((g for b, g in self.barriers(worker, out)), key=lambda g: g.bounds[0])
        self.assertEqual(len(pieces), 5, "a footway, a painted driveway and two gate nodes open four gaps")
        gaps = [(a.bounds[2], b.bounds[0]) for a, b in zip(pieces, pieces[1:])]
        for (lo, hi), centre, width in zip(gaps, (30, 80, 140, 180), (1.6/2 + 2, 3/2 + 2, 1.5, 0.75)):
            self.assertLess(lo, centre); self.assertGreater(hi, centre)
            self.assertAlmostEqual(hi - lo, 2 * width, delta=0.1)
        self.assertEqual(meta["barriers"]["explicit_records"], 5)
        self.assertNotIn("way/4", meta["barriers"]["dropped_sources"])
        # Gate nodes come from the barrier way's own nodes; width tags win.
        nodes = {1: [9, 55], 2: [9.001, 55], 3: [9.002, 55]}
        tags = {2: dict(barrier="lift_gate"), 3: dict(barrier="kissing_gate", width="0.9")}
        self.assertEqual(gate_points([1, 2, 3, 2], nodes, tags), [[9.001, 55, 3.0], [9.002, 55, 0.9]])

    def test_guard_rail_on_a_bridge_is_skipped(self):
        self.setup_city()
        bridge = dict(road_kind="bridge", elevations_m=[6.0, 6.0], osm_way_id=1, osm_node_refs=[1, 2], width_m=8, _city_road_tags=dict(highway="primary"))
        self.add(1, LineString([(0, 0), (100, 0)]), **bridge)
        self.barrier_feature(2, LineString([(10, 4), (90, 4)]), "guard_rail")
        self.barrier_feature(3, LineString([(10, 40), (90, 40)]), "guard_rail")
        worker = self.worker(3)
        out, meta = worker.candidate(16)
        self.assertEqual([f["properties"]["osm_source_id"] for f in out["features"] if "_city_barrier" in f["properties"]], ["way/3"])
        self.assertEqual(meta["barriers"]["skipped_bridge_guard_rails"], 1)
        self.assertEqual(meta["barriers"]["dropped_sources"], ["way/2"])
        self.assertNotIn("way/2", meta["source_ids"])

    def test_inferred_perimeters_gates_coverage_and_explicit_wins(self):
        self.setup_city()
        walk = lambda kind: dict(_city_road_tags=dict(highway=kind))
        self.site(100, box(0, 0, 120, 100), "residential")
        self.add(1, box(10, 10, 50, 30), usage="apartments")
        self.add(2, box(60, 10, 100, 30), usage="apartments")
        self.add(3, box(10, 50, 50, 70), _city_levels=9)  # building=yes, 27 m tall.
        self.add(4, LineString([(60, -20), (60, 40)]), _city_refs=[1, 2], **walk("footway"))
        self.barrier_feature(5, LineString([(0, 101), (120, 101)]), "fence")
        self.site(200, box(200, 0, 300, 100), "residential")  # Two towers but 4 % coverage.
        self.add(6, box(210, 10, 220, 20), usage="apartments")
        self.add(7, box(230, 10, 240, 20), usage="apartments")
        self.site(300, box(400, 0, 500, 80), "school")
        self.site(400, box(600, 0, 700, 80), "industrial", _city_gates=[[*self.inverse(650, 0), 3.0]])
        self.site(500, box(800, 0, 900, 80), "commercial")
        worker = self.worker(3)
        out, meta = worker.candidate(16)
        found = [(f["properties"]["_city_sources"], f["properties"]["_city_barrier"], transform(worker.project, shape(f["geometry"]))) for f in out["features"] if "_city_barrier" in f["properties"]]
        complex_ = [(b, g) for s, b, g in found if s == ["way/100"]]
        self.assertEqual(len(complex_), 2, "the footway gate splits the perimeter")
        self.assertTrue(all(b["kind"] == "fence" and round(b["height_m"] * 100 / 3) == 40 for b, g in complex_))
        gate = shapely.Point(60, 0)
        self.assertGreater(min(g.distance(gate) for b, g in complex_), 2.7, "gate of half the footway width + 2 m")
        self.assertTrue(all(g.distance(LineString([(0, 101), (120, 101)])) > 2.9 for b, g in complex_), "the explicit fence wins within 3 m")
        self.assertFalse(any(s == ["way/200"] for s, b, g in found), "below 15 % coverage no perimeter is inferred")
        [(school, sg)] = [(b, g) for s, b, g in found if s == ["way/300"]]
        self.assertEqual((school["kind"], round(school["height_m"] * 100 / 3)), ("fence", 67))
        self.assertEqual(sg.coords[0], sg.coords[-1])
        [(industry, ig)] = [(b, g) for s, b, g in found if s == ["way/400"]]
        self.assertEqual((industry["kind"], round(industry["height_m"] * 100 / 3)), ("wall", 67))
        self.assertNotEqual(ig.coords[0], ig.coords[-1], "a gate node opens the inferred wall")
        self.assertGreater(ig.distance(shapely.Point(650, 0)), 1.4)
        self.assertFalse(any(s == ["way/500"] for s, b, g in found), "commercial land gets no perimeter")
        self.assertEqual(meta["barriers"]["inferred_sites"], 3)

    def test_city_cli_rules_end_to_end(self):
        import import_layer, tempfile, geojson
        from osm_city_rules_fixture import xml as rules_xml, BBOX
        from osm_fixture import pbf
        from osm_extract import LICENSE
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "rules.pbf"; pbf(source, rules_xml())
            output = Path(directory) / "rules.json"
            argv = ["geojson.py", str(source), str(output), "--input-format", "pbf", "--coordinates", "wgs84-utm", "--origin", "9", "55",
                    "--local-origin", "512", "512", "--license", LICENSE, "--layer-id", "9" * 32, "--osm-bbox", *map(str, BBOX),
                    "--osm-stream", "--osm-city", "--osm-scale", "3"]
            with patch.object(sys, "argv", argv), patch("builtins.print", lambda *a, **k: None):
                geojson.main()
            value = json.loads(output.read_bytes())
        meta = value["coordinates"]["osm_city"]
        fields = Counter(p["field"] for p in value["patches"])
        self.assertEqual(fields["buildings"], 6, "apartments, school, houses, historic, named and site-relation records")
        self.assertEqual(meta["building_records"], dict(grouped_records=3, records=6, solids=10))
        self.assertEqual(meta["barriers"]["explicit_records"], 5, "the lift gate splits its fence")
        self.assertEqual(meta["barriers"]["inferred_sites"], 3)
        self.assertEqual(fields["barriers"], meta["after"]["barriers"])
        kinds = Counter(p["after"]["kind"] for p in value["patches"] if p["field"] == "barriers")
        self.assertEqual(kinds, Counter(fence=6, wall=2, hedge=1))
        surfaces = Counter(p["after"]["surface"] for p in value["patches"] if p["field"] == "surface_areas")
        self.assertGreater(surfaces["grass"], 0)
        self.assertGreater(surfaces["asphalt"], 0)
        self.assertIn("way/6", meta["source_ids"], "an explicit barrier way is mapped")
        self.assertEqual({r["landuse"] for r in value["coordinates"]["generation_regions"]}, {"residential", "park", "water", "industrial"},
                         "city-only areas (school, parking) are rule inputs, not generation regions")
        self.assertTrue({"way/10", "way/22"} <= set(meta["source_ids"]), "city-only areas stay mapped")
        for p in value["patches"]:
            if p["field"] == "barriers":
                self.assertTrue(all(v % 3 == 0 for point in p["after"]["line"] for v in point), "barrier vertices on the 1:3 lattice")
                self.assertEqual(p["after"]["height_cm"] % 3, 0)


class LimitWarnings(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()
        self.addCleanup(import_layer.reset_limits)

    def test_one_entry_per_code_keeps_count_largest_actual_and_reserved_slots(self):
        import import_layer
        from import_layer import ImportLayer, Source, soft_limit
        soft_limit("a", 5, 1, "First budget")
        soft_limit("a", 3, 1, "First budget")
        soft_limit("b", 7, 2, "Document limit", True)
        entries={e["code"]:e for e in import_layer.limit_entries()}
        self.assertEqual((entries["a"]["count"],entries["a"]["actual"]),(2,5))
        self.assertEqual(import_layer.limit_text(entries["a"]),"Limit warning: First budget (5 > 1)")
        self.assertEqual(import_layer.limit_text(entries["b"]),"Limit warning: Document limit (7 > 2); the game refuses maps beyond this")
        layer=ImportLayer("c"*32,Source("s","0"*64,1,"MIT","unknown"),{})
        for i in range(60): layer.warning(f"ordinary {i}")
        first=layer.encode()
        self.assertEqual(len(layer.warnings),50)
        self.assertEqual(layer.warnings[-2:],[import_layer.limit_text(entries["a"]),import_layer.limit_text(entries["b"])])
        self.assertEqual(layer.warning_count,62)
        self.assertEqual(layer.encode(),first,"encoding is idempotent")
        self.assertEqual(layer.warning_count,62)
        soft_limit("x"*600,1,0,"y"*600)
        layer.encode()
        self.assertTrue(all(len(w)<=512 for w in layer.warnings))
        snapshot=import_layer.limit_snapshot()
        import_layer.reset_limits()
        self.assertEqual(import_layer.limit_entries(),[])
        import_layer.limit_restore(snapshot)
        self.assertEqual(len(import_layer.limit_entries()),3)

    def test_progress_is_throttled_per_stage_and_keeps_first_last_and_seq(self):
        from import_layer import Progress, PROGRESS_INTERVAL
        now, lines = [0.0], []
        progress = Progress("r", clock=lambda: now[0], write=lines.append)
        for completed in range(0, 1001):
            progress("read", completed, 1000)  # One stage, no time passes.
        progress("parse", 0, 5)
        progress("parse", 1, 5)
        now[0] += PROGRESS_INTERVAL
        progress("parse", 2, 5)
        progress("optimize", 0, 7, "steps")
        progress("optimize", 1, 7, "steps", gap_m=64)  # Extra fields are never dropped.
        progress("complete", 9, 9, sha256="0"*64)
        events = [json.loads(line) for line in lines]
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events)+1)))
        self.assertEqual([(e["stage"], e["completed"]) for e in events],
                         [("read",0),("read",1000),("parse",0),("parse",2),("optimize",0),("optimize",1),("complete",9)])
        self.assertEqual(events[-1]["sha256"], "0"*64)

if __name__=="__main__": unittest.main()
