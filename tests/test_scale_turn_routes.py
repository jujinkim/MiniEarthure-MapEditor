import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import scale_maps
import scale_turn_routes as turns


class TurnRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, _, cls.metadata = scale_maps.make('mixed', 288)

    def test_two_directions_round_trip_sources_unchanged(self):
        before = copy.deepcopy((self.doc, self.metadata))
        for doc, metadata in [(self.doc,self.metadata), *[(d,m) for d,_,m in
                               [scale_maps.make('mixed',2000), scale_maps.make('dense',2000)]]]:
            outbound, inbound = turns.turn_routes(doc, metadata)
            self.assertEqual(outbound['start_cm'], inbound['end_cm'])
            self.assertEqual(outbound['end_cm'], inbound['start_cm'])
            self.assertAlmostEqual(outbound['distance_m'], inbound['distance_m'])
            for route in [outbound,inbound]:
                self.assertEqual({t['direction'] for t in route['turns']}, {'left','right'})
                self.assertEqual(len(route['turns']),2)
                self.assertEqual(len(route['segments']),20)
                self.assertEqual(route['source_obstacles']['overlaps'],[])
                self.assertEqual(route['stopping']['margin_m'],4)
                for a,b in zip(route['edges'],route['edges'][1:]):
                    self.assertEqual(a['to'],b['from'])
                for a,b in zip(route['segments'],route['segments'][1:]):
                    self.assertEqual(a['end_cm'],b['start_cm'])
                    self.assertEqual(a['end_m'],b['start_m'])
        self.assertEqual((self.doc,self.metadata),before)

    def test_graph_identity_direction_order_and_road_profile(self):
        route = turns.turn_routes(self.doc,self.metadata)[0]
        edges = [(e['road_id'],e['direction']) for e in route['edges']]
        for invalid in [edges[:1], [*edges[:-1],edges[0]],
                        [edges[0],edges[2],edges[1],edges[3]],
                        [edges[0],(edges[1][0],-1),*edges[2:]],
                        [(edges[0][0],0),*edges[1:]]]:
            with self.assertRaises(ValueError): turns.authored_turn(self.doc,self.metadata,'bad',invalid)
        doc = copy.deepcopy(self.doc)
        edge = next(r for r in doc['roads'] if r['id']==edges[1][0])
        old_node = next(n for n in doc['nodes'] if n['id']==edge['from'])
        doc['nodes'].append(dict(old_node,id='same-coordinate-different-node'))
        edge['from'] = 'same-coordinate-different-node'
        with self.assertRaisesRegex(ValueError,'disconnected'):
            turns.authored_turn(doc,self.metadata,'bad',edges)
        for key,value in [('widths_cm',[399]),('kind','bridge'),('surfaces',['gravel'])]:
            doc = copy.deepcopy(self.doc)
            next(r for r in doc['roads'] if r['id']==edges[0][0])[key] = value
            with self.assertRaisesRegex(ValueError,'flat straight'):
                turns.authored_turn(doc,self.metadata,'bad',edges)

    def test_swept_corner_and_stopping_obstacles(self):
        route = turns.turn_routes(self.doc,self.metadata)[0]
        # Use locations inside the swept square, away from its centreline.
        for box in [route['source_obstacles']['swept_bounds_cm'][4],route['stopping']['bounds_cm'][-1]]:
            doc = copy.deepcopy(self.doc)
            x,z = box[2]-10,box[3]-10
            doc['zones'].append(dict(id='swept-obstacle',polygon=[[x-2,z-2],[x+2,z-2],[x+2,z+2],[x-2,z+2]]))
            with self.assertRaisesRegex(ValueError,'swept obstacle'):
                turns.turn_routes(doc,self.metadata)

    def test_union_requires_every_interior_patch_not_just_corners(self):
        self.assertFalse(turns.covered([0,0,10,10],[[0,0,4,10],[6,0,10,10]]))
        self.assertTrue(turns.covered([0,0,10,10],[[0,0,5,10],[5,0,10,10]]))


if __name__=='__main__': unittest.main()
