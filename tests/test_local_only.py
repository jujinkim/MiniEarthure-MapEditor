"""Offline importer boundary, including direct helper calls and retired requests."""
import ast
import importlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
IMPORTERS = ROOT / "scripts/importers"
sys.path.insert(0, str(IMPORTERS))
import copernicus_dem as dem
from test_copernicus_dem import options


class LocalOnlyTests(unittest.TestCase):
    def test_retired_provider_modules_and_sdks_are_absent(self):
        self.assertFalse((IMPORTERS / "osm_download.py").exists())
        for name in ("overture_area", "overture_transportation", "overture_land_cover"):
            module = importlib.import_module(name)
            for entry in ("acquire", "remote_features", "read_features", "main"):
                self.assertFalse(hasattr(module, entry), (name, entry))
        # Attribution URLs are data; executable network imports are forbidden.
        forbidden = {"overturemaps", "urllib", "requests", "http", "socket", "boto3", "pyarrow"}
        for path in IMPORTERS.glob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                self.assertFalse({m.split(".")[0] for m in modules} & forbidden, path.name)
        self.assertNotIn("overturemaps", (ROOT / "requirements-import.txt").read_text())

    def test_dem_rejects_remote_options_and_virtual_raster_sources_before_decode(self):
        for source in ("", "https://example.invalid/tile.tif", "s3://bucket/tile.tif", "/vsicurl/https://example.invalid/tile.tif", "relative.tif"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                dem.plan(options(source))
            with patch.object(dem, "raster_dependencies", side_effect=AssertionError("must validate path first")), self.assertRaises(ValueError):
                dem.sample(source, {}, lambda *a: None)
        for key in ("allow_download", "fallback90"):
            for value in (False, True):
                with self.assertRaises(ValueError):
                    dem.plan(dict(options(), **{key: value}))
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            with self.assertRaises(ValueError):
                dem.capture({"source": {"url": "https://example.invalid/tile.tif", "bytes": 3, "etag": '"old"'}}, d/"part", d/"source", lambda *a: None)
            self.assertEqual(list(d.iterdir()), [])

    def test_dem_cli_rejects_retired_requests_without_output(self):
        with tempfile.TemporaryDirectory() as folder:
            d = Path(folder)
            for mode in ("probe", "download", "catalog", "overture", "overture-transportation", "overture-land-cover"):
                request = d/"request.json"
                request.write_text(json.dumps({"mode": mode, "url": "https://example.invalid/source"}))
                result = subprocess.run([sys.executable, "-B", str(IMPORTERS/"copernicus_dem.py"), str(request), str(d/"output"), "--layer-id", "a"*32], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid DEM mode", result.stderr)
                self.assertFalse((d/"output").exists())


if __name__ == "__main__":
    unittest.main()
