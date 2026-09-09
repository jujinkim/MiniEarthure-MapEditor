import hashlib
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_osm_importer import OPTIONS, osm, convert
from osm_fixture import structural_xml, pbf
from osm_area import crop


def candidate(raw, fmt="osm"):
    value, counts = osm.parse(raw, fmt)
    return osm.finish(convert(value, "synthetic.osm", osm.LICENSE, source_bytes=raw,
        layer_id="c"*32, coordinates=OPTIONS, osm_graph=True), counts)


class Structures(unittest.TestCase):
    def test_geometry_connections_clearance_and_parity(self):
        raw = structural_xml().encode()
        result = candidate(raw)
        roads = [p["after"] for p in result.patches if p["field"] == "roads"]
        self.assertEqual([r["kind"] for r in roads], ["ground","bridge","ground","ground","tunnel","ground"])
        self.assertEqual([p[1] for p in roads[1]["points"]], [0,600,600,0])
        self.assertEqual([p[1] for p in roads[4]["points"]], [0,-600,-600,0])
        self.assertEqual(roads[4]["clearance_cm"], 450)
        self.assertIsNone(roads[1]["clearance_cm"])
        self.assertEqual(roads[0]["to"], roads[1]["from"])
        self.assertEqual(roads[1]["to"], roads[2]["from"])
        self.assertEqual(result.source.sha256, hashlib.sha256(raw).hexdigest())
        self.assertIn("EGM96", " ".join(result.warnings))
        self.assertIn("rectangular_tunnel_cross_section", result.estimates)
        self.assertNotIn("elevation_m", result.estimates)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(candidate(pbf(Path(directory)/"sample.pbf", raw.decode()),"pbf").patches,result.patches)
        # Source layer ordering cannot scale source elevations.
        self.assertEqual(candidate(raw.replace(b'v="1"',b'v="2"')).patches, result.patches)

    def test_whole_candidate_rejection(self):
        changes = {
            "missing-ele": lambda r: r.find("node[@id='3']").remove(r.find("node[@id='3']/tag")),
            "invalid-ele": lambda r: r.find("node/tag").set("v","nan"),
            "huge-ele": lambda r: r.find("node/tag").set("v","10001"),
            "datum": lambda r: ET.SubElement(r.find("node"),"tag",k="ele:local",v="0"),
            "no-approach": lambda r: r.remove(r.find("way[@id='1']")),
            "legal-height": lambda r: r.find("way/tag[@k='maxheight:physical']").set("k","maxheight"),
            "small-clearance": lambda r: r.find("way/tag[@k='maxheight:physical']").set("v","1.99"),
            "tunnel-type": lambda r: r.find("way/tag[@k='tunnel']").set("v","building_passage"),
            "bridge-type": lambda r: r.find("way/tag[@k='bridge']").set("v","movable"),
            "both": lambda r: ET.SubElement(r.find("way[@id='2']"),"tag",k="tunnel",v="yes"),
            "incline": lambda r: ET.SubElement(r.find("way[@id='2']"),"tag",k="incline",v="10%"),
            "node-level": lambda r: ET.SubElement(r.find("node[@id='3']"),"tag",k="level",v="1"),
        }
        for name, change in changes.items():
            with self.subTest(name=name):
                root = ET.fromstring(structural_xml()); change(root)
                with self.assertRaises(ValueError): candidate(ET.tostring(root))

    def test_crop_preserves_profiles_or_rejects(self):
        value, _ = osm.parse(structural_xml().encode(),"osm")
        clipped, _ = crop(value,[8.999,54.999,9.004,55.003])
        self.assertEqual(clipped,value)
        for bbox in [[9.0005,54.999,9.004,55.003],[9.01,55.01,9.02,55.02]]:
            with self.assertRaisesRegex(ValueError,"complete explicit-height"):
                crop(value,bbox)

    def test_interior_shared_node_splits_without_geometric_welding(self):
        root=ET.fromstring(structural_xml())
        # Approach ending in an existing ground way interior must become a graph junction.
        way=root.find("way[@id='1']")
        way.insert(2,ET.Element("nd",ref="7"))
        result=candidate(ET.tostring(root))
        roads=[p["after"] for p in result.patches if p["field"]=="roads"]
        self.assertEqual(len(roads),7)
        self.assertEqual(roads[0]["to"],roads[1]["from"])
        self.assertEqual(roads[1]["from"],roads[2]["from"])
        # Different node IDs at the same coordinates are not joined.
        duplicate=ET.fromstring(ET.tostring(root.find("node[@id='1']")))
        duplicate.set("id","100");root.append(duplicate)
        root.find("way[@id='4']/nd").set("ref","100")
        roads=[p["after"] for p in candidate(ET.tostring(root)).patches if p["field"]=="roads"]
        self.assertNotEqual(roads[0]["from"],roads[4]["from"])

    def test_invalid_cli_keeps_source_and_output(self):
        import subprocess,sys
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/"source.osm";output=Path(directory)/"layer.json"
            raw=structural_xml().replace('k="maxheight:physical"','k="maxheight"').encode();source.write_bytes(raw)
            command=[sys.executable,str(Path(__file__).resolve().parents[1]/"scripts/importers/geojson.py"),str(source),str(output),
                "--input-format","osm","--coordinates","wgs84-utm","--origin","9","55","--local-origin","512","512","--license",osm.LICENSE,"--layer-id","c"*32]
            run=subprocess.run(command,capture_output=True,timeout=15)
            self.assertNotEqual(run.returncode,0);self.assertFalse(output.exists());self.assertEqual(source.read_bytes(),raw)
            source.write_text(structural_xml());output.write_bytes(b"existing")
            run=subprocess.run(command,capture_output=True,timeout=15)
            self.assertNotEqual(run.returncode,0);self.assertEqual(output.read_bytes(),b"existing")

    def test_budget_and_wrong_adapter_do_not_drop_structures(self):
        from unittest.mock import patch
        value,_=osm.parse(structural_xml().encode(),"osm")
        with self.assertRaisesRegex(ValueError,"no silent flattening"):
            convert(value,"source",osm.LICENSE,coordinates=OPTIONS)
        with patch.object(osm,"MAX_FEATURES",5),self.assertRaisesRegex(ValueError,"budget"):
            osm.split_vertical_roads(value["features"])
