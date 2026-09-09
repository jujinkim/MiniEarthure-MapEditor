"""Synthetic standalone tests: python3 -m unittest discover -s tests -p test_importers.py."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from geojson import convert
from import_layer import strict_json


def fixture():
    return {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [[[10,10],[30,10],[30,30],[10,30],[10,10]]]}}]}


class ImportTests(unittest.TestCase):
    def test_metadata_and_new_namespace(self):
        value = fixture()
        raw = json.dumps(value).encode()
        a = convert(value, "source.geojson", "MIT", source_bytes=raw, accuracy="survey 0.5 m")
        b = convert(value, "source.geojson", "MIT")
        self.assertNotEqual(a.layer_id, b.layer_id)
        self.assertEqual(a.source.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(a.source.accuracy, "survey 0.5 m")
        self.assertEqual(a.extent_cm, [1000,1000,3000,3000])
        self.assertEqual(a.estimates["height_m"], 1)
        self.assertIsNone(a.patches[0]["before"])
        self.assertEqual(json.loads(a.encode())["import_version"], 1)
        self.assertEqual(value, fixture())

    def test_bad_shapes_and_numbers(self):
        mutations = [lambda v: v.update(crs={}), lambda v: v.update(features=[]),
            lambda v: v["features"].append(None), lambda v: v["features"][0].update(properties=[]),
            lambda v: v["features"][0]["properties"].update(height_m=True),
            lambda v: v["features"][0]["properties"].update(height_m=float("nan")),
            lambda v: v["features"][0]["geometry"].update(type="Point"),
            lambda v: v["features"][0]["geometry"]["coordinates"][0].pop(),
            lambda v: v["features"][0]["geometry"]["coordinates"].append([[1,1],[2,1],[1,2],[1,1]]),
            lambda v: v["features"][0]["geometry"]["coordinates"][0][1].append(2)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                value = fixture(); mutate(value)
                with self.assertRaises(ValueError): convert(value, "source", "MIT")
        for license_name in ["", "  ", "MIT\n", False]:
            with self.assertRaises(ValueError): convert(fixture(), "source", license_name)
        for raw in ['{"x":1,"x":2}', '{"x":NaN}']:
            with self.assertRaises(ValueError): strict_json(raw)

    def test_road_graph_and_bounded_warnings(self):
        feature = {"type":"Feature","properties":{},"geometry":{"type":"LineString","coordinates":[[10,10],[50,10]]}}
        result = convert({"type":"FeatureCollection","features":[feature]*60}, "roads", "MIT")
        self.assertEqual(len(result.patches), 180)
        self.assertEqual(result.warning_count, 60)
        self.assertEqual(len(result.warnings), 50)
        self.assertEqual(result.patches[2]["after"]["from"], result.patches[0]["id"])

    def test_parent_pipe_eof_stops_helper(self):
        module_path = str(Path(__file__).resolve().parents[1]/"scripts/importers")
        code = "import sys,time;sys.path.insert(0,sys.argv[1]);from geojson import watch_parent_lifetime;watch_parent_lifetime();print('ready',flush=True);time.sleep(60)"
        child = subprocess.Popen([sys.executable,"-B","-u","-c",code,module_path],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            self.assertEqual(child.stdout.readline().strip(),b"ready")
            child.stdin.close()
            self.assertEqual(child.wait(timeout=3),3)
        finally:
            if child.poll() is None: child.kill();child.wait()
            child.stdout.close();child.stderr.close()

    def test_cli_preserves_files(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/"source with spaces.json", Path(directory)/"output.json"
            source.write_text(json.dumps(fixture())); original = source.read_bytes()
            cmd = [sys.executable, str(Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"),str(source),str(output),"--coordinates","local-metres","--license","MIT","--layer-id","a"*32]
            result = subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            before = output.read_bytes()
            self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
            self.assertEqual(output.read_bytes(),before)
            self.assertEqual(source.read_bytes(),original)


if __name__ == "__main__": unittest.main()
