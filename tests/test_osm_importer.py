import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
import osm_extract as osm
from geojson import convert
from osm_fixture import XML, pbf, multipolygon_xml

OPTIONS = dict(mode="wgs84-utm", origin=[9, 55], local_origin_m=[512, 512])


def layer(raw, fmt="osm", token="a" * 32):
    value, counts = osm.parse(raw, fmt)
    return osm.finish(convert(value, "synthetic.osm", osm.LICENSE, source_bytes=raw,
                              layer_id=token, coordinates=OPTIONS), counts)


class OsmTests(unittest.TestCase):
    def test_pbf_xml_parity_provenance_and_reimport(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = pbf(Path(directory) / "source.osm.pbf")
        binary = layer(raw, "pbf")
        xml = layer(XML.encode())
        self.assertEqual(binary.patches, xml.patches)
        self.assertEqual(binary.source.sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(binary.source.license, osm.LICENSE)
        self.assertEqual(binary.adapter, "osm-extract-v1")
        self.assertEqual(binary.feature_count, 3)
        self.assertEqual([p["field"] for p in binary.patches], ["buildings", "nodes", "nodes", "roads", "zones"])
        self.assertEqual(binary.patches[3]["after"]["widths_cm"], [450])
        self.assertEqual(binary.patches[0]["after"]["height_cm"], 1200)
        self.assertIn("ignored_ways=1", " ".join(binary.warnings))
        self.assertIn("tagged_nodes=1", " ".join(binary.warnings))
        self.assertIn("elevation_m", binary.estimates)
        updated = layer(XML.replace("12 m", "23 m").encode(), token="b" * 32)
        self.assertNotEqual(xml.source.sha256, updated.source.sha256)
        self.assertTrue(set(p["id"] for p in xml.patches).isdisjoint(p["id"] for p in updated.patches))

    def test_multipolygon_assembly_parity_and_order(self):
        import xml.etree.ElementTree as ET
        xml = multipolygon_xml()
        expected = layer(xml.encode())
        self.assertEqual(expected.feature_count, 5)
        buildings = [p["after"] for p in expected.patches if p["field"] == "buildings"]
        zones = [p["after"] for p in expected.patches if p["field"] == "zones"]
        self.assertEqual(len(buildings), 3)
        self.assertEqual(len(zones), 3)
        self.assertEqual([len(z["exclusions"]) for z in zones], [0,1,0])
        self.assertIn("assembled_relations=2", " ".join(expected.warnings))
        self.assertIn("member_ways=8", " ".join(expected.warnings))
        with tempfile.TemporaryDirectory() as directory:
            binary = layer(pbf(Path(directory)/"relations.pbf", xml), "pbf")
        self.assertEqual(binary.patches, expected.patches)
        root = ET.fromstring(xml)
        root[:] = root[::-1]
        for entity in root:
            if entity.tag in ("way", "relation") and int(entity.get("id")) >= 100:
                members = [e for e in entity if e.tag != "tag"]
                entity[:] = members[::-1] + [e for e in entity if e.tag == "tag"]
        self.assertEqual(layer(ET.tostring(root)).patches, expected.patches)
        # Identical outer feature tags are consumed once, not emitted as fragments.
        root = ET.fromstring(xml)
        ET.SubElement(root.find("way[@id='100']"), "tag", k="building", v="yes")
        self.assertEqual(layer(ET.tostring(root)).patches, expected.patches)

    def test_multipolygon_defenses(self):
        import xml.etree.ElementTree as ET
        def change(action):
            root = ET.fromstring(multipolygon_xml())
            action(root)
            return ET.tostring(root)
        variants = {
            "missing-way": lambda r: r.remove(r.find("way[@id='100']")),
            "missing-node": lambda r: r.remove(r.find("node[@id='100']")),
            "unknown-role": lambda r: r.find("relation/member").set("role", ""),
            "nested-relation": lambda r: r.find("relation/member").set("type", "relation"),
            "duplicate-member": lambda r: r.find("relation").insert(0, r.find("relation/member")),
            "open-ring": lambda r: r.find("relation").remove(r.find("relation/member")),
            "conflict": lambda r: ET.SubElement(r.find("way[@id='100']"), "tag", k="building", v="school"),
            "member-vertical": lambda r: ET.SubElement(r.find("way[@id='100']"), "tag", k="bridge", v="yes"),
            "relation-vertical": lambda r: ET.SubElement(r.find("relation"), "tag", k="min_height", v="2"),
            "courtyard": lambda r: r.find("relation[@id='101']/tag[@k='landuse']").set("k", "building"),
            "outside-hole": lambda r: r.find("relation[@id='100']/member[@ref='102']").set("role", "inner"),
            "overlapping-outers": lambda r: r.find("relation[@id='101']/member[@ref='112']").set("role", "outer"),
        }
        for name, action in variants.items():
            with self.subTest(name=name), self.assertRaises(ValueError): layer(change(action))
        import polygon_geometry as geometry
        with patch.object(geometry, "MAX_TOPOLOGY_CHECKS", 1), self.assertRaisesRegex(ValueError, "topology budget"):
            layer(multipolygon_xml().encode())

    def test_invalid_multipolygon_cli_never_publishes(self):
        script = Path(__file__).resolve().parents[1] / "scripts/importers/geojson.py"
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/"bad.osm", Path(directory)/"layer.json"
            raw = multipolygon_xml().replace('role="inner"', 'role="unknown"').encode()
            source.write_bytes(raw)
            result = subprocess.run([sys.executable, str(script), str(source), str(output), "--input-format", "osm",
                "--coordinates", "wgs84-utm", "--origin", "9", "55", "--local-origin", "512", "512",
                "--license", osm.LICENSE, "--layer-id", "e"*32], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"outer/inner", result.stderr)
            self.assertFalse(output.exists())
            self.assertEqual(source.read_bytes(), raw)

    def test_unsafe_input_rejects_whole_candidate(self):
        variants = {
            "missing": XML.replace('<nd ref="5"/>', '<nd ref="99"/>'),
            "duplicate": XML.replace('</osm>', '<node id="1" lon="9" lat="55"/></osm>'),
            "bridge": XML.replace('k="width"', 'k="bridge"'),
            "layer": XML.replace('k="width"', 'k="layer"'),
            "height-unit": XML.replace("12 m", "40 ft"),
            "open-building": XML.replace('<nd ref="4"/><nd ref="1"/>', '<nd ref="4"/>'),
            "closed-road": XML.replace('<nd ref="6"/>', '<nd ref="6"/><nd ref="5"/>'),
            "vertical": XML.replace('k="height"', 'k="min_height"'),
            "area-member": XML.replace('</osm>', '<relation id="1"><member type="way" ref="1" role="outer"/><tag k="type" v="multipolygon"/></relation></osm>'),
            "relation-feature": XML.replace('</osm>', '<relation id="1"><tag k="building" v="yes"/></relation></osm>'),
            "area-road": XML.replace('k="width" v="4.5"', 'k="area" v="yes"'),
            "stairs": XML.replace('v="residential"', 'v="steps"'),
            "deleted": XML.replace('<node id="1"', '<node visible="false" id="1"'),
            "dtd": '<!DOCTYPE osm [<!ENTITY x "hi">]>' + XML,
            "malformed": XML[:-10],
        }
        for name, xml in variants.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                layer(xml.encode())
        with self.assertRaises(ValueError): osm.parse(b"broken", "pbf")
        with self.assertRaises(ValueError): osm.parse(b'<osm version="0.6"/>', "osm")
        with self.assertRaises(ValueError): osm.parse(XML.encode("utf-16"), "osm")

    def test_bounds_and_dependency_failure(self):
        for key in ["MAX_INPUT", "MAX_POINTS", "MAX_ENTITIES", "MAX_REFS", "MAX_FEATURES"]:
            with self.subTest(key=key), patch.object(osm, key, 1), self.assertRaises(ValueError):
                osm.parse(XML.encode(), "osm")
        with patch.object(osm, "version", return_value="0"), self.assertRaisesRegex(ValueError, "requirements-import"):
            osm.dependency()

    def test_way_order_independent_and_warning_cap(self):
        value = layer(XML.encode())
        value.warnings = ["road warning"] * 50
        value.warning_count = 80
        osm.finish(value, {})
        self.assertEqual(len(value.warnings), 50)
        self.assertEqual(value.warning_count, 84)
        self.assertIn("OpenStreetMap", value.warnings[0])
        import xml.etree.ElementTree as ET
        root = ET.fromstring(XML)
        root[:] = list(reversed(root[:]))
        reordered = layer(ET.tostring(root))
        self.assertEqual(reordered.patches, layer(XML.encode()).patches)

    def test_real_cli_progress_and_preservation(self):
        script = Path(__file__).resolve().parents[1] / "scripts/importers/geojson.py"
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "source.pbf", Path(directory) / "layer.json"
            raw = pbf(source)
            command = [sys.executable, str(script), str(source), str(output), "--input-format", "pbf",
                       "--coordinates", "wgs84-utm", "--origin", "9", "55", "--local-origin", "512", "512",
                       "--license", osm.LICENSE, "--layer-id", "c" * 32]
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))
            self.assertEqual(list(dict.fromkeys(e["stage"] for e in events)), ["read", "parse", "convert", "write", "complete"])
            self.assertEqual(events[-1]["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            preserved = output.read_bytes()
            result = subprocess.run(command, capture_output=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual(output.read_bytes(), preserved)


if __name__ == "__main__": unittest.main()
