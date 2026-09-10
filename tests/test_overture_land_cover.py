import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import overture_land_cover as a
from overture_land_cover_fixture import snapshot
from geojson import convert

class LandCoverTests(unittest.TestCase):
    def layer(self,obj):
        raw=json.dumps(obj).encode(); value,meta=a.parse(raw)
        return a.finish(convert(value,"synthetic land cover",a.LICENSE,layer_id="a"*32,source_bytes=raw,
            coordinates=dict(mode="wgs84-utm",origin=[9,55],local_origin_m=[512,512])),meta)
    def test_mapping_holes_islands_estimates_order_immutability(self):
        obj=snapshot(); original=copy.deepcopy(obj); layer=self.layer(obj)
        self.assertEqual(obj,original)
        self.assertEqual(layer.feature_count,1)
        self.assertEqual(len(layer.patches),3)
        self.assertEqual(len(layer.patches[0]["after"]["exclusions"]),1)
        meta=layer.coordinates["overture_land_cover"]
        self.assertEqual(meta["feature_sources"][0]["zone_ids"],[p["id"] for p in layer.patches])
        self.assertEqual([r["disposition"] for r in meta["feature_sources"]],["forest","other-subtype","lower-detail"])
        self.assertEqual(layer.estimates,{"vegetation_spacing_density":3})
        obj["features"].reverse()
        self.assertEqual(self.layer(obj).patches,layer.patches)
        self.assertEqual(self.layer(obj).coordinates,layer.coordinates)
        self.assertTrue(all(p["field"]=="zones" and p["after"]["kind"]=="forest" for p in layer.patches))
    def test_known_nonforest_never_becomes_trees(self):
        for subtype in a.SUBTYPES:
            if subtype=="forest": continue
            obj=snapshot();obj["features"][0]["properties"]["subtype"]=subtype
            with self.subTest(subtype=subtype),self.assertRaisesRegex(ValueError,"No high-detail forest"):self.layer(obj)
    def test_strict_source_profiles(self):
        for key,value in [("theme","buildings"),("type","land_use"),("subtype","orchard"),("sources",[]),("id","other"),("cartography",None),("cartography",dict(min_zoom=7,max_zoom=15)),("cartography",dict(min_zoom=True,max_zoom=15))]:
            obj=snapshot();obj["features"][-1]["properties"][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.layer(obj)
        for key,value in [("license","MIT"),("profile","all-vegetation"),("release","latest"),("bbox",[9,55,10,56])]:
            obj=snapshot();obj[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.layer(obj)
        obj=snapshot();obj["features"].append(copy.deepcopy(obj["features"][0]))
        with self.assertRaisesRegex(ValueError,"Duplicate"):self.layer(obj)
    def test_whole_candidate_invalid_geometry_and_quantization(self):
        for change in ["z","open","touch","overlap","wrong-hole","outside","collapse"]:
            obj=snapshot();polys=obj["features"][0]["geometry"]["coordinates"]
            if change=="z":polys[-1][0][1].append(3)
            elif change=="open":polys[-1][0].pop()
            elif change=="touch":polys[0][1][0]=polys[0][0][0];polys[0][1][-1]=polys[0][0][0]
            elif change=="overlap":polys.append(copy.deepcopy(polys[0]))
            elif change=="wrong-hole":polys[-1].append(polys[0].pop())
            elif change=="outside":obj["bbox"]=[10,55,10.001,55.001]
            else:
                polys[:]=[[[[9,55],[9+1e-9,55],[9+1e-9,55+1e-9],[9,55+1e-9],[9,55]]]]
            with self.subTest(change=change),self.assertRaises(ValueError):self.layer(obj)
    def test_budgets(self):
        for module,key,limit in [(a,"MAX_FEATURES",2),(a,"MAX_POINTS",4),(a,"MAX_INPUT",20)]:
            with patch.object(module,key,limit),self.assertRaises(ValueError):self.layer(snapshot())
        with patch("polygon_geometry.MAX_TOPOLOGY_CHECKS",1),self.assertRaisesRegex(ValueError,"topology budget"):self.layer(snapshot())
        with patch("import_layer.MAX_OUTPUT",100),self.assertRaises(ValueError):self.layer(snapshot())

if __name__=="__main__":unittest.main()
