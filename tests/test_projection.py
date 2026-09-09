"""Requires optional requirements-import.txt; synthetic geographic fixtures only."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from projection import Coordinates
from geojson import convert

OPTIONS={"mode":"wgs84-utm","origin":[9,55],"local_origin_m":[512,512]}
POINTS=[[9,55],[9.0002,55],[9.0002,55.0002],[9,55.0002],[9,55]]
LOCAL=[[512,512],[524.79,512],[524.79,534.26],[512,534.26],[512,512]]


def fixture(points):
    return {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"height_m":12},"geometry":{"type":"Polygon","coordinates":[points]}}]}


class ProjectionTests(unittest.TestCase):
    def test_official_proj_vectors_north_and_south(self):
        # https://proj.org/en/stable/operations/projections/utm.html usage vectors.
        north=Coordinates(OPTIONS)
        x,y=north.transformer.transform(12,56,errcheck=True)
        self.assertAlmostEqual(x,687071.44,places=2)
        self.assertAlmostEqual(y,6210141.33,places=2)
        south=Coordinates({"mode":"wgs84-utm","origin":[171,-44],"local_origin_m":[0,0]})
        x,y=south.transformer.transform(174,-44,errcheck=True)
        self.assertAlmostEqual(x,740526.32,places=2)
        self.assertAlmostEqual(y,5123750.87,places=2)
        self.assertEqual(south.metadata["target_crs"],"EPSG:32759")
        self.assertFalse(north.transformer.is_network_enabled)

    def test_exact_local_origin_and_cm_fixture_parity(self):
        geo=convert(fixture(POINTS),"geo","MIT",coordinates=OPTIONS,layer_id="a"*32)
        local=convert(fixture(LOCAL),"local","MIT",layer_id="a"*32)
        self.assertEqual(geo.patches,local.patches)
        self.assertEqual(geo.extent_cm,[51200,51200,52479,53426])
        self.assertEqual(geo.coordinates["axis_order"],"longitude-latitude")
        self.assertEqual(geo.coordinates["target_crs"],"EPSG:32632")
        self.assertIn("proj",geo.coordinates)
        self.assertEqual(geo.source.accuracy,"unknown")

    def test_coordinate_rejection_is_explicit(self):
        p=Coordinates(OPTIONS)
        for point in [[55,9],[13,55],[9,-1],[9,56],[9,85],[181,55],[True,55],[9,55,1]]:
            with self.subTest(point=point),self.assertRaises(ValueError):p.point(point)
        for options in [{"mode":"guess"},{"mode":"local-metres","origin":[0,0]},
            {"mode":"wgs84-utm","origin":None,"local_origin_m":[0,0]},
            {"mode":"wgs84-utm","origin":[0,85],"local_origin_m":[0,0]}]:
            with self.assertRaises(ValueError):Coordinates(options)

    def test_missing_optional_dependency_has_actionable_error(self):
        module=str(Path(__file__).resolve().parents[1]/"scripts/importers")
        code="import sys;sys.path.insert(0,sys.argv[1]);from projection import Coordinates;Coordinates({'mode':'wgs84-utm','origin':[9,55],'local_origin_m':[0,0]})"
        result=subprocess.run([sys.executable,"-S","-c",code,module],capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn("install requirements-import.txt",result.stderr)


if __name__=="__main__":unittest.main()
