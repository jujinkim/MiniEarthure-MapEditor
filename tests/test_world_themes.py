"""World authoring invariants; no game imports or external font/network access."""
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from world_themes import compose,scene,create,PROFILES

ROOT=Path(__file__).resolve().parents[1]
LIBRARY=Path(os.environ.get('WORLD_LIBRARY',ROOT/'addons/mapkit/examples/world-library'))
SIGNS=Path(os.environ.get('WORLD_SIGN_OUTPUT',ROOT/'examples/world-signs'))

class WorldThemes(unittest.TestCase):
    def test_independent_axes(self):
        a=compose('southeast-asian',architecture='contemporary',settlement='dense',sign='arabic')
        self.assertEqual((a['architecture'],a['climate'],a['settlement'],a['sign']),('contemporary','tropical','dense','arabic'))
        self.assertEqual(compose('middle-eastern')['climate'],'temperate')
        with self.assertRaises(ValueError):compose('jungle',climate='invented')

    def test_seven_different_scenes_and_clear_route(self):
        identities=set()
        for name in PROFILES:
            doc,blobs,meta=scene(name,LIBRARY,SIGNS)
            identities.add(tuple(sorted(meta['common_assets'])))
            self.assertEqual(doc['roads'][0]['points'],[[400,0,3200],[9200,0,3200]])
            self.assertEqual(meta['image_decoded_bytes'],1048576)
            self.assertIn('map-writing',[a['id'] for a in doc['assets']])
            self.assertLess(sum(map(len,blobs.values())),200000)
        self.assertEqual(len(identities),7)

    def test_language_changes_only_owned_sign(self):
        a,ab,_=scene('southeast-asian',LIBRARY,SIGNS,sign='thai')
        b,bb,_=scene('southeast-asian',LIBRARY,SIGNS,sign='latin')
        self.assertEqual(a['placements'],b['placements'])
        self.assertEqual([x for x in a['assets'] if x['id']!='map-writing'],[x for x in b['assets'] if x['id']!='map-writing'])
        for path in ab:
            if not path.startswith('signs/'):self.assertEqual(ab[path],bb[path])
        self.assertNotEqual(a['assets'][0],b['assets'][0])

    def test_missing_and_corrupt_sign_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):scene('polar',LIBRARY,Path(tmp))
            (Path(tmp)/'latin.glb').write_bytes(b'corrupt')
            (Path(tmp)/'latin.json').write_text((SIGNS/'latin.json').read_text())
            with self.assertRaisesRegex(ValueError,'hash mismatch'):scene('polar',LIBRARY,Path(tmp))

    def test_static_sign_uv_and_embedded_image(self):
        for name in ['latin','korean','arabic','thai']:
            blob=(SIGNS/(name+'.glb')).read_bytes()
            length=struct.unpack_from('<I',blob,12)[0]
            doc=json.loads(blob[20:20+length])
            p=doc['meshes'][0]['primitives'][0]
            self.assertIn('TEXCOORD_0',p['attributes'])
            self.assertEqual(doc['images'][0]['mimeType'],'image/png')
            self.assertNotIn('uri',doc['images'][0])
            a=doc['accessors'][p['attributes']['TEXCOORD_0']];v=doc['bufferViews'][a['bufferView']]
            uv=struct.unpack_from('<8f',blob,28+length+v['byteOffset'])
            self.assertEqual(set(zip(uv[::2],uv[1::2])),{(0,0),(1,0),(1,1),(0,1)})

    def test_reproducible_new_directory_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)/'new'
            create(folder,LIBRARY,SIGNS,['polar'])
            with self.assertRaises(FileExistsError):create(folder,LIBRARY,SIGNS,['polar'])
            doc,blobs,_=scene('polar',LIBRARY,SIGNS)
            self.assertEqual(json.loads((folder/'polar/document.json').read_text()),doc)
            for path,data in blobs.items():self.assertEqual((folder/'polar'/path).read_bytes(),data)

if __name__=='__main__':unittest.main()
