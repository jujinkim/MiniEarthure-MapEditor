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
        self.assertEqual(self.doc['bounds']['max'], [57600,19200])
        self.assertEqual(math.dist(*straight), 6250)
        original=json.loads((Path(__file__).resolve().parents[1]/'examples/driving-school-v2/document.json').read_text())
        widths={r['id']:max(r['widths_cm']) for r in original['roads']}
        for road in self.doc['roads']:
            if road['id'] in widths:
                self.assertEqual(max(road['widths_cm']), round(widths[road['id']]/4), road['id'])
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
                self.assertLessEqual(abs(b[1]-a[1])/run,0.12 if r['id'].startswith('kart-') else 0.071,r["id"])
        xs = [p[0] for p in self.roads["double-s"]["points"]]
        self.assertEqual((min(xs),max(xs)),(5312,5938))
        self.assertNotIn("crosstown-01",self.roads,"through traffic must bypass the exam lanes")

    def test_village_courses_and_cylindrical_walls(self):
        freeway=self.roads["kart-freeway-highway-straight"]
        self.assertGreater(math.dist(freeway['points'][0],freeway['points'][-1]), 1300)
        self.assertTrue(all(p[1]==62 for p in freeway['points']))
        self.assertEqual(self.roads["kart-freeway-climb"]["points"][0][1],0)
        self.assertEqual(self.roads["kart-freeway-descent"]["points"][-1][1],0)
        turns=[r for r in self.doc["roads"] if r["id"].startswith(("kart-finger-tip-","kart-finger-inside-"))]
        self.assertEqual(len(turns),7)
        for turn in turns:
            self.assertLessEqual(abs(abs(turn["points"][-1][2]-turn["points"][0][2])-450),1)
        self.assertEqual(self.roads["kart-finger-shortcut-1"]["widths_cm"],[150])
        self.assertEqual(self.roads["kart-finger-shortcut-2"]["widths_cm"],[125])
        self.assertEqual(self.roads["kart-finger-clock-tower"]["clearance_cm"],45)
        cylinders=[b for b in self.doc["buildings"] if "-cylinder-" in b["id"]]
        self.assertEqual(len(cylinders),10)
        self.assertTrue(all(len(b["footprint"])==48 and b["roof"]=="flat" for b in cylinders))
        self.assertFalse(any(r["id"].startswith("kart-quarter") for r in self.doc["roads"]))
        self.assertEqual(sum(p['asset_id']=='compact-tree' for p in self.doc['placements']),1226)
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

    def test_city_density_furniture_paving_and_previous_courses(self):
        report=self.town.city_report
        self.assertEqual([d['blocks'] for d in report['districts']],[25,16])
        self.assertEqual(len(self.doc['heightmaps']),432)
        self.assertEqual(report['buildings'],166)
        self.assertEqual(report['grass_ground_fraction'],0)
        for lot in report['lots']:
            x0,y0,x1,y1=lot['bounds']
            coverage=lot['footprint_m2']/((x1-x0)*(y1-y0))
            self.assertGreaterEqual(coverage,0.59 if lot['id']=='korea-1-1' else 0.65,lot['id'])
            self.assertLessEqual(coverage,0.80,lot['id'])
        for asset in ['city-tree','city-lamp','city-bench','city-bus-stop','city-bollard','city-bin']:
            self.assertGreater(report['props'][asset],0,asset)
        self.assertGreaterEqual(report['props']['city-bus-stop'],8)
        self.assertEqual(next(a for a in self.doc['surface_areas'] if a['id']=='city-paving')['polygon'],[[19200,0],[57600,0],[57600,19200],[19200,19200]])
        self.assertGreater(sum('markings' in r for r in self.doc['roads']),100)
        previous=Path(__file__).resolve().parents[1]/'examples/driving-school-v3'
        for r in json.loads((previous/'document.json').read_text())['roads']:
            self.assertEqual(self.roads[r['id']],r,r['id'])
        locations={p['id']:p for p in self.town.locations}
        for p in json.loads((previous/'driving.json').read_text())['locations']:
            if p['id']!='city': self.assertEqual(locations[p['id']],p)
        self.assertGreater(locations['city']['position_cm'][0],19200)
        self.assertGreater(locations['city-skyline']['position_cm'][0],38400)
        lock=json.loads(Path(__file__).with_name('driving_school_v3.lock.json').read_text())
        self.assertEqual(sha(previous.with_suffix('.memap').read_bytes()),lock['inspection']['package_sha256'])

    def test_repeatable_source_assets_and_preserved_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/"first",Path(tmp)/"second"
            report=maps.create(a)
            self.assertEqual(report,maps.create(b))
            before={str(p.relative_to(a)):p.read_bytes() for p in a.rglob("*") if p.is_file()}
            self.assertEqual(before,{str(p.relative_to(b)):p.read_bytes() for p in b.rglob("*") if p.is_file()})
            with self.assertRaises(FileExistsError): maps.create(a)
            self.assertEqual(before,{str(p.relative_to(a)):p.read_bytes() for p in a.rglob("*") if p.is_file()})

    def test_quality_block_preserves_v4_outside_explicit_scope(self):
        previous=Path(__file__).resolve().parents[1]/'examples/driving-school-v4'
        baseline=json.loads((previous/'document.json').read_text())
        report=self.town.city_report['quality_block']
        removed=set(report['replaced_placements'])
        actual={p['id']:p for p in self.doc['placements']}
        for p in baseline['placements']:
            if p['id'] not in removed: self.assertEqual(actual[p['id']],p)
        for key in ['buildings','heightmaps','zones','surface_areas','repetitions','bounds','cell_size_cm']:
            self.assertEqual(self.doc[key],baseline[key],key)
        for asset in baseline['assets']:
            self.assertIn(asset,self.doc['assets'])
            self.assertEqual(self.town.payloads[asset['path']],(previous/asset['path']).read_bytes())
        changed={'korea-ns-1-1','korea-ns-2-1'}
        for road in baseline['roads']:
            if road['id'] not in changed:
                self.assertEqual(self.roads[road['id']],road)
            else:
                south=self.roads[road['id']]
                north=self.roads[road['id']+'-q01-north']
                self.assertEqual(south['points'][0],road['points'][0])
                self.assertEqual(north['points'][-1],road['points'][-1])
                self.assertEqual(south['points'][-1],north['points'][0])
                for key in ['kind','widths_cm','sidewalk_cm','surfaces']:
                    self.assertEqual(south[key],road[key])
                    self.assertEqual(north[key],road[key])
        self.assertEqual(self.town.locations,json.loads((previous/'driving.json').read_text())['locations'])
        lock=json.loads(Path(__file__).with_name('driving_school_v4.lock.json').read_text())
        self.assertEqual(sha(previous.with_suffix('.memap').read_bytes()),lock['inspection']['package_sha256'])

    def test_quality_block_clear_lane_and_original_legible_assets(self):
        from shapely.geometry import box
        from shop_block import SHOPS, hangul, ATTRIBUTION
        corridor=box(240,63.5,268,65.5)
        footprints=[]
        for shop in SHOPS:
            area=box(shop['x']-shop['w']/2,shop['y']-shop['d']/2,
                     shop['x']+shop['w']/2,shop['y']+shop['d']/2)
            self.assertFalse(area.intersects(corridor),shop['id'])
            self.assertTrue(all(not area.intersects(other) for other in footprints),shop['id'])
            footprints.append(area)
            for char in shop['title']:
                strokes=hangul(char)
                self.assertGreater(len(strokes),3,char)
                self.assertTrue(all(0<=v<=1 for line in strokes for point in line for v in point))
        self.assertGreaterEqual(len({s['w'] for s in SHOPS}),5)
        self.assertEqual(len({s['h'] for s in SHOPS}),6)
        self.assertEqual({s['turn'] for s in SHOPS},{0,2})
        self.assertIn(ATTRIBUTION,self.doc['attributions'])
        for asset in self.doc['assets']:
            if asset['id'].startswith('q01-'):
                self.assertEqual(asset['attribution'],ATTRIBUTION)
                self.assertTrue(asset.get('collision') or asset.get('convex_collision'),asset['id'])

    def test_shipped_source_and_package_lock(self):
        root=Path(__file__).resolve().parents[1]/"examples"/"driving-school"
        lock=json.loads(Path(__file__).with_name("driving_school.lock.json").read_text())
        self.assertEqual(root.joinpath("document.json").read_bytes(),canonical(self.doc))
        self.assertEqual(sha(canonical(self.doc)),lock["source_sha256"])
        self.assertEqual(sha(root.with_suffix(".memap").read_bytes()),lock["inspection"]["package_sha256"])
        for path,data in self.town.payloads.items(): self.assertEqual(root.joinpath(path).read_bytes(),data)


if __name__ == "__main__": unittest.main()
