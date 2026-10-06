"""Public authored-source and deterministic package checks; no consumer completion proof."""
import importlib.util
import json
import hashlib
import math
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

    def test_reduced_early_courses_wider_air_turn_and_solid_ends(self):
        source=track.source()
        pieces={p["id"]:p for p in source["instances"]}
        for number in range(1,4):
            self.assertEqual(pieces[f"course-{number:02d}"]["width_cm"],800)
            self.assertAlmostEqual(sum(v*v for v in pieces[f"course-{number:02d}"]["control_points"][-1])**.5,2000)
        self.assertEqual(pieces["right-wide"]["control_points"][-1],[600,0,600])
        self.assertEqual(pieces["left-wide"]["control_points"][-1],[600,0,600])
        for number, turn in [(4,"right-sharp"),(5,"left-sharp")]:
            approach=pieces[f"course-{number:02d}"]
            runout=pieces[f"runout-{number:02d}"]
            self.assertEqual((approach["entry_width_cm"],approach["exit_width_cm"]),(800,400))
            self.assertEqual((runout["entry_width_cm"],runout["exit_width_cm"]),(400,800))
            self.assertEqual(pieces[turn]["width_cm"],400)
            self.assertEqual(pieces[turn]["entry_width_cm"],400)
            self.assertEqual(pieces[turn]["control_points"][-1],[300,0,300])
        # Both 90-degree cubics are exact left/right mirrors in their local heading.
        right=pieces["right-sharp"]["control_points"]
        left=pieces["left-sharp"]["control_points"]
        self.assertEqual(right,[[p[2],p[1],p[0]] for p in left])
        for a,b in zip(source["instances"],source["instances"][1:]):
            self.assertEqual([x+y for x,y in zip(a["position_cm"],a["control_points"][-1])],b["position_cm"])
            self.assertEqual(a["exit_width_cm"],b["entry_width_cm"])
        self.assertEqual(pieces["course-09"]["width_cm"],400)
        self.assertEqual(pieces["flight-10"]["control_points"][-1][1],360)
        for name in ["start-wall","finish-wall"]:
            wall=next(g for g in source["structures"] if g["id"]=="authored-"+name)
            vertices=wall["parts"][0]["vertices"]
            self.assertEqual(max(v[1] for v in vertices)-min(v[1] for v in vertices),100)
            self.assertEqual(max(v[0] for v in vertices)-min(v[0] for v in vertices),840)

    def test_raised_beam_and_early_air_entry(self):
        pieces={p["id"]:p for p in track.source()["instances"]}
        beam=next(s for s in track.source()["structures"] if s["id"]=="authored-single-beam")
        road_y=pieces["course-08"]["position_cm"][1]
        self.assertEqual(beam["position"][1]+10,road_y+45)
        self.assertTrue(all(p[1]==road_y+45 for p in track.source()["grind_lines"][0]["control_points"]))
        self.assertEqual(pieces["course-09"]["control_points"][-1],[0,0,2800])
        self.assertEqual(pieces["flight-09"]["control_points"][-1],[400,0,600])
        self.assertEqual(pieces["landing-09"]["position_cm"],
                         [pieces["course-09"]["position_cm"][0]+400,road_y,pieces["course-09"]["position_cm"][2]+3400])
        for key in ["course-09","flight-09","landing-09"]:
            self.assertEqual(pieces[key]["width_cm"],400)

    def test_export_roundtrip_and_repeatability(self):
        cli=Path(os.environ.get("MAPKIT_CLI",ROOT/"addons/mapkit/target/debug/mapkit")).resolve()
        with tempfile.TemporaryDirectory(prefix="practice-source-") as temp:
            a=track.build(Path(temp)/"a",cli);b=track.build(Path(temp)/"b",cli)
            contents=lambda directory:{str(p.relative_to(directory)):p.read_bytes() for p in directory.rglob("*") if p.is_file()}
            before=contents(a)
            self.assertEqual(before,contents(b))
            with self.assertRaises(FileExistsError):track.build(a,cli)
            self.assertEqual(before,contents(a),"existing output must remain untouched")
            recompiled=Path(temp)/"recompiled.memap"
            subprocess.run([str(cli),"compile-track",str(a/"source.json"),str(recompiled)],check=True)
            self.assertEqual(recompiled.read_bytes(),(a/"practice.memap").read_bytes())
            entry=json.loads((a/"entry.json").read_text())
            self.assertEqual(entry["expected_hash"],hashlib.sha256(recompiled.read_bytes()).hexdigest())
            result=subprocess.run([str(cli),"verify-track",str(a/"practice.memap")],capture_output=True,text=True,check=True)
            assembly=json.loads(result.stdout)["assembly"]
            self.assertFalse(assembly["issues"])
            self.assertEqual(assembly["authoring"],json.loads((a/"source.json").read_text()))
            document=json.loads((a/"project/document.json").read_text())
            self.assertEqual(len(document["courses"][0]["definition"]["checkpoints"]),11)
            source=assembly["authoring"]
            ids=[p["id"] for p in source["instances"]]
            for cp in source["checkpoints"]:
                path=assembly["pieces"][ids.index(cp["piece"])]["path"]
                self.assertAlmostEqual(sum((a-b)**2 for a,b in zip(path[0]["position_cm"],path[cp["sample"]]["position_cm"]))**.5,300,delta=1)
            def check_station(reference, distance_cm, from_end=False):
                path=assembly["pieces"][ids.index(reference["piece"])]["path"]
                stations=[0.0]
                for start,end in zip(path,path[1:]):
                    stations.append(stations[-1]+math.dist(start["position_cm"],end["position_cm"]))
                target=stations[-1]-distance_cm if from_end else distance_cm
                self.assertAlmostEqual(abs(stations[reference["sample"]]-target),min(abs(s-target) for s in stations))
            for cp in source["checkpoints"]:check_station(cp,300)
            for action in source["actions"]:
                check_station(action,400,from_end=True)
                check_station(action["landing"],0)
                path=assembly["pieces"][ids.index(action["piece"])]["path"]
                self.assertAlmostEqual(math.dist(path[action["sample"]]["position_cm"],path[-1]["position_cm"]),400,delta=1)
            first=assembly["pieces"][ids.index(source["checkpoints"][0]["piece"])]["path"][source["checkpoints"][0]["sample"]]["position_cm"]
            self.assertEqual((entry["x_cm"],entry["y_cm"]),(first[0],first[2]))
            self.assertIsNone(document["courses"][0].get("validation"))
            for piece in assembly["pieces"]:
                if piece["id"]=="flight_curve":
                    self.assertTrue(all(not sample["safe"] and sample["mode"]=="flight" for sample in piece["path"]))
            self.assertFalse(any(g["motion"]["kind"]!="static" for g in document["gimmicks"]))
            self.assertEqual(json.loads((a/"courses.json").read_text())["human_completion"],"unverified")

if __name__=="__main__":unittest.main()
