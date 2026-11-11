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


if __name__ == "__main__": unittest.main()
