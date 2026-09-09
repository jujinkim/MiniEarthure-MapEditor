import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import overture_area as a
from overture_fixture import QUERY, FEATURE, snapshot, multipart_snapshot
from geojson import convert

class OvertureTests(unittest.TestCase):
    def parse(self,value): return a.parse(json.dumps(value).encode())
    def test_release_area_validation(self):
        for release in ["latest","2026-02-30.0","../release","2026-08-19.0/foo"]:
            with self.assertRaises(ValueError): a.plan(release,QUERY["bbox"])
        for bbox in [[9,55,9,55],[9,55,10,56],[179,0,-179,1],[9,85,9.001,85.001],[True,55,9.001,55.001]]:
            with self.assertRaises(ValueError): a.plan(QUERY["release"],bbox)
    def test_normalization_provenance_estimates(self):
        raw=json.dumps(snapshot()).encode(); value,metadata=a.parse(raw)
        layer=a.finish(convert(value,"synthetic.overture.json",a.LICENSE,source_bytes=raw,coordinates={"mode":"wgs84-utm","origin":[9,55],"local_origin_m":[512,512]}),metadata)
        self.assertEqual(layer.adapter,"overture-buildings-v1")
        self.assertEqual(layer.patches[0]["after"]["height_cm"],1200)
        self.assertEqual(layer.patches[0]["after"]["usage"],"residential")
        self.assertIn("usage",layer.estimates)
        self.assertEqual(layer.coordinates["overture"]["feature_sources"][0]["sources"],FEATURE["properties"]["sources"])
        self.assertIn("base_m",layer.estimates)
        self.assertNotIn("height_m",layer.estimates)
        self.assertEqual(layer.source.bytes,len(raw))
    def test_unsupported_structures_and_geometry(self):
        for key,value in [("has_parts",True),("is_underground",True),("min_height",3),("min_floor",1),("level",2),("height",-1),("sources",[])]:
            obj=snapshot();obj["features"][0]["properties"][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): self.parse(obj)
        for change in ["holes","multipart","z","open","outside"]:
            obj=snapshot();g=obj["features"][0]["geometry"]
            if change=="holes": g["coordinates"][0].append(copy.deepcopy(g["coordinates"][0][0]))
            if change=="multipart": g["coordinates"].append(copy.deepcopy(g["coordinates"][0]))
            if change=="z": g["coordinates"][0][0][1].append(1)
            if change=="open": g["coordinates"][0][0].pop()
            if change=="outside": obj["bbox"]=[10,55,10.001,55.001]
            with self.subTest(change=change),self.assertRaises(ValueError): self.parse(obj)
    def test_identity_license_bounds(self):
        obj=snapshot();obj["features"]*=2
        with self.assertRaises(ValueError): self.parse(obj)
        obj=snapshot();obj["license"]="MIT"
        with self.assertRaises(ValueError): self.parse(obj)
        obj=snapshot();obj["features"][0]["properties"]["id"]="other"
        with self.assertRaises(ValueError): self.parse(obj)
        with patch.object(a,"MAX_POINTS",4),self.assertRaises(ValueError): self.parse(snapshot())
        with self.assertRaises(ValueError): a.parse(b'{"snapshot_version":1,"snapshot_version":1}')
    def test_atomic_snapshot_limits_and_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);part=root/"part";target=root/"source";events=[]
            result=a.acquire(QUERY,part,target,lambda *v:events.append(v),lambda q:[FEATURE])
            original=target.read_bytes()
            self.assertEqual(result["actual_bytes"],len(original));self.parse(json.loads(original))
            self.assertEqual(events[-1],(len(original),a.MAX_INPUT))
            part.unlink()
            with self.assertRaises(FileExistsError): a.acquire(QUERY,part,target,lambda *a:None,lambda q:[FEATURE])
            self.assertEqual(target.read_bytes(),original)
            part.unlink()
            with patch.object(a,"MAX_INPUT",300),self.assertRaises(ValueError): a.acquire(QUERY,part,root/"new",lambda *a:None,lambda q:[FEATURE])
            self.assertFalse((root/"new").exists())
            part.unlink()
            def failed(q):
                yield FEATURE
                raise OSError("provider interrupted")
            with self.assertRaises(OSError): a.acquire(QUERY,part,root/"new",lambda *a:None,failed)
            self.assertFalse((root/"new").exists());self.assertEqual(target.read_bytes(),original)
    def test_real_arrow_wkb_and_stdout_isolation(self):
        import pyarrow as pa
        from shapely.geometry import shape
        import overturemaps.core as core
        props=copy.deepcopy(FEATURE["properties"]);props["geometry"]=shape(FEATURE["geometry"]).wkb
        table=pa.Table.from_pylist([props]);reader=pa.RecordBatchReader.from_batches(table.schema,table.to_batches())
        calls=[]
        def factory(*args,**kwargs):
            print("provider diagnostic")
            calls.append((args,kwargs));return reader
        stdout,stderr=io.StringIO(),io.StringIO()
        with patch.object(core,"record_batch_reader",factory),contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
            for row in a.remote_features(QUERY):
                print("caller IPC")
                self.assertEqual(row["properties"]["sources"],props["sources"])
        self.assertEqual(stdout.getvalue(),"caller IPC\n")
        self.assertIn("provider diagnostic",stderr.getvalue())
        self.assertEqual(calls[0][1]["release"],QUERY["release"])
        self.assertTrue(calls[0][1]["stac"])
        self.assertEqual(calls[0][1]["bbox"],QUERY["bbox"])
    def layer(self, obj):
        raw = json.dumps(obj).encode()
        value, metadata = a.parse(raw)
        return a.finish(convert(value,"synthetic.overture.json",a.LICENSE,layer_id="a"*32,source_bytes=raw,
            coordinates={"mode":"wgs84-utm","origin":[9,55],"local_origin_m":[512,512]}),metadata)
    def test_multipart_courtyard_mapping_preservation(self):
        obj = multipart_snapshot(); original = copy.deepcopy(obj)
        layer = self.layer(obj)
        self.assertEqual(obj, original)
        self.assertEqual(layer.feature_count, 1)
        self.assertEqual(len(layer.patches), 3)
        self.assertEqual(len(layer.patches[0]["after"]["holes"]), 1)
        self.assertNotIn("holes", layer.patches[1]["after"])
        meta = layer.coordinates["overture"]["feature_sources"][0]
        self.assertEqual(meta["building_ids"], [p["id"] for p in layer.patches])
        self.assertEqual(meta["id"], FEATURE["id"])
        self.assertEqual(meta["sources"], FEATURE["properties"]["sources"])
        self.assertEqual(meta["footprint_count"], 3)
        self.assertIn("courtyard_usage", layer.estimates)
        self.assertEqual(layer.patches, self.layer(obj).patches)
        polygon = snapshot(); polygon["features"][0]["geometry"] = dict(type="Polygon", coordinates=FEATURE["geometry"]["coordinates"][0])
        self.assertEqual(self.layer(polygon).patches, self.layer(snapshot()).patches)
    def test_multipart_invalid_whole_source_and_budgets(self):
        for change in ["overlap", "wrong_owner", "touch", "nested", "empty", "parts", "holes", "z"]:
            obj = multipart_snapshot(); polys = obj["features"][0]["geometry"]["coordinates"]
            if change == "overlap": polys.append(copy.deepcopy(polys[0]))
            if change == "wrong_owner": polys[1].append(polys[0].pop())
            if change == "touch": polys[0][1][0] = polys[0][0][0]; polys[0][1][-1] = polys[0][0][0]
            if change == "nested": polys[0].append(polys.pop(1)[0])
            if change == "empty": polys.append([])
            if change == "parts": polys[:] = polys * 86
            if change == "holes": polys[0] += polys[0][1:] * 16
            if change == "z": polys[-1][0][1].append(2)
            with self.subTest(change=change), self.assertRaises(ValueError): self.layer(obj)
        with patch.object(a,"MAX_POINTS",19), self.assertRaisesRegex(ValueError,"point budget"): self.layer(multipart_snapshot())
        with patch("polygon_geometry.MAX_TOPOLOGY_CHECKS",2), self.assertRaisesRegex(ValueError,"topology budget"): self.layer(multipart_snapshot())
    def test_multipart_arrow_wkb_snapshot_roundtrip(self):
        import pyarrow as pa
        from shapely.geometry import shape
        import overturemaps.core as core
        obj = multipart_snapshot(); feature = obj["features"][0]
        props = copy.deepcopy(feature["properties"]); props["geometry"] = shape(feature["geometry"]).wkb
        table = pa.Table.from_pylist([props])
        reader = pa.RecordBatchReader.from_batches(table.schema,table.to_batches())
        with tempfile.TemporaryDirectory() as folder, patch.object(core,"record_batch_reader",return_value=reader):
            root = Path(folder)
            a.acquire(QUERY,root/"partial",root/"source",lambda *args:None)
            captured = json.loads((root/"source").read_bytes())
            self.assertEqual(captured["features"][0],feature)
            self.assertEqual(len(self.layer(captured).patches),3)
    def test_missing_dependency(self):
        with patch.object(a,"version",return_value="other"),self.assertRaisesRegex(ValueError,"requirements-import"):
            list(a.remote_features(QUERY))

if __name__=="__main__": unittest.main()
