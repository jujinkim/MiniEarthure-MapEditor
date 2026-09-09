import copy
from email.message import Message
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import copernicus_dem as dem
from dem_fixture import create


def options(source=""):
    return dict(coordinates=dict(mode="wgs84-utm",origin=[9.5,55.5],local_origin_m=[0,0]),cell=[0,0],cell_size_cm=51200,map_min_cm=[0,0],spacing_cm=3200,vertical_zero_m=0,source=str(source),allow_download=False,fallback90=False)


class Response(io.BytesIO):
    def __init__(self, url, body=b"abc", size=None, etag='"fixture"', status=200):
        super().__init__(body)
        self.url, self.status = url,status
        self.headers = Message()
        self.headers["Content-Length"] = str(len(body) if size is None else size)
        self.headers["ETag"] = etag
    def geturl(self): return self.url


class DemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.source = Path(cls.folder.name)/"synthetic.tif"
        create(cls.source)
    @classmethod
    def tearDownClass(cls): cls.folder.cleanup()

    def test_grid_and_profile_rejections(self):
        o=options(self.source)
        c,side,points,tile,zero=dem.grid(o)
        self.assertEqual((side,tile,zero),(17,[9,55],0))
        self.assertGreater(points[1][0],points[0][0])
        self.assertGreater(points[17][1],points[0][1])
        for key,value in [("spacing_cm",3000),("spacing_cm",True),("cell",[-1,0]),("cell_size_cm",204800),("vertical_zero_m",float("nan")),("allow_download",1)]:
            with self.subTest(key=key), self.assertRaises(ValueError): dem.grid(dict(o,**{key:value}))
        for origin in [[9.999,55.5],[179.999,55.5],[9.5,-0.001]]:
            bad=copy.deepcopy(o);bad["coordinates"]["origin"]=origin
            with self.assertRaises(ValueError): dem.grid(bad)
        bad=copy.deepcopy(o);bad["coordinates"]["local_origin_m"]=[-20001,0]
        with self.assertRaises(ValueError): dem.grid(bad)

    def test_no_implicit_network_and_404_only_fallback(self):
        with self.assertRaisesRegex(ValueError,"explicitly allow"): dem.plan(options())
        calls=[]
        def opener(url,method,headers=None):
            calls.append((url,method))
            if "30m" in url: raise HTTPError(url,404,"absent",{},None)
            return Response(url)
        o=dict(options(),allow_download=True,fallback90=True)
        p=dem.plan(o,opener)
        self.assertEqual(p["resolution_m"],90);self.assertTrue(p["fallback90"])
        self.assertEqual([c[1] for c in calls],["HEAD","HEAD"])
        for code in [403,429,500]:
            with self.assertRaises(ValueError),patch.object(dem,"open_remote"):
                dem.plan(o,lambda *a: (_ for _ in ()).throw(HTTPError(a[0],code,"failure",{},None)))
        self.assertIn("_30_S01_00_W001_00_DEM",dem.tile_url([-1,-1],90))

    def test_http_framing_and_size_guards(self):
        url=dem.tile_url([9,55],30)
        for response in [Response(url,size=dem.MAX_SOURCE+1),Response(url,etag='W/"weak"'),Response(url,status=206),Response(url,size=0)]:
            with self.assertRaises(ValueError): dem.headers(response,url)
        r=Response(url);r.headers["Content-Length"]="3"
        with self.assertRaises(ValueError): dem.headers(r,url)
        r=Response(url);r.headers["Transfer-Encoding"]="chunked"
        with self.assertRaises(ValueError): dem.headers(r,url)

    def test_full_resolution_bilinear_axes_vertical_png(self):
        p=dem.plan(options(self.source))
        png,meta=dem.sample(self.source,p,lambda *a:None)
        self.assertIsNone(meta["source_accuracy_cm"])
        import numpy as np
        length=struct.unpack(">I",png[33:37])[0]
        raw=zlib.decompress(png[41:41+length])
        rows=[raw[i*35+1:(i+1)*35] for i in range(17)]
        values=np.frombuffer(b"".join(rows),dtype=">u2").reshape(17,17).astype(float)*meta["step_cm"]+meta["offset_cm"]
        points=dem.grid(p["options"])[2]
        for i,(lon,lat) in enumerate(points):
            expected=round((100+(lon-9)*100+(lat-55)*200)*100)
            self.assertLessEqual(abs(values.flat[i]-expected),1)
        self.assertGreater(values[0,1],values[0,0]);self.assertGreater(values[1,0],values[0,0])
        o=dict(p["options"],vertical_zero_m=250)
        png2,meta2=dem.sample(self.source,dem.plan(o),lambda *a:None)
        self.assertEqual(meta["offset_cm"]-meta2["offset_cm"],25000)
        self.assertEqual(meta["source_window"],meta2["source_window"])

    def test_bad_rasters_and_edge_reject_no_fill(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"bad.tif"
            for kwargs in [dict(nodata=True),dict(crs="EPSG:3857"),dict(shift=0.1),dict(bias=20000)]:
                create(path,**kwargs)
                with self.subTest(kwargs=kwargs),self.assertRaises(ValueError): dem.sample(path,dem.plan(options(path)),lambda *a:None)
            o=options(self.source);o["coordinates"]["origin"]=[9.5,55.0002]
            with self.assertRaisesRegex(ValueError,"support crosses"): dem.sample(self.source,dem.plan(o),lambda *a:None)

    def test_capture_preserves_original_and_rejects_changes_collisions(self):
        p=dem.plan(options(self.source));original=dem.identity(self.source)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);events=[]
            captured=dem.capture(p,d/"partial",d/"copy.tif",lambda c,t:events.append((c,t)))
            self.assertEqual(dem.identity(d/"copy.tif"),original)
            self.assertEqual(captured["sha256"],original["sha256"])
            self.assertEqual(events[-1],(original["bytes"],original["bytes"]))
            with self.assertRaises(FileExistsError): dem.capture(p,d/"otherpart",d/"copy.tif",lambda *a:None)
            bad=copy.deepcopy(p);bad["source"]["sha256"]="0"*64
            with self.assertRaises(ValueError): dem.capture(bad,d/"badpart",d/"missing.tif",lambda *a:None)
            self.assertFalse((d/"missing.tif").exists())
            self.assertEqual(dem.identity(self.source),original)

    def test_conditional_remote_capture_truncation_and_cancellation(self):
        url=dem.tile_url([9,55],30)
        p=dem.plan(dict(options(),allow_download=True),lambda u,m:Response(u))
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            def opened(u,m,h):
                self.assertEqual((u,m,h),(url,"GET",{"If-Match":'"fixture"'}));return Response(u)
            dem.capture(p,d/"part",d/"complete.tif",lambda *a:None,opened)
            for i,body in enumerate([b"a",b"abcd"]):
                with self.assertRaises(ValueError): dem.capture(p,d/f"part{i}",d/f"absent{i}",lambda *a:None,lambda u,m,h:Response(u,body,size=3))
                self.assertFalse((d/f"absent{i}").exists())
            def cancel(c,t):
                if c: raise RuntimeError("cancel")
            with self.assertRaises(RuntimeError): dem.capture(p,d/"cancelpart",d/"cancelled",cancel,opened)
            self.assertFalse((d/"cancelled").exists());self.assertEqual((d/"complete.tif").read_bytes(),b"abc")

    def test_execute_provenance_stale_dependencies_failure_preservation(self):
        p=dem.plan(options(self.source))
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);events=[]
            roundtrip=json.loads(json.dumps(p),parse_int=float)
            result=dem.execute(dict(mode="dem",plan=roundtrip,destination=str(d/"capture.tif")),d,lambda *a:events.append(a))
            self.assertEqual(result["review"]["release"],"2021")
            self.assertEqual(result["png_sha256"],hashlib.sha256(Path(result["png_path"]).read_bytes()).hexdigest())
            self.assertEqual([e[0] for e in events if e[1]==0],["acquire","sample"])
            self.assertEqual(json.loads((d/"capture.tif.json").read_text())["source"]["sha256"],p["source"]["sha256"])
            for changed in [dict(p,checked_at=0),dict(p,vertical_crs="ellipsoid")]:
                with self.assertRaises(ValueError): dem.execute(dict(mode="dem",plan=changed,destination=str(d/"new")),d,lambda *a:None)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            with patch.object(dem,"sample",side_effect=ValueError("missing terrain")),self.assertRaises(ValueError):
                dem.execute(dict(mode="dem",plan=p,destination=str(d/"capture.tif")),d,lambda *a:None)
            self.assertTrue((d/"capture.tif").exists());self.assertTrue((d/"capture.tif.json").exists())
            self.assertFalse((d/"capture.tif.png").exists())

    def test_glo90_remote_decode_and_missing_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);source=d/"synthetic90.tif"
            create(source,resolution=90)
            raw=source.read_bytes();methods=[]
            def opener(url,method,headers=None):
                methods.append(method)
                if "30m" in url: raise HTTPError(url,404,"missing",{},None)
                return Response(url,raw)
            p=dem.plan(dict(options(),allow_download=True,fallback90=True),opener)
            with patch.object(dem,"raster_dependencies",side_effect=ValueError("install requirements-import.txt")),self.assertRaisesRegex(ValueError,"install requirements"):
                dem.execute(dict(mode="dem",plan=p,destination=str(d/"not-downloaded")),d,lambda *a:None,opener)
            self.assertNotIn("GET",methods)
            result=dem.execute(dict(mode="dem",plan=p,destination=str(d/"captured")),d,lambda *a:None,opener)
            self.assertEqual(result["review"]["resolution_m"],90)
            self.assertTrue(result["review"]["fallback90"])
            self.assertEqual(result["review"]["source"]["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertTrue(Path(result["png_path"]).exists())


class MosaicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.sources=Path(cls.folder.name)
        for tile in [(9,55),(10,55),(9,54),(10,54)]:
            create(cls.sources/dem.tile_url(tile,30).split("/")[-1],tile=tile)
    @classmethod
    def tearDownClass(cls): cls.folder.cleanup()
    def opts(self):
        o=dict(options(self.sources),cell_count=[2,2])
        o["coordinates"]["origin"]=[9.997,54.997]
        return o
    def test_four_source_mosaic_reference_shared_edges(self):
        o=self.opts();p=dem.plan(o)
        self.assertEqual(len(p["sources"]),4)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);events=[]
            r=dem.execute(dict(mode="dem",plan=p,destination=str(d/"capture")),d,lambda *a:events.append(a))
            import numpy as np
            grids=[]
            for output,points in zip(r["outputs"],dem.mosaic_grid(o)[3]):
                png=Path(output["png_path"]).read_bytes();length=struct.unpack(">I",png[33:37])[0]
                raw=zlib.decompress(png[41:41+length]);side=p["side"];stride=side*2+1
                a=np.frombuffer(b"".join(raw[i*stride+1:(i+1)*stride] for i in range(side)),dtype=">u2").reshape(side,side).astype(float)*r["raster"]["step_cm"]+r["raster"]["offset_cm"]
                for actual,(lon,lat) in zip(a.flat,points): self.assertLessEqual(abs(actual-round((100+(lon-9)*100+(lat-55)*200)*100)),1)
                grids.append(a)
            np.testing.assert_array_equal(grids[0][:,-1],grids[1][:,0])
            np.testing.assert_array_equal(grids[0][-1,:],grids[2][0,:])
            self.assertEqual(len(r["review"]["sources"]),4)
            self.assertEqual(events[-1],("sample",4*17*17,4*17*17))
            self.assertTrue(all(Path(s["source"]["captured_path"]).is_file() for s in r["review"]["sources"]))
    def test_limits_missing_source_and_stale_plan(self):
        for counts in [[0,1],[5,1],[True,1],[4,4]]:
            o=dict(self.opts(),cell_count=counts,cell_size_cm=102400,spacing_cm=200)
            with self.assertRaises(ValueError): dem.plan(o)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError): dem.plan(dict(self.opts(),source=folder))
            p=dem.plan(self.opts());p["sources"][0]["source"]["sha256"]="0"*64
            with self.assertRaisesRegex(ValueError,"changed"):
                dem.execute(dict(mode="dem",plan=p,destination=folder+"/capture"),Path(folder),lambda *a:None)
            self.assertEqual(list(Path(folder).iterdir()),[])
    def test_cancel_preserves_completed_sources_and_no_png(self):
        p=dem.plan(self.opts())
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);first=p["sources"][0]["source"]["bytes"]
            def cancel(stage,c,t):
                if stage=="acquire" and c>first: raise RuntimeError("cancel")
            with self.assertRaisesRegex(RuntimeError,"cancel"):
                dem.execute(dict(mode="dem",plan=p,destination=str(d/"capture")),d,cancel)
            self.assertTrue((d/"capture.source-0.tif").exists())
            self.assertFalse(list(d.glob("*.png")))
    def test_mixed_glo90_fallback_and_nodata(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);raws={}
            for tile in [(9,55),(10,55),(9,54),(10,54)]:
                resolution=90 if tile==(10,55) else 30
                path=d/(str(tile)+".tif");create(path,resolution=resolution,tile=tile)
                raws[dem.tile_url(tile,resolution)]=path.read_bytes()
            def opener(url,method,headers=None):
                if url not in raws: raise HTTPError(url,404,"absent",{},None)
                return Response(url,raws[url])
            o=dict(self.opts(),source="",allow_download=True,fallback90=True)
            o["coordinates"]["origin"]=[9.99999,55.00001]
            p=dem.plan(o,opener)
            self.assertEqual(sum(s["fallback90"] for s in p["sources"]),1)
            r=dem.execute(dict(mode="dem",plan=p,destination=str(d/"captured")),d,lambda *a:None,opener)
            self.assertEqual(len(r["outputs"]),4)
            paths=[Path(s["source"]["captured_path"]) for s in r["review"]["sources"]]
            heights,meta=dem.mosaic_heights(paths,p,lambda *a:None)
            for group,points in zip(heights,dem.mosaic_grid(o)[3]):
                for actual,(lon,lat) in zip(group.flat,points): self.assertLessEqual(abs(actual-round((100+(lon-9)*100+(lat-55)*200)*100)),1)
            create(paths[0],tile=tuple(p["sources"][0]["tile"]),nodata=True)
            with self.assertRaisesRegex(ValueError,"Missing/non-finite"):
                dem.mosaic_heights(paths,p,lambda *a:None)

    def test_missing_support_rejects_after_capture(self):
        p=dem.plan(self.opts())
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            with patch.object(dem,"mosaic_heights",side_effect=ValueError("missing support")),self.assertRaises(ValueError):
                dem.execute(dict(mode="dem",plan=p,destination=str(d/"capture")),d,lambda *a:None)
            self.assertEqual(len(list(d.glob("*.tif"))),4)
            self.assertFalse(list(d.glob("*.png")))


if __name__ == "__main__": unittest.main()
