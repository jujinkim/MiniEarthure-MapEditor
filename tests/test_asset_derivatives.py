import io
import json
from pathlib import Path
import sys
import unittest

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from asset_derivatives import derive, pack, unpack, asset, asset_bundle


class AssetDerivativesTest(unittest.TestCase):
    def test_lod_pair_scale_hash_and_source_preservation(self):
        model = dict(asset={"version":"2.0"}, buffers=[dict(byteLength=0)],
            scenes=[dict(nodes=[0])], nodes=[dict(translation=[1,2,3],scale=[2,1,1])])
        near = pack(model, b"")
        model["nodes"][0] = dict(matrix=[1,0,0,0,0,1,0,0,0,0,1,0,4,5,6,1])
        far = pack(model, b"")
        record = dict(path="near.glb", distant_path="far.glb", collision=[dict(center=[100,200,300],size_cm=[200,400,600])])
        result, payloads, report = asset_bundle(record, {"near.glb":near,"far.glb":far},512,.125)
        self.assertEqual(record["path"],"near.glb")
        self.assertEqual(result["collision"][0]["center"],[12,25,38])
        self.assertEqual(unpack(payloads[result["path"]])[0]["nodes"][0]["translation"],[.125,.25,.375])
        self.assertEqual(unpack(payloads[result["distant_path"]])[0]["nodes"][0]["matrix"][12:15],[.5,.625,.75])
        self.assertEqual(report["distant"]["scale"],.125)
        with self.assertRaises(ValueError): asset(record,near)

    def test_embedded_texture_rebuilt_deduplicated_and_source_immutable(self):
        stream = io.BytesIO()
        Image.new("RGBA", (1024, 512), (27, 53, 82, 255)).save(stream, format="PNG")
        picture = stream.getvalue()
        original = pack(dict(asset={"version":"2.0"}, buffers=[dict(byteLength=len(picture))],
            bufferViews=[dict(buffer=0, byteOffset=0, byteLength=len(picture))]*2,
            images=[dict(bufferView=0, mimeType="image/png"),dict(bufferView=1,mimeType="image/png")]), picture)
        before = bytes(original)
        result, report = derive(original, "glb")
        self.assertEqual(original, before)
        self.assertEqual(derive(original, "glb"), (result, report))
        gltf, binary = unpack(result)
        self.assertEqual(gltf["bufferViews"][0], gltf["bufferViews"][1])
        view = gltf["bufferViews"][0]
        self.assertEqual(Image.open(io.BytesIO(binary[:view["byteLength"]])).size, (256,128))
        self.assertLess(len(result), len(original))
        self.assertNotIn(picture, result)

    def test_profiles_no_upsampling_and_rejection(self):
        stream = io.BytesIO(); Image.new("RGB",(32,16)).save(stream,format="PNG")
        for profile in (128,256,512):
            result, _ = derive(stream.getvalue(),"png",profile)
            self.assertEqual(Image.open(io.BytesIO(result)).size,(32,16))
        with self.assertRaises(ValueError): derive(stream.getvalue(),"png",2048)


if __name__ == "__main__": unittest.main()
