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
    parser.add_argument('--full', action='store_true', help='Also run edit/import/preview and installed-client adapter regressions')
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
            scripts += ['editor_validator', 'test_drive_validator']
        commands += [(name, [godot, '--headless', '--path', str(project), '--script', f'res://tests/{name}.gd']) for name in scripts]
        for name, command in commands:
            started = time.monotonic()
            log = args.log_dir / f'{name}.log'
            with log.open('w') as output:
                result = subprocess.run(command, stdout=output, stderr=subprocess.STDOUT, timeout=180)
            text = log.read_text()
            diagnostics = [line for line in text.splitlines() if line.startswith(('ERROR:', 'SCRIPT ERROR:', 'WARNING:'))]
            (args.log_dir / f'{name}.json').write_text(json.dumps({
                'command': command, 'exit_code': result.returncode, 'seconds': round(time.monotonic() - started, 3), 'diagnostics': diagnostics,
            }, indent=2) + '\n')
            if result.returncode or diagnostics or (name in scripts and f'{name}: PASS' not in text):
                raise SystemExit(f'{name}: FAIL; {log}')
            print(f'{name}: PASS; {log}', flush=True)


if __name__ == '__main__':
    main()
