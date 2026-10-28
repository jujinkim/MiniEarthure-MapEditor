import sys, json, unittest, tempfile, subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from osm_area import crop, bounds, projected_bounds
from osm_extract import parse, LICENSE
from osm_fixture import XML, pbf
from shapely.geometry import shape


def feature(kind, coordinates):
    return dict(type="Feature", properties={}, geometry=dict(type=kind, coordinates=coordinates))
def run(features, box=[0,0,0.01,0.01]):
    return crop(dict(type="FeatureCollection", features=features), box)

class CropTests(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def test_line_crossings_no_inside_nodes_and_split(self):
        f=feature("LineString",[[-.001,.002],[.011,.002],[.011,.008],[-.001,.008]])
        result, meta=run([f])
        self.assertEqual(len(result["features"]),2)
        for part in result["features"]: self.assertAlmostEqual(shape(part["geometry"]).length,.01)
        self.assertEqual(meta["counts"]["changed_features"],1)
        self.assertEqual(run([f]), (result,meta))
    def test_polygon_holes_and_split_parts(self):
        polygon=feature("Polygon",[[[-.001,-.001],[.011,-.001],[.011,.011],[-.001,.011],[-.001,-.001]],[[.002,.002],[.002,.008],[.008,.008],[.008,.002],[.002,.002]]])
        result,_=run([polygon]); clipped=shape(result["features"][0]["geometry"])
        self.assertAlmostEqual(clipped.area,.000064)
        self.assertEqual(len(clipped.geoms[0].interiors),1)
        # A courtyard that crosses both sides splits the output into two solids.
        polygon["geometry"]["coordinates"][1]=[[-.0005,.004],[.0105,.004],[.0105,.006],[-.0005,.006],[-.0005,.004]]
        result,_=run([polygon]); self.assertEqual(len(shape(result["features"][0]["geometry"]).geoms),2)
    def test_region_clips_concave_areas_with_unique_cuts(self):
        from shapely.geometry import Polygon
        # L-shaped union: a road along y=.008 leaves and re-enters the region twice.
        region = Polygon([(0,0),(.01,0),(.01,.01),(.006,.01),(.006,.004),(.004,.004),(.004,.01),(0,.01)])
        road = dict(type="Feature", properties=dict(osm_way_id=7, osm_node_refs=[1,2], road_kind="ground"),
                    geometry=dict(type="LineString", coordinates=[[-.001,.008],[.011,.008]]))
        block = feature("Polygon",[[[.003,.007],[.007,.007],[.007,.009],[.003,.009],[.003,.007]]])
        result, meta = crop(dict(type="FeatureCollection", features=[road, block]), [0,0,.01,.01], region=region, areas=[dict(source_id="relation/1", name="A")])
        roads = [f for f in result["features"] if "osm_node_refs" in f["properties"]]
        self.assertEqual([round(shape(f["geometry"]).length, 9) for f in roads], [.004, .004])
        cuts = [r for f in roads for r in f["properties"]["osm_node_refs"]]
        self.assertEqual(len(cuts), len(set(cuts)))
        self.assertTrue(all(isinstance(r, str) and r.startswith("crop-0-0-") for r in cuts))
        blocks = [shape(f["geometry"]) for f in result["features"] if "osm_node_refs" not in f["properties"]]
        self.assertAlmostEqual(sum(b.area for b in blocks), .002*.001*2)
        self.assertEqual((meta["region"], meta["areas"][0]["source_id"]), ("administrative-union-v1", "relation/1"))
        # Ordinary roads keep their source identity when covered, and cut pieces are
        # rejoined across area vertices rather than split per segment.
        wavy = Polygon([(0,0)]+[(.001*i, .0001*(i%2)) for i in range(1,10)]+[(.01,0),(.01,.01),(0,.01)])
        inside = dict(type="Feature", properties=dict(osm_source_id="way/9", _city_refs=[1,2,3], _city_ends=["1","3"]),
                      geometry=dict(type="LineString", coordinates=[[.002,.005],[.004,.006],[.006,.005]]))
        through = dict(type="Feature", properties=dict(osm_source_id="way/10", _city_refs=[4,5,6], _city_ends=["4","6"]),
                       geometry=dict(type="LineString", coordinates=[[.002,-.002],[.002,.004],[.003,.008]]))
        out, _ = crop(dict(type="FeatureCollection", features=[inside, through]), [0,-.01,.01,.01], region=wavy)
        self.assertEqual(out["features"][0], inside)
        self.assertEqual(len(out["features"]), 2)
        self.assertEqual(out["features"][1]["properties"]["_city_ends"], [None, "6"])
        # A boundary grazing a road's first vertex leaves a sub-centimetre sliver,
        # which is a boundary contact rather than a road piece.
        graze = Polygon([(0,0),(.01,0),(.01,.01),(.0020000005,.01),(.0020000005,.0060000005),(0,.0060000005)])
        road = dict(type="Feature", properties=dict(osm_source_id="way/11", _city_refs=[7,8], _city_ends=["7","8"]),
                    geometry=dict(type="LineString", coordinates=[[.002,.006],[.0005,.009]]))
        _, meta = crop(dict(type="FeatureCollection", features=[road, inside]), [0,0,.01,.01], region=graze)
        self.assertEqual((meta["counts"]["output_features"], meta["counts"]["boundary_contacts"]), (1, 1))
        # The minimum drivable piece is one map centimetre at the adopted 1:D: the
        # ~6 cm source sliver is a contact at 1:8 (8 cm) but a road piece at 1:3.
        sliver = Polygon([(0,0),(.01,0),(.01,.01),(.00200025,.01),(.00200025,.0060005),(0,.0060005)])
        for denominator, expected in ((8, (1, 1)), (3, (2, 0))):
            with self.subTest(denominator=denominator):
                _, meta = crop(dict(type="FeatureCollection", features=[road, inside]), [0,0,.01,.01], region=sliver, denominator=denominator)
                self.assertEqual((meta["counts"]["output_features"], meta["counts"]["boundary_contacts"]), expected)
        for bad in (0, 9, 3.0, True):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, "integer denominator"):
                crop(dict(type="FeatureCollection", features=[road]), [0,0,.01,.01], region=graze, denominator=bad)
        # A pinched boundary splits one park into two parts touching at a point.
        pinch = Polygon([(0,0),(.01,0),(.005,.005),(.01,.01),(0,.01),(.005,.005)]).buffer(0)
        park = feature("Polygon",[[[.004,.003],[.009,.003],[.009,.007],[.004,.007],[.004,.003]]])
        parts, _ = crop(dict(type="FeatureCollection", features=[park]), [0,0,.01,.01], region=pinch)
        self.assertEqual(len(parts["features"]), 2)
        # Two source nodes at one stored position: a covered building keeps its
        # shape but not the repeated vertex, as a rectangle crop would.
        twin = feature("Polygon",[[[.001,.001],[.002,.001],[.002,.001],[.002,.002],[.001,.002],[.001,.001]]])
        kept, _ = crop(dict(type="FeatureCollection", features=[twin]), [0,0,.01,.01], region=region)
        self.assertEqual(len(kept["features"][0]["geometry"]["coordinates"][0][0]), 5)
        with self.assertRaisesRegex(ValueError, "do not overlap"):
            crop(dict(type="FeatureCollection", features=[road]), [.02,.02,.03,.03], region=region)

    def test_play_area_rings_follow_the_window_on_the_map_lattice(self):
        from shapely.geometry import Polygon
        from osm_area import play_area
        import math
        options = dict(mode="wgs84-utm", origin=[9.005, 55.005], local_origin_m=[1000, 1000])
        self.assertEqual(play_area([9, 55, 9.01, 55.01], None, options, 3), [])
        # A wavy region (1,200 vertices) clipped by the rectangle's east edge.
        wave = [(9 + .012 * i / 600, 55.0005 + .0003 * math.sin(i)) for i in range(601)]
        region = Polygon(wave + [(9.012, 55.009), (9, 55.009)])
        [ring] = play_area([9, 55, 9.01, 55.01], region, options, 3)
        self.assertLessEqual(len(ring), 512)
        self.assertTrue(all(v % 3 == 0 for point in ring for v in point), "source cm multiples of D")
        self.assertTrue(Polygon(ring).is_valid and Polygon([(x/3, y/3) for x, y in ring]).is_valid)
        xs = [x for x, y in ring]
        self.assertLess(max(xs) - min(xs), 0.0101 * 64000 * 100 / 1, "clipped to the rectangle")

    def test_an_estimated_chain_is_kept_whole_when_any_way_touches_the_region(self):
        from shapely.geometry import box
        def way(identity, coordinates, heights, chain):
            return dict(type="Feature", properties=dict(osm_source_id=f"way/{identity}", _city_estimated_m=heights, _city_estimated_kind="bridge",
                        _city_refs=[identity, identity+1], _city_ends=[str(identity), str(identity+1)], _city_estimated_chain=chain),
                        geometry=dict(type="LineString", coordinates=coordinates))
        a = way(1, [[.0005,.0005],[.0015,.0005]], [0.0, 6.0], 1)
        b = way(2, [[.0015,.0005],[.0025,.0005]], [6.0, 0.0], 1)
        c = way(3, [[.0018,.0008],[.0028,.0008]], [0.0, 0.0], 3)
        out, meta = crop(dict(type="FeatureCollection", features=[a, b, c]), [0,0,.003,.001], region=box(0,0,.0012,.001))
        self.assertEqual([f["properties"]["osm_source_id"] for f in out["features"]], ["way/1", "way/2"], "the chain's outside way stays; its deck must not end in the air")
        self.assertEqual(out["features"][1], b)
        self.assertEqual(meta["counts"]["outside_features"], 1)

    def test_empty_tangent_invalid_and_caps(self):
        with self.assertRaisesRegex(ValueError,"no supported"): run([feature("LineString",[[-.001,0],[0,0]])])
        with self.assertRaisesRegex(ValueError,"Invalid OSM"): run([feature("Polygon",[[[1,1],[2,2],[1,2],[2,1],[1,1]]])])
        for b in [[0,0,0,1],[179,0,-179,1],[False,0,.01,.01],[0,0,float("nan"),.01]]:
            with self.subTest(b=b), self.assertRaises(ValueError): bounds(b)
        import import_layer
        self.addCleanup(import_layer.reset_limits)
        import_layer.reset_limits()
        # The crop output budget warns; the source feature is kept.
        with patch("osm_area.MAX_POINTS",1): out=run([feature("LineString",[[0,0],[.01,.01]])])
        self.assertIn("crop_points", {e["code"] for e in import_layer.limit_entries()})
        with patch("osm_area.version",return_value="0"), self.assertRaisesRegex(ValueError,"requirements-import"): run([])
    def test_osm_xml_pbf_parity_and_cli(self):
        script=Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"source.pbf"; raw=pbf(path)
            b=[9,55,9.0005,55.0005]
            self.assertEqual(crop(parse(raw,"pbf")[0],b),crop(parse(XML.encode(),"osm")[0],b))
            output=Path(directory)/"layer.json"
            command=[sys.executable,str(script),str(path),str(output),"--input-format","pbf","--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512","--license",LICENSE,"--layer-id","a"*32,"--osm-bbox",*map(str,b)]
            result=subprocess.run(command,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)
            layer=json.loads(output.read_bytes()); self.assertEqual(layer["coordinates"]["osm_crop"]["bbox"],b)
            self.assertEqual(path.read_bytes(),raw)
            saved=output.read_bytes()
            self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=15).returncode,0)
            self.assertEqual(output.read_bytes(),saved)
            self.assertIn("crop",layer["warnings"][0])
    def test_unsupported_outside_not_hidden(self):
        raw=XML.replace('k="width"','k="bridge"').encode()
        with self.assertRaises(ValueError): crop(parse(raw,"osm")[0],[9,55,9.00001,55.00001])

    def test_city_extent_uses_projection_radius_and_strip(self):
        coordinates = dict(mode="wgs84-utm", origin=[9,55], local_origin_m=[0,0])
        self.assertEqual(projected_bounds([8.9,54.9,9.1,55.1],coordinates),[8.9,54.9,9.1,55.1])
        with self.assertRaisesRegex(ValueError,"20 km"): projected_bounds([8.9,54.7,9.1,55.3],coordinates)
        with self.assertRaisesRegex(ValueError,"strip"): projected_bounds([5.9,54.9,9.1,55.1],coordinates)

if __name__=="__main__": unittest.main()
