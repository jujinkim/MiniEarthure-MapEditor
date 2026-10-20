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
import import_layer
from dem_fixture import create


def codes():
    return {entry["code"] for entry in import_layer.limit_entries()}

# Support windows of the synthetic four-tile mosaic, identical before the shared-read change.
WINDOWS_CORNER="6e52f8a93531b9f90be1d8af41ff25f314fa06df4097d089f350c2f1be628822"
WINDOWS_EDGE="cb81dadb2018ecdbf536d9a44db25586c9162682abcffaeb41c567b504b67954"


def options(source=""):
    return dict(coordinates=dict(mode="wgs84-utm",origin=[9.5,55.5],local_origin_m=[0,0]),cell=[0,0],cell_count=[1,1],cell_size_cm=51200,map_min_cm=[0,0],spacing_cm=3200,vertical_zero_m=0,source=str(source))


class DemTests(unittest.TestCase):
    def setUp(self):
        import_layer.reset_limits()
        self.addCleanup(import_layer.reset_limits)

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
        for key,value in [("spacing_cm",3000),("spacing_cm",True),("cell",[-1,0]),("cell_size_cm",204800),("vertical_zero_m",float("nan")),("allow_download",True),("fallback90",False),
                          ("osm_denominator",0),("osm_denominator",9),("osm_denominator",2.5),("osm_denominator",True),("osm_denominator",float("inf")),("osm_denominator","3")]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError): dem.plan(dict(base,**{key:value}))
        # Any adopted OSM scale 1:D, D an integer 1..8, sent as an int or a float.
        single=dict(base);del single["cell_count"]
        for value in (1, 2, 3.0, 8, 8.0):
            with self.subTest(denominator=value):
                self.assertEqual(dem.grid(dict(single,cell_size_cm=6400,spacing_cm=400,osm_denominator=value))[1],17)
        missing=dict(base);del missing["cell_count"]
        with self.assertRaises((KeyError,ValueError)):dem.plan(missing)
        crossing=copy.deepcopy(base);crossing["coordinates"]["origin"]=[9.999,55.5]
        with self.assertRaisesRegex(ValueError,"multiple source"):dem.plan(crossing)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            import time
            for changed in [dict(dem.plan(base),adapter="copernicus-dem-v2"),dict(dem.plan(base),checked_at=int(time.time())+3600)]:
                with self.assertRaises(ValueError):dem.execute(dict(mode="dem",plan=changed,destination=str(d/"absent")),d,lambda *a:None)
            self.assertEqual(list(d.iterdir()),[])
            self.assertNotIn("dem_review_age",codes())
            # An old review is re-planned and hash-checked; its age only warns.
            result=dem.execute(dict(mode="dem",plan=dict(dem.plan(base),checked_at=0),destination=str(d/"old")),d,lambda *a:None)
            self.assertEqual(len(result["outputs"]),1)
            self.assertIn("dem_review_age",codes())

    def test_city_grid_keeps_sample_source_and_cell_budgets(self):
        raw = dict(options(self.source), cell_count=[8,12], cell_size_cm=12800,
                   spacing_cm=400, osm_denominator=8)
        p = dem.plan(raw)
        self.assertEqual((len(p['cells']), p['side']), (96,33))
        self.assertEqual(p['cells'][-1], [7,11])
        self.assertEqual(len(p['sources']), 1)
        # Count is independent of aspect ratio, but never unbounded.
        for counts in [[16,16],[256,1],[1,256]]:
            grid=dem.mosaic_grid(dict(options(self.source),cell_count=counts,
                                      cell_size_cm=200,spacing_cm=200))
            self.assertEqual(len(grid[2]),256)
        self.assertEqual(import_layer.limit_entries(),[])
        # Above the former 256 cells and 1025² samples a mosaic warns; the
        # raised ceilings (1024 cells, 4096² samples) still refuse.
        small=dict(options(self.source),cell_size_cm=200,spacing_cm=200)
        self.assertEqual(len(dem.mosaic_grid(dict(small,cell_count=[17,16]))[2]),272)
        self.assertIn("dem_cells",codes())
        for counts in [[33,32],[1025,1],[1,1025],[True,1]]:
            with self.subTest(counts=counts),self.assertRaises(ValueError):
                dem.mosaic_grid(dict(small,cell_count=counts))
        dem.mosaic_grid(dict(options(self.source),cell_count=[4,4],spacing_cm=200))
        self.assertIn("dem_samples",codes())
        with self.assertRaisesRegex(ValueError,'4096² samples'):
            dem.mosaic_grid(dict(options(self.source),cell_count=[16,16],spacing_cm=200))
        original = dem.identity(self.source)
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            result=dem.execute(dict(mode='dem',plan=p,destination=str(d/'city')),d,lambda *a:None)
            self.assertEqual(len(result['outputs']),96)
            self.assertEqual(result['outputs'][-1]['cell'],[7,11])
        self.assertEqual(dem.identity(self.source),original)

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
        with patch.object(dem,"SOURCE_CEILING",original["bytes"]-1),self.assertRaises(ValueError):dem.plan(options(self.source))
        self.assertNotIn("dem_source_bytes",codes())
        with patch.object(dem,"MAX_SOURCE",original["bytes"]-1):dem.plan(options(self.source))
        self.assertIn("dem_source_bytes",codes())

    def test_decode_budget_counts_touched_blocks_before_hashing(self):
        cost=dem.plan(options(self.source))["sources"][0]["source"]["decode"]
        self.assertEqual((cost["block"],cost["blocks"],cost["decoded_bytes"]),([1024,1024],1,4*1024*1024))
        self.assertGreater(cost["compressed_bytes"],0)
        with patch.object(dem,"DECODE_CEILING",cost["decoded_bytes"]-1),patch.object(dem,"identity",side_effect=AssertionError("hashed before the decode ceiling")):
            with self.assertRaisesRegex(ValueError,"decode exceeds.*flat terrain"):dem.plan(options(self.source))
        with patch.object(dem,"MAX_DECODE",cost["decoded_bytes"]):dem.plan(options(self.source))
        self.assertNotIn("dem_decode_bytes",codes())
        with patch.object(dem,"MAX_DECODE",cost["decoded_bytes"]-1):dem.plan(options(self.source))
        self.assertIn("dem_decode_bytes",codes())
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            changed=dem.plan(options(self.source));changed["sources"][0]["source"]["decode"]["blocks"]=2
            with self.assertRaisesRegex(ValueError,"review again"):dem.execute(dict(mode="dem",plan=changed,destination=str(d/"tampered")),d,lambda *a:None)
            self.assertEqual(list(d.iterdir()),[])
            with patch.object(dem,"captured_cost",return_value=[dict(cost,blocks=2)]),self.assertRaisesRegex(ValueError,"decode plan changed"):
                dem.execute(dict(mode="dem",plan=dem.plan(options(self.source)),destination=str(d/"recheck")),d,lambda *a:None)
            self.assertFalse(list(d.glob("*.png")))

    def test_review_errors_stay_bounded_without_raster_stack(self):
        with tempfile.TemporaryDirectory() as folder:
            empty=Path(folder)/"empty.tif";empty.write_bytes(b"")
            with self.assertRaisesRegex(ValueError,"^Empty DEM$"):dem.plan(options(empty))
            junk=Path(folder)/"junk.tif";junk.write_bytes(b"not a tiff")
            with self.assertRaises(ValueError) as caught:dem.plan(options(junk))
            self.assertNotIn(folder,str(caught.exception))
        with patch.dict(sys.modules,{"numpy":None}),patch.object(dem,"raster_dependencies",side_effect=ValueError("DEM needs rasterio 1.4.4")):
            with self.assertRaisesRegex(ValueError,"DEM needs rasterio"):dem.plan(options(self.source))

    def test_array_grid_matches_scalar_projection_and_keeps_guard_errors(self):
        from pyproj.enums import TransformDirection
        cell=options(self.source);del cell["cell_count"]
        for raw in [cell,dict(cell,cell=[7,11],cell_size_cm=12800,spacing_cm=400,osm_denominator=8),dict(cell,cell=[7,11],cell_size_cm=12800,spacing_cm=400,osm_denominator=3.0),
                    dict(cell,coordinates=dict(mode="wgs84-utm",origin=[-70.5,-33.4],local_origin_m=[100.5,-3.25]),cell=[3,2],cell_size_cm=6400,spacing_cm=200)]:
            coordinates,side,points,_,_=dem.grid(raw)
            size,spacing,denominator=raw["cell_size_cm"],raw["spacing_cm"],raw.get("osm_denominator",1)
            reference=[]
            for row in range(side):
                for col in range(side):
                    local=[(raw["map_min_cm"][i]+raw["cell"][i]*size+(col if i==0 else row)*spacing)/100 for i in range(2)]
                    dx,dy=[local[i]*denominator-coordinates.local[i] for i in range(2)]
                    reference.append(coordinates.transformer.transform(coordinates.origin_xy[0]+dx,coordinates.origin_xy[1]+dy,direction=TransformDirection.INVERSE,errcheck=True))
            self.assertIsNotNone(dem._grid_points(raw,coordinates,denominator,size,spacing,side))
            self.assertEqual(points,reference)
        # Near a guard the scalar loop runs and reports its own first error.
        for edge,message in [([39,0],"source exceeds 20 km"),([40,0],"DEM exceeds 20 km"),([0,39],"DEM exceeds 20 km")]:
            with self.subTest(edge=edge),self.assertRaisesRegex(ValueError,message):dem.grid(dict(cell,cell=edge))
        fast=dem.grid(cell)[2]
        with patch.object(dem,"_grid_points",return_value=None):self.assertEqual(dem.grid(cell)[2],fast)


class MosaicTests(unittest.TestCase):
    def setUp(self):
        import_layer.reset_limits()
        self.addCleanup(import_layer.reset_limits)

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
    def test_combined_tiles_beyond_one_tile_limit_and_single_grid_pass(self):
        largest=max(s["source"]["bytes"] for s in dem.plan(self.opts())["sources"])
        with patch.object(dem,"MAX_SOURCE",largest):
            p=dem.plan(self.opts())
            self.assertGreater(sum(s["source"]["bytes"] for s in p["sources"]),dem.MAX_SOURCE)
            with tempfile.TemporaryDirectory() as folder,patch.object(dem,"mosaic_grid",wraps=dem.mosaic_grid) as grids:
                d=Path(folder)
                r=dem.execute(dict(mode="dem",plan=p,destination=str(d/"capture")),d,lambda *a:None)
                self.assertEqual(grids.call_count,1)
                self.assertEqual(len(r["outputs"]),4)
        with patch.object(dem,"SOURCE_CEILING",largest-1),self.assertRaisesRegex(ValueError,"exceeds 256 MiB"):dem.plan(self.opts())
        self.assertNotIn("dem_source_bytes",codes())
        with patch.object(dem,"MAX_SOURCE",largest-1):dem.plan(self.opts())
        self.assertIn("dem_source_bytes",codes())

    def test_four_source_outputs_and_windows_are_unchanged(self):
        from rasterio.io import DatasetReader
        original=DatasetReader.read
        for origin,pngs,windows in [([9.997,54.997],"4ca30924babfc681cea3db98b76d1648fcefc4b6e643979d7f03dd58bb22adde",WINDOWS_CORNER),
                                          ([9.99999,55.00001],"f2b6901d3932977c51346ce5035d49ff58f56fe8b3883059fa8f005706eb344d",WINDOWS_EDGE)]:
            o=self.opts();o["coordinates"]["origin"]=origin
            reads=[]
            def counted(dataset,*args,**kwargs):
                reads.append(args)
                return original(dataset,*args,**kwargs)
            with tempfile.TemporaryDirectory() as folder,patch.object(DatasetReader,"read",counted):
                d=Path(folder)
                r=dem.execute(dict(mode="dem",plan=dem.plan(o),destination=str(d/"capture")),d,lambda *a:None)
                digests="".join(hashlib.sha256(Path(output["png_path"]).read_bytes()).hexdigest() for output in r["outputs"])
                self.assertEqual(hashlib.sha256(digests.encode()).hexdigest(),pngs)
                self.assertEqual(hashlib.sha256(json.dumps(r["raster"]["source_windows"]).encode()).hexdigest(),windows)
                # One read per bilinear corner set, not one per corner.
                self.assertLess(len(reads),len(r["raster"]["source_windows"]))

    def test_limits_missing_source_and_stale_plan(self):
        for counts in [[0,1],[True,1],[16,16]]:
            o=dict(self.opts(),cell_count=counts,cell_size_cm=102400,spacing_cm=200)
            with self.assertRaises(ValueError): dem.plan(o)
        self.assertEqual(import_layer.limit_entries(),[])
        # More than the former 1025² samples (and four tiles) warns instead.
        dem.mosaic_grid(dict(self.opts(),cell_count=[5,1],cell_size_cm=102400,spacing_cm=200))
        self.assertIn("dem_samples",codes())
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
