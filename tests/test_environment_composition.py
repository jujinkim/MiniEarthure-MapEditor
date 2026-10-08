"""Spatial acceptance: complete assemblies and geometry, not prop counts."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from environment_generation import Generator, GenerationRequest, GenerationContext, PROFILES, new_context, write_result, generate
from environment_layout import polygon, digest
from environment_metrics import measure, topology

KIT=Path(__file__).resolve().parents[1]/'addons/mapkit'


def layout(theme,seed=9026,density=1):
    profile=PROFILES[theme]
    request=GenerationRequest('new',theme,seed,[0,0,profile.minimum_size_m[0]*100,profile.minimum_size_m[1]*100],density)
    g=Generator(request,new_context(request),KIT)
    # This suite measures layout. The terrain/seam, PNG and native package
    # suites exercise full serialization separately, without repeating 21 bakes.
    for stage in ('water','districts','road','approaches','driving','fixed','facilities','details','nature'):
        getattr(g,stage+'_stage')()
    g.sites.sort(key=lambda s:s['id'])
    return g


class CompositionTests(unittest.TestCase):
    def test_seven_themes_three_seeds_actual_geometry(self):
        for seed in (9026,17,410):
            for theme in PROFILES:
                with self.subTest(theme=theme,seed=seed):
                    g=layout(theme,seed);report=g.quality_stage();m=report['metrics']
                    self.assertEqual(report['errors'],[])
                    self.assertEqual(set(report['required']),set(report['present']))
                    self.assertTrue(m['staging_straights'])
                    self.assertLessEqual(m['max_road_grade'],.1205)
                    self.assertTrue(m['cost_cells'])
                    if g.profile.road_mode=='loop':
                        self.assertEqual(m['road_graph']['cycle_rank'],1)
                        self.assertEqual(m['road_graph']['dead_ends'],3)
                        self.assertGreaterEqual(m['natural_land_fraction'],.85)
                    else:
                        self.assertGreaterEqual(m['core_land_fraction'],.20)
                        self.assertLessEqual(m['core_land_fraction'],.35)
                        self.assertTrue(m['parcel_occupancy'])

    def test_density_preserves_remote_topology_required_sites_and_open_space(self):
        a=layout('deep-forest',density=.1);b=layout('deep-forest',density=2)
        self.assertEqual(a.doc['roads'],b.doc['roads'])
        self.assertEqual([s['id'] for s in a.sites],[s['id'] for s in b.sites])
        for g in (a,b): self.assertFalse(g.quality_stage()['errors'])
        self.assertGreater(len(b.doc['placements']),len(a.doc['placements']))

    def test_metric_rejects_real_missing_access_and_added_branch(self):
        g=layout('deep-forest');site=next(s for s in g.sites if s['group']=='campground')
        site['entrance']=site['entrance'].buffer(-100)
        self.assertTrue(any('Entrance' in e for e in measure(g)[1]))
        clone=copy.deepcopy(g.doc['roads'][0]);clone['id']='illegal-extra-loop'
        g.doc['roads'].append(clone)
        self.assertEqual(topology(g.doc)[0]['cycle_rank'],2)

    def test_nonrectangular_loop_and_shared_asset_silhouettes(self):
        g=layout('red-canyon')
        self.assertLess(len(g.doc['roads']),20)
        self.assertTrue(any(len(r['points'])>10 for r in g.doc['roads']))
        for family in ('home','market','lodge','hall','boulder'):
            records=[g.modules['environment-'+family+'-'+str(i)] for i in range(3)]
            self.assertEqual(len({digest(data) for _,data in records}),3)
            self.assertTrue(all(record['collision'] or record.get('convex_collision') for record,_ in records))
            for record,_ in records:
                for convex in record.get('convex_collision',[]):
                    vertices=convex['vertices'];centre=[sum(p[i] for p in vertices)/len(vertices) for i in range(3)]
                    for face in convex['faces']:
                        a,b,c=[vertices[i] for i in face]
                        u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
                        normal=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
                        self.assertGreater(sum(normal[i]*(a[i]-centre[i]) for i in range(3)),0)

    def test_atomic_boundary_manual_edit_and_deletion_survive_multiple_reruns(self):
        p=PROFILES['village'];request=GenerationRequest('new','village',9026,[0,0,112000,96000],.2)
        result=generate(request,new_context(request),KIT)
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'map';write_result(result,source)
            site=next(s for s in result.metadata['sites'] if s['group']=='housing' and s['required'])
            document=copy.deepcopy(result.document)
            member=next(p for p in document['placements'] if p['id']==site['objects'][0])
            member['yaw_offset_mdeg']+=1000
            removed=next(p for p in document['placements'] if p['id']==site['objects'][1])
            document['placements'].remove(removed)
            before=[copy.deepcopy(p) for p in document['placements'] if p['id'].startswith(site['id']+'-')]
            fill=replace(request,mode='fill')
            for _ in range(3):
                document=generate(fill,GenerationContext.from_document(document,str(source)),KIT).document
                self.assertTrue(all(p in document['placements'] for p in before))
                self.assertNotIn(removed['id'],[p['id'] for p in document['placements']])
            # A boundary through a compound retains members on BOTH sides.
            other=next(s for s in result.metadata['sites'] if s['group']=='school')
            cut=round(other['anchor'][0]*100)
            partial=replace(fill,bounds_cm=[0,0,cut,96000])
            output=generate(partial,GenerationContext.from_document(result.document,str(source)),KIT)
            members=[p for p in result.document['placements'] if p['id'].startswith(other['id']+'-')]
            self.assertTrue(all(p in output.document['placements'] for p in members))


if __name__=='__main__': unittest.main()
