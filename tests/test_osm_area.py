import sys, json, unittest, tempfile, subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from osm_area import crop, bounds
from osm_extract import parse, LICENSE
from osm_fixture import XML, pbf
from shapely.geometry import shape


def feature(kind, coordinates):
    return dict(type="Feature", properties={}, geometry=dict(type=kind, coordinates=coordinates))
def run(features, box=[0,0,0.01,0.01]):
    return crop(dict(type="FeatureCollection", features=features), box)

class CropTests(unittest.TestCase):
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
    def test_empty_tangent_invalid_and_caps(self):
        with self.assertRaisesRegex(ValueError,"no supported"): run([feature("LineString",[[-.001,0],[0,0]])])
        with self.assertRaisesRegex(ValueError,"Invalid OSM"): run([feature("Polygon",[[[1,1],[2,2],[1,2],[2,1],[1,1]]])])
        for b in [[0,0,0,1],[0,0,.021,.01],[179,0,-179,1],[False,0,.01,.01],[0,0,float("nan"),.01]]:
            with self.subTest(b=b), self.assertRaises(ValueError): bounds(b)
        with patch("osm_area.MAX_POINTS",1), self.assertRaisesRegex(ValueError,"budget"): run([feature("LineString",[[0,0],[.01,.01]])])
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

if __name__=="__main__": unittest.main()
