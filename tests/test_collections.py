"""Whole-source GeometryCollection normalization; synthetic local geometry only."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
import geojson
from projection import Coordinates


def ring(x, y):
    return [[x,y],[x+10,y],[x+10,y+10],[x,y+10],[x,y]]


def fixture():
    return dict(type="FeatureCollection", features=[dict(type="Feature", properties=dict(width_m=6,height_m=8),
        geometry=dict(type="GeometryCollection", geometries=[
            dict(type="LineString", coordinates=[[10,10],[20,10]]),
            dict(type="GeometryCollection", geometries=[
                dict(type="MultiLineString", coordinates=[[[10,30],[20,30]],[[10,40],[20,40]]]),
                dict(type="Polygon", coordinates=[ring(50,50)])])])),
        dict(type="Feature", properties=dict(landuse="forest"), geometry=dict(type="MultiPolygon", coordinates=[[ring(100,100)],[ring(150,150)]]))])


class Collections(unittest.TestCase):
    def setUp(self):
        import import_layer
        import_layer.reset_limits()  # Limit warnings are process-wide; isolate tests.

    def test_order_parent_properties_exact_tree_mapping_and_no_source_mutation(self):
        value=fixture(); original=copy.deepcopy(value); raw=json.dumps(value).encode()
        layer=geojson.convert(value,"synthetic","MIT",layer_id="a"*32,source_bytes=raw)
        self.assertEqual(value,original)
        self.assertEqual(layer.source.sha256,hashlib.sha256(raw).hexdigest())
        self.assertEqual((layer.feature_count,layer.point_count,len(layer.patches)),(4,18,12))
        meta=layer.coordinates["geojson_collections"]
        self.assertEqual(meta["sources"],[dict(feature=0,tree=[0,[1,2]]),dict(feature=1,tree=3)])
        self.assertEqual([leaf["geometry"] for leaf in meta["leaves"]],["LineString","MultiLineString","Polygon","MultiPolygon"])
        self.assertEqual([leaf["point_count"] for leaf in meta["leaves"]],[2,4,4,8])
        self.assertEqual([rid for leaf in meta["leaves"] for rid in leaf["record_ids"]],[p["id"] for p in layer.patches])
        self.assertTrue(all("-collection" in p["id"] for p in layer.patches))
        self.assertTrue(all(p["after"]["widths_cm"]==[600] for p in layer.patches if p["field"]=="roads"))
        self.assertEqual([p["after"]["height_cm"] for p in layer.patches if p["field"]=="buildings"],[800])
        self.assertEqual(sum(p["field"]=="zones" for p in layer.patches),2)
        self.assertIn("-1-collection-part-0",layer.coordinates["geojson_multilines"]["features"][0]["road_ids"][0])
        self.assertEqual(layer.encode(),geojson.convert(value,"synthetic","MIT",layer_id="a"*32,source_bytes=raw).encode())

    def test_empty_unsupported_and_malformed_leaf_reject_entire_source(self):
        for geometry in [None,[],dict(type="GeometryCollection",geometries=[]),dict(type="GeometryCollection",geometries={},coordinates=[]),
                         dict(type="Point",coordinates=[1,2]),dict(type="MultiPoint",coordinates=[[1,2]]),
                         dict(type="LineString",coordinates=[[1,2],[2,3,4]]),
                         dict(type="LineString",coordinates=[[1,2],[2,3]],crs={})]:
            value=fixture(); value["features"][0]["geometry"]["geometries"].append(geometry)
            with self.subTest(geometry=geometry),self.assertRaises(ValueError):geojson.convert(value,"bad","MIT")
        value=fixture();value["features"][0]["properties"]["road_kind"]="bridge"
        with self.assertRaisesRegex(ValueError,"structural/OSM"):geojson.convert(value,"bad","MIT")
        with self.assertRaisesRegex(ValueError,"OSM graph"):geojson.convert(fixture(),"bad","MIT",osm_graph=True)

    def test_tree_depth_node_leaf_record_and_output_budgets(self):
        import import_layer
        self.addCleanup(import_layer.reset_limits)
        value=fixture(); leaf=dict(type="LineString",coordinates=[[1,2],[2,3]])
        for _ in range(65): leaf=dict(type="GeometryCollection",geometries=[leaf])
        value["features"][0]["geometry"]=leaf
        with self.assertRaisesRegex(ValueError,"nesting"):geojson.convert(value,"large","MIT")
        # Former budgets warn; the raised ceilings still refuse before projection.
        for name,limit,code in [("MAX_COLLECTION_NODES",2,"collection_nodes"),("MAX_COLLECTION_LEAVES",1,"collection_leaves")]:
            import_layer.reset_limits()
            layer=geojson.convert(fixture(),"large","MIT")
            self.assertEqual(import_layer.limit_entries(),[])
            with patch.object(geojson,name,limit):layer=geojson.convert(fixture(),"large","MIT")
            self.assertIn(code,{e["code"] for e in import_layer.limit_entries()})
            self.assertTrue(any(w.startswith("Limit warning: ") for w in layer.warnings))
        for name,limit,message in [("COLLECTION_NODES_CEILING",2,"node ceiling"),("COLLECTION_LEAVES_CEILING",1,"leaf ceiling")]:
            with patch.object(geojson,name,limit),patch.object(Coordinates,"point",side_effect=AssertionError("projected before tree admission")):
                with self.assertRaisesRegex(ValueError,message):geojson.convert(fixture(),"large","MIT")
        for name,limit,code in [("MAX_RECORDS",3,"import_records"),("MAX_POINTS",4,"import_coordinates"),("MAX_OUTPUT",128,"import_output")]:
            import_layer.reset_limits()
            with patch("import_layer."+name,limit):layer=geojson.convert(fixture(),"large","MIT")
            entry=next(e for e in import_layer.limit_entries() if e["code"]==code)
            self.assertGreater(entry["actual"],entry["limit"])
            self.assertIn(import_layer.limit_text(entry),layer.warnings)

    def test_noncollection_output_and_fresh_namespaces(self):
        value=fixture();value["features"]=value["features"][1:]
        plain=geojson.convert(value,"plain","MIT")
        self.assertNotIn("geojson_collections",plain.coordinates)
        self.assertTrue(all("-collection" not in p["id"] for p in plain.patches))
        a=geojson.convert(fixture(),"a","MIT");b=geojson.convert(fixture(),"a","MIT")
        self.assertTrue(set(p["id"] for p in a.patches).isdisjoint(p["id"] for p in b.patches))

    def test_cli_atomic_publication_and_original_preservation(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/"source.geojson";source.write_text(json.dumps(fixture()));original=source.read_bytes()
            output=Path(d)/"result.json"
            command=[sys.executable,"-B",str(Path(geojson.__file__)),str(source),str(output),"--license","MIT","--coordinates","local-metres","--layer-id","a"*32]
            run=subprocess.run(command,capture_output=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr)
            result=output.read_bytes();self.assertEqual(source.read_bytes(),original)
            self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=10).returncode,0)
            self.assertEqual(output.read_bytes(),result)
            value=fixture();value["features"][0]["geometry"]["geometries"].append(dict(type="Point",coordinates=[1,2]))
            source.write_text(json.dumps(value));command[4]=str(Path(d)/"rejected.json")
            self.assertNotEqual(subprocess.run(command,capture_output=True,timeout=10).returncode,0)
            self.assertFalse(Path(command[4]).exists())


if __name__=="__main__":unittest.main()
