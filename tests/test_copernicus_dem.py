import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import copernicus_dem as dem
from dem_fixture import create


def options(source=""):
    return dict(coordinates=dict(mode="wgs84-utm",origin=[9.5,55.5],local_origin_m=[0,0]),cell=[0,0],cell_count=[1,1],cell_size_cm=51200,map_min_cm=[0,0],spacing_cm=3200,vertical_zero_m=0,source=str(source))


class DemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.source = Path(cls.folder.name)/"synthetic.tif"
        create(cls.source)
    @classmethod
    def tearDownClass(cls): cls.folder.cleanup()

    def test_current_single_source_contract_bilinear_axes_and_units(self):
        original = dem.identity(self.source)
        raw = options(self.source)
        scaled = dict(raw, cell_size_cm=6400, spacing_cm=400, osm_denominator=8)
        self.assertEqual(dem.mosaic_grid(raw)[3], dem.mosaic_grid(scaled)[3])
        p = dem.plan(raw)
        self.assertEqual(p["adapter"], "copernicus-dem-v1")
        self.assertEqual((len(p["sources"]),p["cells"]), (1,[[0,0]]))
        heights, meta = dem.mosaic_heights([self.source],p,lambda *a:None)
        compact, compact_meta = dem.mosaic_heights([self.source],dem.plan(scaled),lambda *a:None)
        self.assertEqual(meta["source_windows"],compact_meta["source_windows"])
        for actual,(lon,lat) in zip(heights[0].flat,dem.mosaic_grid(raw)[3][0]):
            self.assertLessEqual(abs(actual-round((100+(lon-9)*100+(lat-55)*200)*100)),1)
        self.assertGreater(heights[0][0,1],heights[0][0,0])
        self.assertGreater(heights[0][1,0],heights[0][0,0])
        self.assertLessEqual(abs(meta['offset_cm']/8-compact_meta['offset_cm']),1)
        _, shifted = dem.mosaic_heights([self.source],dem.plan(dict(raw,vertical_zero_m=250)),lambda *a:None)
        self.assertEqual(meta['offset_cm']-shifted['offset_cm'],25000)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            result=dem.execute(dict(mode="dem",plan=json.loads(json.dumps(p),parse_int=float),destination=str(d/"capture")),d,lambda *a:None)
            output=result["outputs"][0]
            self.assertEqual(output["png_sha256"],hashlib.sha256(Path(output["png_path"]).read_bytes()).hexdigest())
            self.assertTrue(Path(output["png_path"]).read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(dem.identity(self.source),original)

    def test_grid_and_removed_formats_fail_closed(self):
        base=options(self.source)
        for key,value in [("spacing_cm",3000),("spacing_cm",True),("cell",[-1,0]),("cell_size_cm",204800),("vertical_zero_m",float("nan")),("allow_download",True),("fallback90",False),("osm_denominator",2)]:
            with self.subTest(key=key),self.assertRaises(ValueError): dem.plan(dict(base,**{key:value}))
        missing=dict(base);del missing["cell_count"]
        with self.assertRaises((KeyError,ValueError)):dem.plan(missing)
        crossing=copy.deepcopy(base);crossing["coordinates"]["origin"]=[9.999,55.5]
        with self.assertRaisesRegex(ValueError,"multiple source"):dem.plan(crossing)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            for changed in [dict(dem.plan(base),adapter="copernicus-dem-v2"),dict(dem.plan(base),checked_at=0)]:
                with self.assertRaises(ValueError):dem.execute(dict(mode="dem",plan=changed,destination=str(d/"absent")),d,lambda *a:None)
            self.assertEqual(list(d.iterdir()),[])

    def test_bad_rasters_no_fill_and_dependency_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder);bad=d/"bad.tif"
            for kwargs in [dict(nodata=True),dict(crs="EPSG:3857"),dict(shift=0.1),dict(bias=20000)]:
                create(bad,**kwargs)
                with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):dem.mosaic_heights([bad],dem.plan(options(bad)),lambda *a:None)
            with patch.object(dem,"raster_dependencies",side_effect=ValueError("install requirements-import.txt")),self.assertRaisesRegex(ValueError,"install requirements"):
                dem.execute(dict(mode="dem",plan=dem.plan(options(self.source)),destination=str(d/"absent")),d,lambda *a:None)
            self.assertFalse((d/"absent.source-0.tif").exists())

    def test_capture_change_collision_cancellation_and_failure_preserve_sources(self):
        review=dem.plan(options(self.source));source=review["sources"][0];original=dem.identity(self.source)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            captured=dem.capture(source,d/"part",d/"copy.tif",lambda *a:None)
            self.assertEqual(dem.identity(d/"copy.tif"),original)
            with self.assertRaises(FileExistsError):dem.capture(source,d/"part2",d/"copy.tif",lambda *a:None)
            changed=copy.deepcopy(source);changed["source"]["sha256"]="0"*64
            with self.assertRaises(ValueError):dem.capture(changed,d/"badpart",d/"missing",lambda *a:None)
            self.assertFalse((d/"missing").exists())
            def cancel(c,t):
                if c:raise RuntimeError("cancel")
            with self.assertRaises(RuntimeError):dem.capture(source,d/"cancelpart",d/"cancelled",cancel)
            self.assertFalse((d/"cancelled").exists())
            with patch.object(dem,"mosaic_heights",side_effect=ValueError("missing support")),self.assertRaises(ValueError):
                dem.execute(dict(mode="dem",plan=review,destination=str(d/"captured")),d,lambda *a:None)
            self.assertTrue((d/"captured.source-0.tif").exists())
            self.assertFalse(list(d.glob("*.png")))
        self.assertEqual(dem.identity(self.source),original)
        with patch.object(dem,"MAX_SOURCE",original["bytes"]-1),self.assertRaises(ValueError):dem.plan(options(self.source))


class MosaicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.sources=Path(cls.folder.name)
        for tile in [(9,55),(10,55),(9,54),(10,54)]:
            create(cls.sources/dem.tile_filename(tile),tile=tile)
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
            with self.assertRaises(ValueError): dem.plan(dict(self.opts(),source=folder))
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

    def test_local_mixed_resolution_sampling_and_nodata(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            o = self.opts()
            o["coordinates"]["origin"] = [9.99999,55.00001]
            review = dem.plan(o)
            paths = []
            for item in review["sources"]:
                tile = tuple(item["tile"])
                resolution = 90 if tile == (10,55) else 30
                path = d/dem.tile_filename(tile, resolution)
                create(path, tile=tile, resolution=resolution)
                item.update(resolution_m=resolution, fallback90=resolution==90)
                paths.append(path)
            review["options"] = dict(o)
            original_review = copy.deepcopy(review)
            heights, _ = dem.mosaic_heights(paths, review, lambda *a: None)
            self.assertEqual(review, original_review)
            for group, points in zip(heights, dem.mosaic_grid(o)[3]):
                for actual, (lon,lat) in zip(group.flat,points):
                    self.assertLessEqual(abs(actual-round((100+(lon-9)*100+(lat-55)*200)*100)),1)
            create(paths[0], tile=tuple(review["sources"][0]["tile"]), nodata=True)
            with self.assertRaisesRegex(ValueError,"Missing/non-finite"):
                dem.mosaic_heights(paths, review, lambda *a: None)

    def test_missing_support_rejects_after_capture(self):
        p=dem.plan(self.opts())
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            with patch.object(dem,"mosaic_heights",side_effect=ValueError("missing support")),self.assertRaises(ValueError):
                dem.execute(dict(mode="dem",plan=p,destination=str(d/"capture")),d,lambda *a:None)
            self.assertEqual(len(list(d.glob("*.tif"))),4)
            self.assertFalse(list(d.glob("*.png")))


if __name__ == "__main__": unittest.main()
