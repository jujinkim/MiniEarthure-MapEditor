#!/usr/bin/env python3
"""Check source startup without Godot import metadata; reuse the installed native build."""
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
    parser.add_argument('--godot', required=True)
    parser.add_argument('--log-dir', required=True, type=Path)
    parser.add_argument('--rendered', action='store_true', help='Also capture the cold standalone initial screen')
    parser.add_argument('--case', action='append', choices=['cold-source', 'cold-initial-screen', 'registered-source', 'missing-native', 'worker-cold-source', 'worker-missing-native'], help='Run only selected cases')
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    native_name = {'darwin': 'libmapkit_godot.dylib', 'win32': 'mapkit_godot.dll'}.get(sys.platform, 'libmapkit_godot.so')
    native = source / 'addons/mapkit/target/debug' / native_name
    if not native.is_file():
        raise SystemExit(f'Build MapKit first: {native}')
    data = (Path.home() / 'Library/Application Support' if sys.platform == 'darwin' else
            Path(os.environ['APPDATA']) if sys.platform == 'win32' else
            Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share'))))
    data = data / 'MiniEarthureValidation'
    data.mkdir(parents=True, exist_ok=True)
    args.log_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='mapeditor-startup-') as directory, tempfile.TemporaryDirectory(prefix='startup-', dir=data) as user:
        project = Path(directory)
        for folder in ('scripts', 'tests', 'ui'):
            shutil.copytree(source / folder, project / folder, ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('main.tscn', 'project.godot'):
            shutil.copy2(source / name, project / name)
        addon = project / 'addons/mapkit'
        for folder in ('godot', 'assets'):
            shutil.copytree(source / 'addons/mapkit' / folder, addon / folder)
        shutil.copy2(source / 'addons/mapkit/mapkit.gdextension', addon / 'mapkit.gdextension')
        (addon / 'target/debug').mkdir(parents=True)
        library = addon / 'target/debug' / native_name
        shutil.copy2(native, library)

        def run(name, mode, extra, rendered=False, expected_exit=0, expected_native_error=False):
            if args.case and name not in args.case:
                return
            user_path = Path(user) / name
            user_path.mkdir()
            (project / 'override.cfg').write_text('[application]\nconfig/use_custom_user_dir=true\nconfig/custom_user_dir_name="MiniEarthureValidation/' + user_path.relative_to(data).as_posix() + '"\n')
            env = {**os.environ, 'MAPEDITOR_STARTUP_MODE': mode, 'MAPEDITOR_STARTUP_USER': user_path.as_posix()}
            if rendered:
                env['MINIEARTHURE_INITIAL_SCREEN_CAPTURE'] = str((args.log_dir / 'initial-screen.png').resolve())
            command = [args.godot, *([] if rendered else ['--headless']), '--path', str(project), *extra]
            start = time.monotonic()
            result = subprocess.run(command, capture_output=True, text=True, timeout=60, env=env)
            text = result.stdout + result.stderr
            (args.log_dir / f'{name}.log').write_text(text)
            diagnostics = [line for line in text.splitlines() if line.startswith(('ERROR:', 'SCRIPT ERROR:', 'WARNING:'))]
            assert result.returncode == expected_exit, (name, text)
            assert 'SCRIPT ERROR:' not in text and 'WARNING:' not in text, (name, text)
            if expected_native_error:
                assert 'MapEditor startup: Cannot load the MapKit extension' in text, (name, text)
                expected = ('ERROR: GDExtension dynamic library not found:', 'ERROR: Error loading extension:', "ERROR: Can't open dynamic library:", "ERROR: Can't open GDExtension dynamic library:")
                assert diagnostics and all(line.startswith(expected) for line in diagnostics), (name, text)
            else:
                assert not diagnostics, (name, text)
            if name == 'worker-cold-source':
                assert 'Initialize godot-rust' in text and 'MapEditor startup:' not in text, (name, text)
                assert not (user_path / 'recovery').exists() and not (user_path / 'workbench.cfg').exists()
            elif name != 'worker-missing-native':
                marker = 'initial_screen_validator: PASS' if rendered else 'source_startup_validator: PASS'
                assert marker in text, (name, text)
            results.append({'name': name, 'seconds': round(time.monotonic() - start, 3), 'exit_code': result.returncode, 'expected_diagnostics': diagnostics, 'passed': True})
            print(f'{name}: PASS', flush=True)

        validator = ['--script', 'res://tests/source_startup_validator.gd']
        assert not (project / '.godot').exists()
        # No request is supplied: successful bootstrap reaches the private
        # worker's argument rejection (2), with no Editor session constructed.
        run('worker-cold-source', 'cold', ['--', '--native-import-validation'], expected_exit=2)
        run('cold-source', 'cold', validator)
        if args.rendered:
            assert not (project / '.godot/extension_list.cfg').exists()
            run('cold-initial-screen', 'cold', ['--script', 'res://tests/initial_screen_validator.gd'], rendered=True)
        # This is the exact metadata a prior import would use to register the
        # module. No full import or native rebuild is needed for the warm case.
        (project / '.godot').mkdir(exist_ok=True)
        registry = project / '.godot/extension_list.cfg'
        registry.write_text('res://addons/mapkit/mapkit.gdextension\n')
        run('registered-source', 'registered', validator)
        registry.unlink()
        library.unlink()  # Only the disposable copy is removed.
        run('missing-native', 'missing', validator, expected_native_error=True)
        run('worker-missing-native', 'missing', ['--', '--native-import-validation'], expected_exit=1, expected_native_error=True)
    (args.log_dir / 'results.json').write_text(json.dumps({'native_sha256': hashlib.sha256(native.read_bytes()).hexdigest(), 'checks': results}, indent=2) + '\n')


if __name__ == '__main__':
    main()
