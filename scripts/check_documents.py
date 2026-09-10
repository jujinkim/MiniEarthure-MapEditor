#!/usr/bin/env python3
"""Run public Editor document checks with copied sources and isolated user data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', default='godot')
    parser.add_argument('--log-dir', type=Path, required=True)
    parser.add_argument('--import-python', default=sys.executable, help='Python with optional projection requirements for geographic validator')
    parser.add_argument('--full', action='store_true', help='Also run edit/import/preview and installed-client adapter regressions')
    parser.add_argument('--script', action='append', help='Run only named test scripts (repeatable)')
    parser.add_argument('--resource-pack', action='store_true', help='Build host resource PCK and run scripts with loose product scripts hidden; not a native distribution')
    parser.add_argument('--rendered', action='store_true', help='Run behavior on the native display; import remains headless')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    godot = shutil.which(args.godot)
    if not godot:
        raise SystemExit('Godot executable not found')
    version = subprocess.check_output([godot, '--version'], text=True).strip()
    if not version.startswith('4.7.2.stable.'):
        raise SystemExit(f'Godot 4.7.2 required; found {version}')
    native_name = {'darwin': 'libmapkit_godot.dylib', 'win32': 'mapkit_godot.dll'}.get(sys.platform, 'libmapkit_godot.so')
    native = root / 'addons/mapkit/target/debug' / native_name
    if not native.is_file():
        raise SystemExit(f'Build the public MapKit Godot binding first: {native}')
    data_root = (Path.home() / 'Library/Application Support' if sys.platform == 'darwin' else
                 Path(os.environ.get('APPDATA', str(Path.home() / 'AppData/Roaming'))) if sys.platform == 'win32' else
                 Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))))
    data_root = data_root / 'MapEditorDocumentValidation'
    data_root.mkdir(parents=True, exist_ok=True)
    args.log_dir.mkdir(parents=True, exist_ok=True)
    (args.log_dir / 'environment.json').write_text(json.dumps({
        'godot': version, 'platform': sys.platform, 'native_sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
        'source_files': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for directory in ('scripts', 'tests') for p in (root / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts},
    }, indent=2) + '\n')
    with tempfile.TemporaryDirectory(prefix='mapeditor-documents-') as directory, tempfile.TemporaryDirectory(prefix='run-', dir=data_root) as user_directory:
        project = Path(directory)
        for folder in ('scripts', 'tests'):
            shutil.copytree(root / folder, project / folder, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(root / 'main.tscn', project / 'main.tscn')
        shutil.copy2(root / 'project.godot', project / 'project.godot')
        addon = project / 'addons/mapkit'
        addon.mkdir(parents=True)
        shutil.copytree(root / 'addons/mapkit/godot', addon / 'godot')
        shutil.copy2(root / 'addons/mapkit/mapkit.gdextension', addon / 'mapkit.gdextension')
        (addon / 'target/debug').mkdir(parents=True)
        shutil.copy2(native, addon / 'target/debug' / native_name)
        (project / 'override.cfg').write_text('[application]\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="MapEditorDocumentValidation/' + Path(user_directory).name + '"\n')
        (project / 'check_user_path.gd').write_text('extends SceneTree\nfunc _initialize():\n\tif OS.get_user_data_dir().replace("\\\\", "/") != ' + json.dumps(Path(user_directory).as_posix()) + ':\n\t\tpush_error("User-data isolation failed")\n\t\tquit(1)\n\telse: quit(0)\n')
        commands = [('import', [godot, '--headless', '--import', '--frame-delay', '1000', '--path', str(project)]),
                    ('user-path', [godot, '--headless', '--path', str(project), '--script', 'res://check_user_path.gd'])]
        scripts = ['document_history_validator', 'document_recovery_validator']
        if args.full:
            scripts += ['editor_ux_validator', 'editor_validator', 'test_drive_validator', 'workbench_validator', 'authoring_validator', 'authoring_safety_validator', 'preview_export_validator', 'import_layer_validator', 'import_job_validator', 'projection_validator', 'heightmap_import_validator', 'osm_import_validator', 'osm_structures_validator', 'osm_multipolygon_validator', 'download_validator', 'overture_validator', 'area_selection_validator', 'osm_area_validator', 'osm_stream_validator', 'overture_geometry_validator', 'overture_vertical_validator', 'overture_transportation_validator', 'overture_land_cover_validator', 'dem_validator', 'dem_mosaic_validator']
        if args.script:
            scripts = args.script
        pack_args = []
        if args.resource_pack:
            shutil.copy2(root / 'export_presets.cfg', project / 'export_presets.cfg')
            preset = {'win32': 'Windows', 'darwin': 'Mac development'}.get(sys.platform, 'Linux')
            if sys.platform == 'darwin':
                with (project / 'export_presets.cfg').open('a') as presets:
                    presets.write('\n[preset.2]\nname="Mac development"\nplatform="macOS"\nrunnable=true\nexport_filter="all_resources"\ninclude_filter="scripts/importers/*.py"\nexclude_filter="tests/*,addons/mapkit/tests/*"\nscript_export_mode=2\n[preset.2.options]\nbinary_format/architecture="arm64"\n')
            artifact = project / 'editor.pck'
            commands.append(('resource-pack', [godot, '--headless', '--path', str(project), '--export-pack', preset, str(artifact)]))
            pack_args = ['--main-pack', str(artifact)]
        commands += [(name, [godot, *([] if args.rendered else ['--headless']), '--path', str(project), *pack_args,
                             '--script', str(project / 'tests' / (name + '.gd')) if args.resource_pack else f'res://tests/{name}.gd']) for name in scripts]
        for name, command in commands:
            started = time.monotonic()
            log = args.log_dir / f'{name}.log'
            with log.open('w') as output:
                result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=180, env={**os.environ, "MAPEDITOR_TEST_IMPORT_PYTHON": args.import_python})
            text = log.read_text()
            diagnostics = [line for line in text.splitlines() if line.startswith(('ERROR:', 'SCRIPT ERROR:', 'WARNING:'))]
            (args.log_dir / f'{name}.json').write_text(json.dumps({
                'command': command, 'exit_code': result.returncode, 'seconds': round(time.monotonic() - started, 3), 'diagnostics': diagnostics,
            }, indent=2) + '\n')
            if result.returncode or diagnostics or (name in scripts and f'{name}: PASS' not in text):
                raise SystemExit(f'{name}: FAIL; {log}')
            if name == 'resource-pack':
                (args.log_dir / 'resource-artifact.json').write_text(json.dumps({'bytes': artifact.stat().st_size,
                    'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(), 'scope': 'compiled host resource pack; no native distribution'}, indent=2) + '\n')
                (project / 'scripts').rename(project / 'hidden-loose-scripts')
                (project / 'main.tscn').rename(project / 'hidden-main.tscn')
            print(f'{name}: PASS; {log}', flush=True)


if __name__ == '__main__':
    main()
