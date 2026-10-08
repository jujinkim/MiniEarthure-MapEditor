#!/usr/bin/env python3
"""Bounded, source-preserving distribution assets (MIT). No game dependency.

Images, including GLB bufferView images, are resized without upsampling. GLB
buffers are rebuilt so original high-resolution image bytes do not ship hidden
in the BIN chunk. Existing UV/material atlases are retained. Identical encoded
payloads share a buffer range; final assets use content-addressed paths.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import struct

from PIL import Image

PROFILES = (128, 256, 512)
MAX_SOURCE = 64 * 1024 * 1024
MAX_PIXELS = 16 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def image_bytes(data, size):
    with Image.open(io.BytesIO(data)) as image:
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Texture decode exceeds 16 megapixels")
        image.load()
        image = image.convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True, compress_level=9)
        return out.getvalue(), image.width * image.height * 4 * 4 // 3


def unpack(data):
    if len(data) < 20 or data[:4] != b"glTF" or struct.unpack_from("<II", data, 4) != (2, len(data)):
        raise ValueError("Invalid GLB header")
    chunks, offset = {}, 12
    while offset < len(data):
        length, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        if length % 4 or offset + length > len(data) or kind in chunks:
            raise ValueError("Invalid GLB chunks")
        chunks[kind] = data[offset:offset + length]
        offset += length
    gltf = json.loads(chunks[0x4E4F534A])
    if len(gltf.get("buffers", [])) != 1 or "uri" in gltf["buffers"][0]:
        raise ValueError("Only self-contained GLB assets are supported")
    return gltf, chunks.get(0x004E4942, b"")


def pack(gltf, binary):
    raw = json.dumps(gltf, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    raw += b" " * (-len(raw) % 4)
    binary += b"\0" * (-len(binary) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(raw) + len(binary))
            + struct.pack("<II", len(raw), 0x4E4F534A) + raw
            + struct.pack("<II", len(binary), 0x004E4942) + binary)


def derive(data, extension, profile=256, scale=1.0):
    if profile not in PROFILES or not 0 < scale <= 16:
        raise ValueError("Choose 128/256/512 px and a bounded positive scale")
    if not data or len(data) > MAX_SOURCE:
        raise ValueError("Asset source exceeds 64 MiB or is empty")
    decoded = 0
    if extension in ("png", "webp"):
        result, decoded = image_bytes(data, profile)
        output_extension = "png"
    elif extension == "glb":
        gltf, binary = unpack(data)
        views = gltf.get("bufferViews", [])
        replacements = {}
        for item in gltf.get("images", []):
            if "uri" in item or type(item.get("bufferView")) is not int:
                raise ValueError("GLB textures must be embedded buffer views")
            index = item["bufferView"]
            if index not in range(len(views)):
                raise ValueError("Invalid embedded image view")
            view = views[index]
            start, length = view.get("byteOffset", 0), view["byteLength"]
            image, memory = image_bytes(binary[start:start + length], profile)
            replacements[index] = image
            decoded += memory
            item["mimeType"] = "image/png"
        # Geometry remains byte-identical; scaling is an authoring operation on
        # root nodes and must also be applied to the declared collision proxies.
        if scale != 1:
            roots = {node for scene in gltf.get("scenes", []) for node in scene.get("nodes", [])}
            for index in roots:
                node = gltf["nodes"][index]
                if "matrix" in node:
                    for row in range(3):
                        for col in range(4): node["matrix"][col * 4 + row] *= scale
                else:
                    node["scale"] = [v * scale for v in node.get("scale", [1, 1, 1])]
                    if "translation" in node: node["translation"] = [v * scale for v in node["translation"]]
        output, shared = bytearray(), {}
        for index, view in enumerate(views):
            start, length = view.get("byteOffset", 0), view["byteLength"]
            if view.get("buffer", 0) != 0 or start < 0 or length < 0 or start + length > len(binary):
                raise ValueError("GLB buffer view exceeds source")
            part = replacements.get(index, binary[start:start + length])
            key = digest(part)
            if key not in shared:
                output.extend(b"\0" * (-len(output) % 4))
                shared[key] = len(output)
                output.extend(part)
            view.update(buffer=0, byteOffset=shared[key], byteLength=len(part))
        gltf["buffers"][0]["byteLength"] = len(output)
        result, output_extension = pack(gltf, bytes(output)), "glb"
    else:
        raise ValueError("Choose a local GLB, PNG or WebP")
    return result, dict(source_sha256=digest(data), sha256=digest(result), profile_px=profile,
                        source_bytes=len(data), bytes=len(result), texture_memory_bytes=decoded,
                        extension=output_extension, scale=scale)


def asset(record, source, profile=256, scale=1.0):
    output, report = derive(source, Path(record["path"]).suffix[1:], profile, scale)
    record = copy.deepcopy(record)
    record["path"] = "assets/" + report["sha256"] + "." + report["extension"]
    for box in record.get("collision", []):
        for key in ("center", "size_cm"): box[key] = [round(v * scale) for v in box[key]]
    for shape in record.get("convex_collision", []):
        shape["vertices"] = [[round(v * scale) for v in point] for point in shape["vertices"]]
    return record, output, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--profile", type=int, choices=PROFILES, default=256)
    args = parser.parse_args()
    if args.destination.exists() or args.source.resolve() == args.destination.resolve():
        raise FileExistsError("Choose a new derivative path; originals are immutable")
    if args.source.stat().st_size > MAX_SOURCE: raise ValueError("Asset source exceeds 64 MiB")
    result, report = derive(args.source.read_bytes(), args.source.suffix[1:].lower(), args.profile)
    with args.destination.open("xb") as out: out.write(result)
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__": main()
