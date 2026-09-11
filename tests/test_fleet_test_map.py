"""Public source reproducibility and refusal; no private runtime dependency."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fleet_test_map import create

class FleetMapTests(unittest.TestCase):
    def test_reproducible_source_and_safe_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "new"
            report = create(destination)
            for name, digest in report["source_files"].items():
                self.assertEqual(hashlib.sha256((destination / name).read_bytes()).hexdigest(), digest)
                self.assertEqual((destination / name).read_bytes(), (ROOT / "examples/fleet-playground" / name).read_bytes())
            before = (destination / "document.json").read_bytes()
            with self.assertRaises(FileExistsError): create(destination)
            self.assertEqual(before, (destination / "document.json").read_bytes())

    def test_actual_gap_bypass_and_authored_collision(self):
        doc = json.loads((ROOT / "examples/fleet-playground/document.json").read_text())
        roads = {r["id"]: r for r in doc["roads"]}
        self.assertEqual(doc["recipe_version"], 6)
        self.assertEqual(roads["landing"]["points"][0][0] - roads["launch"]["points"][-1][0], 1200)
        self.assertEqual(roads["launch"]["points"][-1][1], 300)
        self.assertTrue(all(p[1] == 0 for p in roads["bypass"]["points"]))
        self.assertEqual(len(doc["placements"]), 7)
        self.assertEqual(len(doc["assets"]), 2)
        self.assertTrue(all(a["collision"] for a in doc["assets"]))

if __name__ == "__main__": unittest.main()
