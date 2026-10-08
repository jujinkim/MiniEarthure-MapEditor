import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from environment_generation import *

KIT=Path(__file__).resolve().parents[1]/'addons/mapkit'


class EnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)/'world'
        cls.request=GenerationRequest('new','village',9026,[0,0,112000,96000],.25)
        cls.result=generate(cls.request,new_context(cls.request),KIT)
        write_result(cls.result,cls.root)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def test_reproducible_metres_required_groups_and_seams(self):
        other=generate(self.request,new_context(self.request),KIT)
        self.assertEqual(other.document,self.result.document)
        self.assertEqual(other.assets,self.result.assets)
        self.assertFalse(other.diagnostics['errors'])
        self.assertEqual(other.diagnostics['counts']['heightmaps'],1050)
        a,b=other.document['heightmaps'][:2]
        with Image.open(io.BytesIO(other.assets[a['path']])) as im: right=[im.getpixel((16,y)) for y in range(17)]
        with Image.open(io.BytesIO(other.assets[b['path']])) as im: left=[im.getpixel((0,y)) for y in range(17)]
        self.assertEqual(right,left)
        self.assertTrue(any(p.get('yaw_offset_mdeg') for p in other.document['placements']))
        self.assertTrue(all(s['access']<150 for s in other.metadata['sites']))
        for feature in other.document['gimmicks']:
            self.assertGreater(len(set(tuple(v) for v in feature['parts'][0]['vertices'])),4)

    def test_rerun_no_duplicates_manual_edit_deletion_and_boundary(self):
        request=GenerationRequest('fill','village',9026,self.request.bounds_cm,.25)
        first=generate(request,GenerationContext.from_document(self.result.document,str(self.root)),KIT)
        again=generate(request,GenerationContext.from_document(first.document,str(self.root)),KIT)
        self.assertEqual(again.patches,[])
        document=copy.deepcopy(again.document)
        changed=next(p for p in document['placements'] if 10000<p['position'][0]<50000 and 10000<p['position'][2]<80000)
        changed['yaw_offset_mdeg']+=1234
        deleted=next(p for p in document['placements'] if p['id']!=changed['id'] and p['position'][0]<50000)
        document['placements'].remove(deleted)
        request=GenerationRequest('fill','village',9026,[0,0,56000,96000],.25)
        partial=generate(request,GenerationContext.from_document(document,str(self.root)),KIT)
        self.assertIn(changed,partial.document['placements'])
        self.assertNotIn(deleted['id'],[p['id'] for p in partial.document['placements']])
        fixed={p['id']:p for p in document['placements'] if p['position'][0]>=49600}
        self.assertTrue(all(p in partial.document['placements'] for p in fixed.values()))
        self.assertEqual(document['roads'],partial.document['roads'])
        self.assertEqual(document['heightmaps'],partial.document['heightmaps'])
        self.assertEqual(len({p['id'] for p in partial.document['placements']}),len(partial.document['placements']))

    def test_semantic_infill_holes_protection_and_exactly_once_scale(self):
        request=GenerationRequest('fill','village',55,[0,0,16000,16000],.5)
        doc=empty('osm-environment-fixture',16000,3200)
        doc.update(free_roam=True,surface_areas=[],water_bodies=[],gimmicks=[])
        road(doc,'fixed',[[0,0,8000],[16000,0,8000]],width=100)
        region=dict(id='r',source_id='relation/71',landuse='residential',protected=False,polygon=[[0,0],[16000,0],[16000,16000],[0,16000]],holes=[[[7000,9000],[9000,9000],[9000,12000],[7000,12000]]])
        protected=dict(id='p',source_id='way/72',landuse='nature_reserve',protected=True,polygon=[[0,0],[5000,0],[5000,7000],[0,7000]],holes=[])
        doc['attributions'].append(dict(source='osm',license='ODbL',notice=json.dumps(dict(adapter='osm-extract-v1',authored_units=dict(source_denominator=8),authored_regions=[region,protected]))))
        ctx=GenerationContext.from_document(doc)
        result=generate(request,ctx,KIT)
        self.assertEqual(result.document['roads'],doc['roads'])
        self.assertTrue(result.document['placements'])
        self.assertEqual(ctx.source_denominator,8)
        self.assertTrue(all(a['id'].endswith('-env-8-256') for a in result.document['assets']))
        self.assertTrue(all(r['scale']<=3/8 for r in result.diagnostics['assets'].values()))
        hole=Polygon([(p[0]/100,p[1]/100) for p in region['holes'][0]])
        generator=Generator(request,ctx,KIT)
        assets={a['id']:a for a in result.document['assets']}
        for p in result.document['placements']:
            area=generator.footprint(assets[p['asset_id']],(p['position'][0]/100,p['position'][2]/100),p['yaw_offset_mdeg']/1000)
            self.assertFalse(area.intersects(polygon(protected)))
            self.assertFalse(area.intersects(hole))
        unknown=generate(request,GenerationContext(copy.deepcopy(doc),regions=[],source_denominator=8),KIT)
        self.assertFalse(unknown.document['placements'])
        self.assertTrue(unknown.document['surface_areas'])

    def test_rotation_footprint_and_independent_random_streams(self):
        g=Generator(self.request,new_context(self.request),KIT)
        asset=dict(id='box',collision=[dict(center=[0,100,0],size_cm=[400,200,100])])
        a=g.footprint(asset,(10,10),0);b=g.footprint(asset,(10,10),45)
        self.assertAlmostEqual(a.area,b.area)
        self.assertFalse(a.equals(b))
        a=rng(8,'region-a');b=rng(8,'region-b')
        sample=[a.random() for _ in range(5)]
        for _ in range(100): b.random()
        replay=rng(8,'region-a')
        self.assertEqual(sample,[replay.random() for _ in range(5)])
        self.assertNotEqual(rng(8,'region-a').random(),rng(8,'region-b').random())


if __name__=='__main__': unittest.main()
