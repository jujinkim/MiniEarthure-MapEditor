"""Original source preservation and authored texture geometry safety."""
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "addons/mapkit/scripts/atmosphere_assets.py"

def load():
    spec=importlib.util.spec_from_file_location("atmosphere",MODULE)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class AtmosphereAssets(unittest.TestCase):
    def test_geometry_and_existing_sources_are_unchanged(self):
        module=load()
        for name in ["q01-cafe","korea-building-0"]:
            original=(ROOT/"examples/driving-school/assets"/(name+".glb")).read_bytes()
            changed,windows,_=module.style(original,name)
            self.assertTrue(windows)
            a,old=module.unpack_glb(original);b,new=module.unpack_glb(changed)
            for mesh_a,mesh_b in zip(a["meshes"],b["meshes"]):
                for pa,pb in zip(mesh_a["primitives"],mesh_b["primitives"]):
                    for attribute in ["POSITION","NORMAL"]:
                        self.assertEqual(pa["attributes"][attribute],pb["attributes"][attribute])
                    self.assertEqual(pa.get("indices"),pb.get("indices"))
            self.assertEqual(old,new[:len(old)])
            if a.get("images"):self.assertEqual(original,changed)
    def test_all_seven_profiles_and_new_destination_only(self):
        module=load()
        with tempfile.TemporaryDirectory() as temporary:
            for concept in module.CONCEPTS:
                source=ROOT/"examples/world-themes"/concept
                before=(source/"document.json").read_bytes()
                destination=Path(temporary)/concept
                doc=module.upgrade(source,destination,concept)
                self.assertEqual(doc["environment"]["concept"],concept)
                self.assertEqual(doc["recipe_version"],1)
                self.assertEqual(before,(source/"document.json").read_bytes())
                with self.assertRaises(FileExistsError):module.upgrade(source,destination,concept)
if __name__=="__main__":unittest.main()
