"""Synthetic source, graph identity, rejection, budgets and real Arrow boundary."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
import overture_transportation as a
from overture_transportation_fixture import snapshot, scoped_snapshot, off_vertex_snapshot


class TransportationTests(unittest.TestCase):
    def layer(self,value):
        raw=json.dumps(value).encode()
        parsed=a.parse(raw)
        layer=a.convert(parsed,"synthetic",raw,layer_id="a"*32,
            coordinates={"mode":"wgs84-utm","origin":[9,55],"local_origin_m":[512,512]})
        return layer

    def test_internal_junction_order_identity_and_source_retention(self):
        value=snapshot(); before=copy.deepcopy(value)
        layer=self.layer(value)
        nodes=[p["after"] for p in layer.patches if p["field"]=="nodes"]
        roads=[p["after"] for p in layer.patches if p["field"]=="roads"]
        self.assertEqual(len(nodes),4);self.assertEqual(len(roads),3)
        self.assertEqual(roads[0]["to"],roads[1]["from"])
        self.assertEqual(roads[0]["to"],roads[2]["from"])
        self.assertEqual([r["surfaces"] for r in roads],[["asphalt"],["asphalt"],["gravel"]])
        self.assertEqual([r["widths_cm"] for r in roads],[[600],[600],[400]])
        self.assertEqual(value,before)
        metadata=layer.coordinates["overture_transportation"]
        self.assertEqual(metadata["segment_sources"][0]["road_ids"],[roads[0]["id"],roads[1]["id"]])
        self.assertEqual(metadata["connector_sources"][1]["sources"],value["features"][1]["properties"]["sources"])
        self.assertEqual(layer.source.sha256,hashlib.sha256(json.dumps(value).encode()).hexdigest())
        value["features"].reverse()
        for f in value["features"]:
            if "connectors" in f["properties"]:f["properties"]["connectors"].reverse()
        other=self.layer(value)
        self.assertEqual(other.patches,layer.patches)
        self.assertEqual(other.coordinates,layer.coordinates)

    def test_coincident_coordinates_never_merge_source_ids(self):
        value=snapshot()
        twin=copy.deepcopy(value["features"][1]);twin["id"]="b-twin";twin["properties"]["id"]="b-twin"
        value["features"].append(twin)
        value["features"][5]["properties"]["connectors"][0]["connector_id"]="b-twin"
        roads=[p["after"] for p in self.layer(value).patches if p["field"]=="roads"]
        self.assertNotEqual(roads[0]["to"],roads[2]["from"])
        self.assertEqual(roads[0]["points"][-1],roads[2]["points"][0])

    def test_unknown_width_and_surface_estimates_and_strict_rules(self):
        value=snapshot();p=value["features"][4]["properties"]
        p["width_rules"]=None;p["road_surface"]=None
        layer=self.layer(value)
        self.assertEqual(layer.estimates["width_m"],2)
        self.assertEqual(layer.patches[4]["after"]["widths_cm"],[800])
        p["road_flags"]=["is_link"]
        self.layer(value)
        p["road_flags"]=[dict(values=["is_link"],between=None)]
        p["width_rules"]=[dict(value=4,between=[0,1])]
        self.layer(value)

    def test_whole_graph_rejections(self):
        modes=["missing","duplicate","orphan","no_endpoint","wrong_at","off_vertex","same_vertex","outside","bbox","subtype","class","bridge","tunnel","flags","level","level_rules","access","turn","subclass","scoped_width","scoped_surface","width","surface","z","repeat","collapse","version","sources","theme","id","bool","future"]
        for mode in modes:
            value=json.loads(json.dumps(snapshot()));s=value["features"][4];p=s["properties"]
            if mode=="missing":value["features"].pop(0)
            elif mode=="duplicate":value["features"].append(copy.deepcopy(value["features"][0]))
            elif mode=="orphan":
                f=copy.deepcopy(value["features"][0]);f["id"]="unused";f["properties"]["id"]="unused";value["features"].append(f)
            elif mode=="no_endpoint":p["connectors"].pop(0)
            elif mode=="wrong_at":p["connectors"][1]["at"]=0.7
            elif mode=="off_vertex":value["features"][1]["geometry"]["coordinates"][1]+=0.00001
            elif mode=="same_vertex":p["connectors"][1]=copy.deepcopy(p["connectors"][0])
            elif mode=="outside":value["bbox"][0]=9.0001
            elif mode=="bbox":value["bbox"][2]=9.1
            elif mode=="subtype":p["subtype"]="rail"
            elif mode=="class":p["class"]="footway"
            elif mode in ("bridge","tunnel"):p["road_flags"]=[dict(values=["is_"+mode])]
            elif mode=="flags":p["road_flags"]=[dict(values=["is_link"],between=[0.1,0.8])]
            elif mode=="level":p["level"]=1
            elif mode=="level_rules":p["level_rules"]=[dict(value=1)]
            elif mode=="access":p["access_restrictions"]=[dict(access_type="denied")]
            elif mode=="turn":p["prohibited_transitions"]=[dict(final_heading="forward")]
            elif mode=="subclass":p["subclass"]="parking_aisle"
            elif mode=="scoped_width":p["width_rules"]=[dict(value=6,between=[0,0.5])]
            elif mode=="scoped_surface":p["road_surface"]=[dict(value="dirt"),dict(value="paved")]
            elif mode=="width":p["width_rules"]=[dict(value=True)]
            elif mode=="surface":p["road_surface"]=[dict(value="unpaved")]
            elif mode=="z":s["geometry"]["coordinates"][0].append(10)
            elif mode=="repeat":s["geometry"]["coordinates"].append(s["geometry"]["coordinates"][0])
            elif mode=="collapse":
                s["geometry"]["coordinates"].insert(1,[9.000100000001,55.0002])
            elif mode=="version":p["version"]=True
            elif mode=="sources":p["sources"]=[]
            elif mode=="theme":p["theme"]="buildings"
            elif mode=="id":p["id"]="other"
            elif mode=="bool":value["ground_m"]=True
            else:p["future_geometry"]=True
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.layer(value)

    def test_integral_json_numbers_and_reusable_parsed_metadata(self):
        value=snapshot();value["snapshot_version"]=1.0
        for f in value["features"]: f["properties"]["version"]=1.0
        self.layer(value)
        raw=json.dumps(value).encode();parsed=a.parse(raw);before=copy.deepcopy(parsed)
        for token in ["a"*32,"b"*32]:
            a.convert(parsed,"synthetic",raw,layer_id=token,coordinates={"mode":"wgs84-utm","origin":[9,55],"local_origin_m":[512,512]})
        self.assertEqual(parsed,before)
        value["features"][0]["properties"]["version"]=1.5
        with self.assertRaises(ValueError):self.layer(value)

    def test_budgets(self):
        for name,limit in [("MAX_FEATURES",5),("MAX_POINTS",8),("MAX_ROADS",2)]:
            with self.subTest(name=name),patch.object(a,name,limit),self.assertRaises(ValueError):self.layer(snapshot())

    def test_scoped_geodetic_boundaries_and_provenance(self):
        from pyproj import Geod
        value=scoped_snapshot();raw=json.dumps(value).encode()
        parsed=a.parse(raw);layer=self.layer(value)
        roads=[p["after"] for p in layer.patches if p["field"]=="roads"]
        self.assertEqual(len(roads),3)
        self.assertEqual(len([p for p in layer.patches if p["field"]=="nodes"]),4)
        self.assertEqual(roads[0]["widths_cm"],[600,400])
        self.assertEqual(roads[1]["surfaces"],["asphalt","dirt"])
        geod=Geod(ellps="WGS84")
        original=value["features"][4]["geometry"]["coordinates"]
        total=sum(geod.inv(*x,*y)[2] for x,y in zip(original,original[1:]))
        inserted=parsed["roads"][0]["coords"][1]
        self.assertAlmostEqual(geod.inv(*original[0],*inserted)[2]/total,0.25,places=9)
        self.assertNotEqual(inserted[1],original[0][1],"ellipsoid interpolation, not linear lon/lat")
        meta=layer.coordinates["overture_transportation"]["segment_sources"][0]
        self.assertEqual(meta["road_spans"][0]["fractions"],[0,0.25,value["features"][4]["properties"]["connectors"][1]["at"]])
        self.assertEqual(meta["road_spans"][1]["points_cm"],roads[1]["points"])
        value["features"][4]["properties"]["width_rules"].reverse()
        self.assertEqual(self.layer(value).patches,layer.patches)
        self.assertEqual(self.layer(value).coordinates,layer.coordinates)

    def test_interval_failures_and_output_admission(self):
        invalid=[[],[0,0],[0.8,0.2],[False,1],[0,1.01],[0],"0,1"]
        for between in invalid:
            value=snapshot();value["features"][4]["properties"]["width_rules"]=[dict(value=6,between=between)]
            with self.subTest(between=between),self.assertRaises(ValueError): self.layer(value)
        for rules in [
            [dict(value=6,between=[0,0.4]),dict(value=4,between=[0.5,1])],
            [dict(value=6,between=[0,0.6]),dict(value=4,between=[0.5,1])],
            [dict(value=6),dict(value=4,between=[0.5,1])],
            [dict(value=6,when={})], [dict(value=None)], [dict(value=0.1)]]:
            value=snapshot();value["features"][4]["properties"]["width_rules"]=rules
            with self.subTest(rules=rules),self.assertRaises(ValueError): self.layer(value)
        for name,limit in [("MAX_RULES",1),("MAX_OUTPUT_POINTS",11)]:
            with patch.object(a,name,limit),self.assertRaises(ValueError): self.layer(scoped_snapshot())
        value=scoped_snapshot();value["features"][4]["properties"]["width_rules"][0]["between"][1]=1e-10
        value["features"][4]["properties"]["width_rules"][1]["between"][0]=1e-10
        with self.assertRaisesRegex(ValueError,"collapse"):self.layer(value)
        value=scoped_snapshot();p=value["features"][4]["properties"]
        at=p["connectors"][1]["at"]
        p["width_rules"]=[dict(value=6,between=[0,at]),dict(value=4,between=[at,1])]
        p["road_surface"]=[dict(value="gravel")]
        self.assertEqual([len(r["coords"]) for r in a.parse(json.dumps(value).encode())["roads"]],[2,2,2])

    def test_off_vertex_shared_connection_and_physical_intervals(self):
        value = off_vertex_snapshot(); before = copy.deepcopy(value)
        layer = self.layer(value)
        meta = layer.coordinates["overture_transportation"]
        self.assertEqual(meta["source_position_count"],8)
        ref = meta["segment_sources"][0]["connectors"][1]
        self.assertIsNone(ref["vertex"])
        self.assertEqual(ref["resolved_at"],0.5)
        roads = [p["after"] for p in layer.patches if p["field"] == "roads"]
        self.assertEqual(roads[0]["points"][-1], roads[2]["points"][0])
        self.assertEqual(roads[0]["to"], roads[2]["from"])
        self.assertEqual(roads[0]["widths_cm"],[600,400])
        self.assertEqual(roads[1]["surfaces"],["asphalt","dirt"])
        self.assertEqual(value,before)
        value["features"].reverse()
        self.assertEqual(self.layer(value).patches,layer.patches)
        self.assertEqual(self.layer(value).coordinates,layer.coordinates)

    def test_connector_tolerance_and_rejection(self):
        from pyproj import Geod
        geod = Geod(ellps="WGS84")
        value = off_vertex_snapshot()
        point = value["features"][1]["geometry"]["coordinates"]
        for delta in [0.0005,0.002]:
            changed = copy.deepcopy(value)
            lon,lat,_ = geod.fwd(*point,0,delta)
            changed["features"][1]["geometry"]["coordinates"] = [lon,lat]
            changed["features"][5]["geometry"]["coordinates"][0] = [lon,lat]
            if delta < 0.001:
                meta = self.layer(changed).coordinates["overture_transportation"]
                self.assertAlmostEqual(meta["segment_sources"][0]["connectors"][1]["displacement_m"],delta,places=7)
            else:
                with self.assertRaisesRegex(ValueError,"Off-line|1 mm"): self.layer(changed)
        changed = copy.deepcopy(value)
        changed["features"][4]["properties"]["connectors"][1]["at"] = 0.6
        with self.assertRaisesRegex(ValueError,"at disagrees"): self.layer(changed)
        with patch.object(a,"MAX_CONNECTOR_EDGE_CHECKS",0),self.assertRaisesRegex(ValueError,"comparison budget"):
            self.layer(value)
        changed = copy.deepcopy(value)
        changed["features"][4]["properties"]["width_rules"] = [dict(value=6,between=[0,0.5]),dict(value=4,between=[0.5,1])]
        self.assertEqual(len(a.parse(json.dumps(changed).encode())["roads"][0]["coords"]),2)
        changed["features"][4]["properties"]["width_rules"][0]["between"][1] = 0.50000000001
        changed["features"][4]["properties"]["width_rules"][1]["between"][0] = 0.50000000001
        with self.assertRaisesRegex(ValueError,"collapse"): self.layer(changed)

    def test_ambiguous_closest_positions_and_displaced_endpoint(self):
        from pyproj import Geod
        geod = Geod(ellps="WGS84")
        def position(x,y):
            lon,lat,_ = geod.fwd(9,55,90,x)
            lon,lat,_ = geod.fwd(lon,lat,0,y)
            return [lon,lat]
        coords = [position(0,0),position(10,0),position(10,0.001),position(0,0.001)]
        lengths = [0]
        for x,y in zip(coords,coords[1:]):lengths.append(lengths[-1]+geod.inv(*x,*y)[2])
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            a.connection_position(position(5,0.0005),0.25,coords,lengths,geod,[0])
        value = off_vertex_snapshot()
        point = value["features"][0]["geometry"]["coordinates"]
        lon,lat,_ = geod.fwd(*point,270,0.0005)
        value["features"][0]["geometry"]["coordinates"] = [lon,lat]
        layer = self.layer(value)
        ref = layer.coordinates["overture_transportation"]["segment_sources"][0]["connectors"][0]
        self.assertEqual(ref["vertex"],0)
        self.assertEqual(ref["resolved_at"],0)
        self.assertAlmostEqual(ref["displacement_m"],0.0005,places=7)


if __name__=="__main__":unittest.main()
