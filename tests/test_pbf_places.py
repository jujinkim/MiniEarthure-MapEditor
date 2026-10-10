import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from pbf_places import lookup
from pbf_places_fixture import XML, pbf


class PlaceLookup(unittest.TestCase):
    def run_lookup(self, query, xml=XML, event=lambda *args: None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "original.pbf"
            raw = pbf(source, xml)
            try:
                value = lookup(source, query, root, event)
                self.assertEqual(value["source_sha256"], hashlib.sha256(raw).hexdigest())
                return value
            finally:
                self.assertEqual(source.read_bytes(), raw)
                self.assertEqual(sorted(p.name for p in root.iterdir()), ["original.pbf"])

    def test_korean_english_exact_extent_and_byte_progress(self):
        for query in ("가상시", "synthetic"):
            events = []
            value = self.run_lookup(query, event=lambda *args: events.append(args))
            place = value["places"][0]
            self.assertEqual(place["bbox"], [9,55,9.0002,55.0002])
            self.assertEqual(place["name"], "가상시")
            self.assertEqual(place["source_id"], "relation/10")
            self.assertFalse(place["issue"])
            for stage in ("read", "index_relations", "index_ways", "index_nodes"):
                steps = [x for x in events if x[0] == stage]
                self.assertEqual(steps[0][1], 0)
                self.assertEqual(steps[-1][1:3], (value["source_bytes"],)*2)
        self.assertFalse(self.run_lookup("unknown")["places"])

    def test_missing_and_nested_outer_never_guess(self):
        for xml in (XML.replace('type="way" ref="1" role="outer"', 'type="way" ref="999" role="outer"'),
                    XML.replace('ref="11" role="subarea"', 'ref="11" role="outer"')):
            place = self.run_lookup("가상", xml)["places"][0]
            self.assertTrue(place["issue"])
            self.assertEqual(place["bbox"], [])
            self.assertEqual(place["outlines"], [])

    def test_cancel_and_budget_clean_owned_capture(self):
        def cancel(stage, completed, total):
            if stage == "index_ways": raise ValueError("controlled cancellation")
        with self.assertRaisesRegex(ValueError, "controlled cancellation"):
            self.run_lookup("가상", event=cancel)
        with patch("pbf_places.MAX_REFS", 1), self.assertRaisesRegex(ValueError, "reference budget"):
            self.run_lookup("가상")
        with self.assertRaisesRegex(ValueError,"name"):
            self.run_lookup("")


if __name__ == "__main__": unittest.main()
