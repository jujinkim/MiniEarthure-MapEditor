"""Authored map invariants; native geometry/clearance is checked separately."""
import collections
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import driving_school_map as maps
from reference_maps import canonical, sha


class DrivingSchoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.town = maps.build()
        cls.doc = cls.town.doc
        cls.roads = {r["id"]: r for r in cls.doc["roads"]}

    def test_all_districts_connected_by_exact_graph_endpoints(self):
        nodes = {n["id"]: n["position"] for n in self.doc["nodes"]}
        graph = collections.defaultdict(set)
        for r in self.doc["roads"]:
            self.assertEqual(r["points"][0], nodes[r["from"]], r["id"])
            self.assertEqual(r["points"][-1], nodes[r["to"]], r["id"])
            graph[r["from"]].add(r["to"])
            graph[r["to"]].add(r["from"])
        seen, pending = set(), [self.roads["license-start"]["from"]]
        while pending:
            node = pending.pop()
            if node not in seen:
                seen.add(node)
                pending.extend(graph[node] - seen)
        self.assertEqual(set(graph), seen, "every course must be reachable without teleporting")

    def test_all_advertised_circuits_close_without_gaps(self):
        for route in self.town.routes:
            roads = [self.roads[key] for key in route["roads"]]
            pairs = list(zip(roads, roads[1:]))
            if route["closed"]: pairs.append((roads[-1], roads[0]))
            for a,b in pairs:
                self.assertEqual(a["to"], b["from"], route["id"])
                self.assertEqual(a["points"][-1], b["points"][0], route["id"])

    def test_course_scale_turns_and_gradients(self):
        straight = self.roads["two-km-straight"]["points"]
        self.assertEqual(math.dist(*straight), 200000)
        for i in range(1,7):
            points = self.roads[f"hairpin-turn-{i}"]["points"]
            first = [b-a for a,b in zip(points[0],points[1])]
            last = [b-a for a,b in zip(points[-2],points[-1])]
            cosine = sum(a*b for a,b in zip(first,last))/(math.dist(points[0],points[1])*math.dist(points[-2],points[-1]))
            self.assertLess(cosine,-0.98)
        for r in self.doc["roads"]:
            for a,b in zip(r["points"],r["points"][1:]):
                run = math.hypot(b[0]-a[0],b[2]-a[2])
                self.assertGreater(run,0,r["id"])
                self.assertLessEqual(abs(b[1]-a[1])/run,0.07,r["id"])
        xs = [p[0] for p in self.roads["double-s"]["points"]]
        self.assertEqual((min(xs),max(xs)),(170000,190000))
        self.assertNotIn("crosstown-01",self.roads,"through traffic must bypass the exam lanes")

    def test_village_courses_and_cylindrical_walls(self):
        freeway=self.roads["kart-freeway-highway-straight"]
        self.assertEqual(freeway["points"],[[405000,2000,333000],[470000,2000,333000]])
        self.assertEqual(self.roads["kart-freeway-climb"]["points"][0][1],0)
        self.assertEqual(self.roads["kart-freeway-descent"]["points"][-1][1],0)
        turns=[r for r in self.doc["roads"] if r["id"].startswith(("kart-finger-tip-","kart-finger-inside-"))]
        self.assertEqual(len(turns),7)
        for turn in turns:
            self.assertEqual(abs(turn["points"][-1][2]-turn["points"][0][2]),9000)
        self.assertEqual(self.roads["kart-finger-shortcut-1"]["widths_cm"],[600])
        self.assertEqual(self.roads["kart-finger-shortcut-2"]["widths_cm"],[500])
        self.assertEqual(self.roads["kart-finger-clock-tower"]["clearance_cm"],700)
        cylinders=[b for b in self.doc["buildings"] if "-cylinder-" in b["id"]]
        self.assertEqual(len(cylinders),10)
        self.assertTrue(all(len(b["footprint"])==48 and b["roof"]=="flat" for b in cylinders))
        self.assertFalse(any(r["id"].startswith("kart-quarter") for r in self.doc["roads"]))
        for r in self.doc["roads"]:
            if r["id"].startswith("kart-") and r["kind"] != "tunnel":
                self.assertEqual(r["kind"], "elevated" if any(p[1] for p in r["points"]) else "ground", r["id"])
        # A sloping structural mouth cannot join flat terrain. Ground-level
        # endpoints of elevated roads need a level first/last segment.
        for r in self.doc["roads"]:
            if r["kind"] == "elevated":
                for end,neighbor in ((0,1),(-1,-2)):
                    if r["points"][end][1] == 0:
                        self.assertEqual(r["points"][neighbor][1],0,r["id"])

    def test_repeatable_source_assets_and_preserved_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/"first",Path(tmp)/"second"
            report=maps.create(a)
            self.assertEqual(report,maps.create(b))
            before={str(p.relative_to(a)):p.read_bytes() for p in a.rglob("*") if p.is_file()}
            self.assertEqual(before,{str(p.relative_to(b)):p.read_bytes() for p in b.rglob("*") if p.is_file()})
            with self.assertRaises(FileExistsError): maps.create(a)
            self.assertEqual(before,{str(p.relative_to(a)):p.read_bytes() for p in a.rglob("*") if p.is_file()})

    def test_shipped_source_and_package_lock(self):
        root=Path(__file__).resolve().parents[1]/"examples"/"driving-school"
        lock=json.loads(Path(__file__).with_name("driving_school.lock.json").read_text())
        self.assertEqual(root.joinpath("document.json").read_bytes(),canonical(self.doc))
        self.assertEqual(sha(canonical(self.doc)),lock["source_sha256"])
        self.assertEqual(sha(root.with_suffix(".memap").read_bytes()),lock["inspection"]["package_sha256"])
        for path,data in self.town.payloads.items(): self.assertEqual(root.joinpath(path).read_bytes(),data)


if __name__ == "__main__": unittest.main()
