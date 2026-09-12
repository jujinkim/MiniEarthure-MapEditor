"""Routes must follow connected, obstacle-free authored roads in fixed packages."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import scale_maps
import scale_routes


class ScaleRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc, cls.payloads, cls.metadata = scale_maps.make('mixed',288)

    def test_corridors_have_exact_density_graph_and_grade_evidence(self):
        before = copy.deepcopy((self.doc,self.metadata))
        routes = scale_routes.routes(self.doc,self.metadata)
        self.assertEqual(len(routes),7)
        for route in routes:
            actual = {kind for s in route['segments'] for kind in s['adjacent_kinds']}
            expected = set() if route['id']=='bridge-grades' else set(route['id'].split('-'))
            self.assertEqual(actual,expected)
            for a,b in zip(route['segments'],route['segments'][1:]):
                self.assertEqual(a['end_cm'],b['start_cm'])
            self.assertEqual(route['source_obstacles']['overlaps'],[])
        self.assertEqual(routes[-1]['expected_height_range_m'],3)
        self.assertEqual(routes[-1]['start_cm'],[1600,0,800])
        self.assertEqual(routes[-1]['end_cm'],[27200,0,800])
        self.assertEqual((self.doc,self.metadata),before)

    def test_disconnected_node_and_road_gap_are_rejected(self):
        doc = copy.deepcopy(self.doc)
        road = next(r for r in doc['roads'] if r['id']=='grid-ns-3-0')
        road['to'] = road['from']
        with self.assertRaisesRegex(ValueError,'endpoint'):scale_routes.routes(doc,self.metadata)
        with self.assertRaisesRegex(ValueError,'disconnected'):
            scale_routes.corridor(self.doc,self.metadata,'gap',['grid-ns-3-0','grid-ns-3-2'])

    def test_rotated_obstacle_tree_envelope_and_bad_density_reject(self):
        for kind in ['placement','zone','terrain']:
            doc = copy.deepcopy(self.doc)
            road = next(r for r in doc['roads'] if r['id']=='grid-ns-3-0')
            x,_,z=road['points'][0]
            if kind=='placement':
                doc['placements'].append(dict(id='blocked',asset_id='q03-home-0',position=[x,0,z+1600],quarter_turns=1))
            elif kind=='zone':
                doc['zones'].append(dict(id='blocked',polygon=[[x-200,z],[x+200,z],[x+200,z+2000],[x-200,z+2000]]))
            else:
                doc['heightmaps'].append(dict(cell=dict(x=x//1600,y=z//1600)))
            with self.assertRaisesRegex(ValueError,'obstacle'):scale_routes.routes(doc,self.metadata)
        metadata=copy.deepcopy(self.metadata)
        for lot in metadata['lots']:lot['kind']='urban'
        with self.assertRaisesRegex(ValueError,'density'):scale_routes.routes(self.doc,metadata)

    def test_native_record_pairing_payloads_and_semantics(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            source=root/'source'
            scale_maps.create(source,'mixed',288)
            metadata=json.loads((source/'scale.json').read_text())
            records=[dict(sha256=value) for value in metadata['source_hashes'].values()]
            names=list(metadata['source_hashes'])
            index=dict(authoring_source=0,records=records,payloads={name:i for i,name in enumerate(names) if i},
                       side_cells=16,world_content_hash='test-index-identity')
            raw=json.dumps(index).encode()
            package=root/'fixture.mkregions'
            package.write_bytes(b'MKREGN01'+struct.pack('<Q',len(raw))+hashlib.sha256(raw).digest()+raw)
            output=root/'routes.json'
            scale_routes.create(source,package,output,source)
            with self.assertRaises(FileExistsError):scale_routes.create(source,package,output,source)
            (source/'document.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'source identity'):
                scale_routes.create(source,package,root/'bad.json',source)
            with self.assertRaisesRegex(ValueError,'authoring source'):
                scale_routes.package_identity(package,metadata['source_hashes'],source)
            altered=copy.deepcopy(self.doc)
            altered['roads'][0]['points'].reverse()
            self.assertNotEqual(scale_routes.document_semantics(self.doc),scale_routes.document_semantics(altered))


if __name__=='__main__':unittest.main()
