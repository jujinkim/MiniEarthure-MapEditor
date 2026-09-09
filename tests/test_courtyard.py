import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/importers"))
from courtyard_fixture import xml
from osm_fixture import pbf
from osm_extract import parse,finish,LICENSE
from geojson import convert
class CourtyardTests(unittest.TestCase):
 def test_xml_pbf_courtyard_parity_counts_and_originals(self):
  raw=xml().encode()
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'synthetic.pbf';binary=pbf(path,xml())
   a,counts=parse(raw,'osm');b,pbf_counts=parse(binary,'pbf')
   self.assertEqual(a,b);self.assertEqual(counts,pbf_counts);self.assertEqual(counts['inner_rings'],1)
   layer=finish(convert(a,'synthetic',LICENSE,layer_id='c'*32,source_bytes=binary,coordinates=dict(mode='wgs84-utm',origin=[9,55],local_origin_m=[512,512])),counts)
   self.assertEqual(len(layer.patches),1);self.assertEqual(len(layer.patches[0]['after']['holes']),1)
   self.assertEqual(layer.point_count,8);self.assertEqual(layer.patches[0]['after']['roof'],'flat')
   self.assertEqual(path.read_bytes(),binary);self.assertTrue(any('recipe 5' in x for x in layer.warnings))
if __name__=='__main__':unittest.main()
