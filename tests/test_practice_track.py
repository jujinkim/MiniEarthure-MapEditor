"""Public authored-source and deterministic package checks; no consumer completion proof."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("practice_track", ROOT/"scripts/practice_track.py")
track=importlib.util.module_from_spec(spec);spec.loader.exec_module(track)

class PracticeTrack(unittest.TestCase):
    def test_authored_sequence_and_real_beam(self):
        source=track.source()
        self.assertEqual([c["piece"] for c in source["checkpoints"]],
                         ["course-%02d"%n for n in range(1,11)]+["completion"])
        self.assertEqual(len(source["grind_lines"]),1)
        self.assertTrue(all(a["kind"]=="manual_flight" and a["landing"] for a in source["actions"]))
        beam=[g for g in source["structures"] if g["id"]=="authored-single-beam"]
        self.assertEqual(len(beam),1)
        self.assertEqual(len(beam[0]["parts"]),1)
        self.assertTrue(all(g["motion"]["kind"]=="static" and g.get("effect") is None for g in source["structures"]))
        self.assertFalse(source["grounded_supports"])

    def test_export_roundtrip_and_repeatability(self):
        cli=Path(os.environ.get("MAPKIT_CLI",ROOT/"addons/mapkit/target/debug/mapkit")).resolve()
        with tempfile.TemporaryDirectory(prefix="practice-source-") as temp:
            a=track.build(Path(temp)/"a",cli);b=track.build(Path(temp)/"b",cli)
            self.assertEqual((a/"source.json").read_bytes(),(b/"source.json").read_bytes())
            self.assertEqual((a/"practice.memap").read_bytes(),(b/"practice.memap").read_bytes())
            result=subprocess.run([str(cli),"verify-track",str(a/"practice.memap")],capture_output=True,text=True,check=True)
            assembly=json.loads(result.stdout)["assembly"]
            self.assertFalse(assembly["issues"])
            self.assertEqual(assembly["authoring"],track.source())
            document=json.loads((a/"project/document.json").read_text())
            self.assertEqual(len(document["courses"][0]["definition"]["checkpoints"]),11)
            self.assertIsNone(document["courses"][0].get("validation"))
            for piece in assembly["pieces"]:
                if piece["id"]=="flight_curve":
                    self.assertTrue(all(not sample["safe"] and sample["mode"]=="flight" for sample in piece["path"]))
            self.assertFalse(any(g["motion"]["kind"]!="static" for g in document["gimmicks"]))
            self.assertEqual(json.loads((a/"courses.json").read_text())["human_completion"],"unverified")

if __name__=="__main__":unittest.main()
