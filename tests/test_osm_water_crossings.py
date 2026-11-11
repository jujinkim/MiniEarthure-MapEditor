import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/importers"))
from osm_water_crossings import classify
from osm_extract import level_structures, estimate_structures


class SourceWaterTests(unittest.TestCase):
    def scene(self, tags=None, end=9.004):
        nodes = {1:(8.996,55.), 2:(end,55.), 3:(8.999,54.999), 4:(9.001,54.999), 5:(9.001,55.001), 6:(8.999,55.001)}
        ways = [(1,"road",[1,2],dict(highway="residential", **(tags or {}))),
                (2,"region",[3,4,5,6,3],dict(natural="water"))]
        return nodes, ways

    def test_inference_uses_original_water_and_keeps_deck(self):
        nodes, ways = self.scene()
        ways, water, evidence = classify(ways,nodes,[])
        self.assertTrue(evidence[1]["inferred"])
        self.assertEqual(level_structures(ways,nodes,{}), set())
        estimated, leveled = estimate_structures(ways,nodes,{},set(),water=water)
        self.assertIn(1,estimated)
        self.assertNotIn(1,leveled)
        self.assertEqual(estimated[1][1], "bridge")
        self.assertGreaterEqual(max(p[2] for p in estimated[1][0]),5)

    def test_explicit_bridge_crossing_no_roads_stays_structural(self):
        nodes, ways = self.scene(dict(bridge="yes"))
        self.assertNotIn(1,level_structures(ways,nodes,{}))
        result,_ = estimate_structures(ways,nodes,{},set())
        self.assertEqual(result[1][1],"bridge")

    def test_split_chain_has_land_anchors_and_continuous_deck(self):
        nodes, ways = self.scene()
        nodes.update({7:(8.9995,55.), 8:(9.0005,55.)})
        ways[0:1] = [(10,"road",[1,7],dict(highway="residential")),
                     (11,"road",[8,7],dict(highway="residential")),
                     (12,"road",[8,2],dict(highway="residential"))]
        result,water,evidence = classify(ways,nodes,[])
        self.assertTrue(all(evidence[i]["inferred"] for i in (10,11,12)))
        self.assertEqual(evidence[11]["chain_sources"], ["way/10","way/11","way/12"])
        estimates,_ = estimate_structures(result,nodes,{},set(),water=water)
        self.assertEqual(set(estimates),{10,11,12})
        self.assertEqual(estimates[10][0][-1][2],estimates[11][0][-1][2])
        self.assertEqual(estimates[11][0][0][2],estimates[12][0][0][2])
        self.assertGreaterEqual(estimates[11][0][0][2],5)
        # A side branch at the submerged split prevents guessed routing.
        nodes[9]=(9.,55.002)
        ways.append((13,"road",[7,9],dict(highway="residential")))
        _,_,evidence = classify(ways,nodes,[])
        self.assertTrue(evidence[10]["unresolved"])

    def test_chain_exception_does_not_become_a_bridge(self):
        nodes, ways = self.scene()
        nodes[7]=(9.,55.)
        ways[0:1]=[(10,"road",[1,7],dict(highway="residential")),
                    (11,"road",[7,2],dict(highway="residential",ford="yes"))]
        result,_,evidence=classify(ways,nodes,[])
        self.assertTrue(evidence[10]["unresolved"])
        self.assertTrue(evidence[11]["ford"])
        self.assertTrue(all("bridge" not in tags for _,kind,_,tags in result if kind=="road"))

    def test_failed_crossing_retains_original_id_and_reason_in_review(self):
        from collections import Counter
        from osm_extract import build_features
        from osm_review import Review
        nodes,ways = self.scene(end=9.)
        review = Review(True)
        collection,_ = build_features(nodes,{},ways,{i:(refs,tags) for i,_,refs,tags in ways},[],set(),Counter(),review=review,city=True)
        [record] = collection["osm_water_crossings"]
        self.assertEqual(record["source_id"],"way/1")
        self.assertEqual(record["status"],"excluded")
        self.assertEqual(record["failure"],review.excluded["way/1"]["reason"])
        self.assertIn("land anchors",record["failure"])
        from osm_area import crop
        cropped,_ = crop(collection,[8.998,54.998,9.002,55.002],review=review)
        self.assertEqual(cropped["osm_water_crossings"],collection["osm_water_crossings"])

    def test_dead_end_and_exceptions_are_reviewed(self):
        nodes, ways = self.scene(end=9.)
        result,_,evidence = classify(ways,nodes,[])
        self.assertTrue(evidence[1]["unresolved"])
        self.assertNotIn("bridge",result[0][3])
        for tags in [dict(ford="yes"),dict(embankment="yes"),dict(tunnel="yes")]:
            nodes,ways = self.scene(tags)
            result,_,evidence = classify(ways,nodes,[])
            self.assertNotIn("bridge",result[0][3])
            self.assertIn("precedence",evidence[1]["reason"])

    def test_explicit_ford_node_precedes_inference(self):
        nodes, ways = self.scene()
        nodes[7] = (9., 55.)
        ways[0] = (1, "road", [1,7,2], dict(highway="residential"))
        result, _, evidence = classify(ways,nodes,[],node_tags={7:dict(ford="yes")})
        self.assertTrue(evidence[1]["ford"])
        self.assertNotIn("bridge",result[0][3])

    def test_waterway_width_uses_the_city_source_defaults(self):
        from shapely.ops import transform
        nodes = {1:(9.,55.), 2:(9.01,55.)}
        for kind,width in [("river",12), ("canal",8), ("ditch",1.5)]:
            _,water,_ = classify([(1,"waterway",[1,2],dict(waterway=kind))],nodes,[])
            metric = transform(lambda x,y:(x,y*110540.0),water)
            self.assertAlmostEqual(metric.bounds[3]-metric.bounds[1],width,places=5)

    def test_insufficient_bridge_ramp_is_rejected(self):
        nodes, ways = self.scene(dict(bridge="yes"))
        nodes[1],nodes[2] = (8.9989,55.),(9.0011,55.)
        ways,water,_=classify(ways,nodes,[])
        result,leveled=estimate_structures(ways,nodes,{},set(),water=water)
        self.assertNotIn(1,result)
        self.assertNotIn(1,leveled)

    def test_water_bridge_uses_source_junction_sections_and_preserves_ground_remainders(self):
        from copy import deepcopy
        from osm_structure_sections import estimate
        # Nearby side roads bound the approach. A distant junction on the same
        # OSM way does not erase the usable approach beside the river.
        xy=[(-180,0),(-70,0),(-30,0),(30,0),(70,0),(180,0),(-70,100),(70,100),
            (-10,-50),(10,-50),(10,50),(-10,50)]
        nodes={i:(9+x/111320,y/110540) for i,(x,y) in enumerate(xy,1)}
        ways=[(10,"road",[1,2,3],dict(highway="residential")),
              (11,"road",[3,4],dict(highway="residential",bridge="yes")),
              (12,"road",[4,5,6],dict(highway="residential")),
              (13,"road",[2,7],dict(highway="residential")),
              (14,"road",[5,8],dict(highway="residential")),
              (20,"region",[9,10,11,12,9],dict(natural="water"))]
        original=deepcopy(ways)
        source,water,_=classify(ways,nodes,[])
        chains={}
        result,flat,sections=estimate(source,nodes,{},set(),set(),set(),chains,water)
        self.assertEqual(set(result),{11});self.assertEqual(set(sections),{10,12})
        self.assertEqual([s["kind"] for s in sections[10]],["ground","bridge"])
        self.assertEqual([s["kind"] for s in sections[12]],["bridge","ground"])
        self.assertEqual(sections[10][0]["points"][-1],sections[10][1]["points"][0])
        self.assertEqual(sections[12][0]["points"][-1],sections[12][1]["points"][0])
        self.assertEqual(result[11][0][0],sections[10][1]["points"][-1])
        self.assertEqual(result[11][0][-1],sections[12][0]["points"][0])
        self.assertEqual(ways,original);self.assertFalse(flat)
        self.assertTrue(all(chain in (10,11,12) for chain in chains.values()))
        self.assertEqual(estimate(source,nodes,{},set(),set(),set(),{},water),(result,flat,sections))


if __name__ == "__main__": unittest.main()
