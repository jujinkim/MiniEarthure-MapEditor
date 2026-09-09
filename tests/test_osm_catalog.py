import unittest, sys, json, io
from pathlib import Path
from email.message import Message
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import osm_download as d
class Response(io.BytesIO):
    status=200
    headers=Message()
    def geturl(self): return d.CATALOG
class CatalogTests(unittest.TestCase):
    def test_official_fields_and_filtering(self):
        features=[dict(properties=dict(id="region",name="Region",parent="continent",urls=dict(pbf=d.BASE+"region-latest.osm.pbf")))]
        def read(): return d.catalog(lambda *args: Response(json.dumps(dict(type="FeatureCollection",features=features)).encode()))
        self.assertEqual(read()["regions"][0]["parent"],"continent")
        for url in ["https://example.com/a.osm.pbf",d.BASE+"a.osm.pbf?x=1"]:
            features[0]["properties"]["urls"]["pbf"]=url
            with self.assertRaises(ValueError): read()
        features[0]["properties"]["urls"]["pbf"]=d.BASE+"region-latest.osm.pbf"
        features.append(features[0])
        with self.assertRaises(ValueError): read()
    def test_catalog_caps_and_invalid_json(self):
        for raw in [b"x",b"x"*(d.CATALOG_LIMIT+1),b'{"type":"FeatureCollection","features":[]}']:
            with self.assertRaises(ValueError): d.catalog(lambda *a: Response(raw))
if __name__=="__main__": unittest.main()
