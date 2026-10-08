import io
import json
from pathlib import Path
import sys
import unittest

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from asset_derivatives import derive, pack, unpack


class AssetDerivativesTest(unittest.TestCase):
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
