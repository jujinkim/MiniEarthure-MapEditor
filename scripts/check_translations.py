#!/usr/bin/env python3
"""Audit shipped catalogs, source/UI entrypoints, bounded interpolation and font provenance."""
import ast
import hashlib
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
FORMAT = re.compile(r"%[-+0-9.]*[sdifxXoc]|%%")
LITERAL = r'(?:"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\')'
INVARIANTS = {"MiniEarthure", "MiniEarthure Client", "MAP EDITOR", "GeoJSON", "Godot", "DEM", "PNG", "PNG16", "TTF", "OTF", "GLB", "WebP", "A–Z", "kph", "mph", "m", "cm", "s", "h", "ms", "MB", "MiB", "X", "Y", "Z", "FWD", "RWD", "AWD", "AI", "Ctrl", "Shift", "Space", "Escape", "Enter", "Tab", "Backspace", "Delete", "Alt", "Cmd", "Meta", "Primary", "English", "한국어", "日本語"}
NON_DISPLAY = {'produced using Copernicus WorldDEM-%d © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved': 'license original', 'bilinear across full-resolution COG sample centres; local rows +northing': 'persisted sampling contract', 'source vertices before crop; target heights linearly interpolated at cuts; round once to cm': 'persisted processing contract', 'PNG columns +local x, rows +local y': 'persisted axis contract', 'fill missing original nodes before graph normalization, datum conversion and crop': 'persisted processing contract', 'Duplicate command ID: ': 'developer assertion', 'ODbL-1.0; © OpenStreetMap contributors; https://www.openstreetmap.org/copyright': 'license original', 'ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; https://docs.overturemaps.org/attribution/#buildings': 'license original', 'ODbL-1.0; © OpenStreetMap contributors; TomTom; Overture Maps Foundation; https://docs.overturemaps.org/attribution/#transportation': 'license original', 'ODbL-1.0; © OpenStreetMap contributors, Overture Maps Foundation; ESA WorldCover (CC-BY-4.0); © ESA WorldCover project 2020 / Contains modified Copernicus Sentinel data (2020) processed by ESA WorldCover consortium; https://docs.overturemaps.org/attribution/#base': 'license original', 'MapEditor startup: ': 'console log prefix', 'MapEditor icon unavailable: ': 'console log prefix', '; showing the action name.': 'console log suffix', 'Initialize godot-rust (': 'worker protocol diagnostic recognizer', 'Godot TextServer Advanced': 'saved shaping-engine identity'}
NON_DISPLAY.update({
    "Copernicus 2021 mosaic": "persisted source name",
    "Copernicus 2021 mosaic#": "persisted source path prefix",
    "EPSG:3855 / EGM2008 metres": "persisted vertical datum contract",
    "EPSG:5773 / EGM96 metres": "persisted vertical datum contract",
})
def unique(pairs):
    result = {}
    for key, value in pairs:
        assert key not in result, ("duplicate JSON key", key)
        result[key] = value
    return result

def source_keys():
    for path in (ROOT / "scripts").glob("*.gd"):
        source = path.read_text()
        patterns = [r'I18N\.t\(\s*(' + LITERAL + ')',
                    r'(?:MENU|LAYOUT)\.label\(\s*(' + LITERAL + ')',
                    r'\.(?:text|title|placeholder_text|tooltip_text|dialog_text|ok_button_text|cancel_button_text|prefix|suffix)\s*=[ \t]*(' + LITERAL + ')']
        if (ROOT / "scripts/workspace_commands.gd").exists():
            patterns += [r'(?<!commands.)(?<!registry.)\b(?:hint|row|number|text|choice|button|_label|_button|_spin|_field|_pick|opt_number|opt_choice)\([^,\n]+,\s*(' + LITERAL + ')',
                         r'\bpage\(\s*(' + LITERAL + ')',
                         r'\.register\(\s*(' + LITERAL + ')',
                         r'\.register\(\s*' + LITERAL + r',\s*(' + LITERAL + r')\s*,']
        # Catch helper-fed status/errors that do not call t() until the UI boundary.
        for line in source.splitlines():
            if line.lstrip().startswith("#"): continue
            for literal in re.findall(LITERAL, line):
                value = ast.literal_eval(literal)
                if value in NON_DISPLAY or value.startswith(("res://", "user://", "<svg ", "<path ", '" stroke=')): continue
                if value.startswith("*") and ";" in value:
                    yield path.name, value.split(";")[1].strip()
                elif re.search(r"[A-Za-z]{2,}[^\n]* [^\n]*[A-Za-z]{2,}", value):
                    yield path.name, value
        for pattern in patterns:
            for match in re.finditer(pattern, source):
                yield path.name, ast.literal_eval(match[1])
        for name in ("ERROR_MESSAGES", "BUILTIN_NAMES"):
            match = re.search(r'const ' + name + r' := (\{.*?\})', source, re.S)
            if match:
                for key in json.loads(match[1]).values(): yield path.name, key
    for path in ROOT.glob("**/*.tscn"):
        if any(part in path.parts for part in ("addons", ".godot", "tests", "docs")): continue
        for match in re.finditer(r'^(?:text|title|placeholder_text|tooltip_text) = (' + LITERAL + ')', path.read_text(), re.M):
            yield path.name, ast.literal_eval(match[1])

def main():
    packs = {p.stem: json.loads(p.read_text(), object_pairs_hook=unique) for p in (ROOT / "translations").glob("*.json")}
    base = packs["en"]["messages"]
    for code, pack in packs.items():
        assert pack["schema"] == 1
        assert set(pack["messages"]) == set(base), (code, "missing/extra keys")
        assert (ROOT / "translations" / (code + ".json")).stat().st_size <= 256 * 1024
        for key, value in pack["messages"].items():
            assert isinstance(value, str) and len(value) <= 2048, (code, key)
            if code == "template": assert value == ""
            else:
                assert value.strip(), (code, key, "empty translation")
                assert FORMAT.findall(key) == FORMAT.findall(value), (code, key, "format signature")
                if code == "en" and key.isascii(): assert key == value, key
    missing = sorted(set((path, key) for path, key in source_keys() if key not in base and key not in INVARIANTS and re.search(r"[a-zA-Z가-힣]", FORMAT.sub("", key))))
    assert not missing, "Missing display keys:\n" + "\n".join(map(str, missing))
    notice = (ROOT / "fonts/NOTICE.txt").read_text()
    assert "2.004" in notice and (ROOT / "fonts/OFL.txt").is_file()
    for path in (ROOT / "fonts").glob("*.otf"):
        assert hashlib.sha256(path.read_bytes()).hexdigest() in notice, path.name
    print(f"translations: PASS ({len(base)} keys, en/ko/ja; source/helpers/scenes/content, formats, font hashes)")
if __name__ == "__main__": main()
