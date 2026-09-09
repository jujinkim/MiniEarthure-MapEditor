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
from overture_fixture import QUERY, FEATURE, snapshot
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
    def test_missing_dependency(self):
        with patch.object(a,"version",return_value="other"),self.assertRaisesRegex(ValueError,"requirements-import"):
            list(a.remote_features(QUERY))

if __name__=="__main__": unittest.main()
