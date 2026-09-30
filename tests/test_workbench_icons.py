#!/usr/bin/env python3
"""Check real SVG/import/PCK loading without native builds or user map data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--godot', required=True)
    parser.add_argument('--log-dir', required=True, type=Path)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    args.log_dir.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='mapeditor-icon-assets-') as directory:
        project = Path(directory)
        (project / 'scripts').mkdir()
        (project / 'tests').mkdir()
        shutil.copy2(source / 'scripts/workbench_style.gd', project / 'scripts/workbench_style.gd')
        shutil.copy2(source / 'tests/workbench_icon_validator.gd', project / 'tests/workbench_icon_validator.gd')
        shutil.copytree(source / 'ui/icons', project / 'ui/icons', ignore=shutil.ignore_patterns('*.import'))
        (project / 'project.godot').write_text('config_version=5\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n')

        def run(name, extra, mode='', expected_warning=False):
            start = time.monotonic()
            command = [args.godot, '--headless', '--path', str(project), *extra]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60,
                                    env={**os.environ, 'MAPEDITOR_ICON_FIXTURE': mode})
            text = result.stdout + result.stderr
            (args.log_dir / f'{name}.log').write_text(text)
            diagnostics = [line for line in text.splitlines() if line.startswith(('ERROR:', 'SCRIPT ERROR:', 'WARNING:'))]
            expected = ['WARNING: MapEditor icon unavailable: res://ui/icons/save.svg; showing the action name.'] if expected_warning else []
            assert result.returncode == 0 and diagnostics == expected, (name, text)
            if mode:
                assert f'workbench_icon_validator: PASS ({mode})' in text, (name, text)
            results.append({'name': name, 'seconds': round(time.monotonic() - start, 3),
                            'passed': True, 'expected_diagnostics': expected})
            print(f'{name}: PASS', flush=True)

        validator = ['--script', 'res://tests/workbench_icon_validator.gd']
        run('cold-source', validator, 'cold')
        # Reproduce descriptors surviving a missing compiled texture directory.
        for icon in (project / 'ui/icons').glob('*.svg'):
            Path(str(icon) + '.import').write_text('[remap]\nimporter="texture"\ntype="CompressedTexture2D"\npath="res://.godot/imported/absent.ctex"\n')
        run('stale-import', validator, 'stale')
        for descriptor in (project / 'ui/icons').glob('*.import'):
            descriptor.unlink()
        run('asset-import', ['--import'])
        run('imported-source', validator, 'imported')
        # A resource-only PCK omits every raw SVG; ID lookup must use the same IDs.
        files = [project / 'project.godot', project / 'scripts/workbench_style.gd', project / 'tests/workbench_icon_validator.gd']
        files += list((project / 'ui/icons').glob('*.import')) + list((project / '.godot/imported').glob('*.ctex'))
        pack_code = 'extends SceneTree\nfunc _initialize():\n\tvar pack := PCKPacker.new()\n\tassert(pack.pck_start("res://icons.pck") == OK)\n'
        for file in files:
            relative = file.relative_to(project).as_posix()
            pack_code += '\tassert(pack.add_file(' + json.dumps('res://' + relative) + ', ' + json.dumps(str(file)) + ') == OK)\n'
        pack_code += '\tassert(pack.flush() == OK)\n\tquit()\n'
        (project / 'pack.gd').write_text(pack_code)
        run('pack-assets', ['--script', 'res://pack.gd'])
        pack_sha = hashlib.sha256((project / 'icons.pck').read_bytes()).hexdigest()
        (project / 'ui').rename(project / 'hidden-ui')
        run('remapped-pck', ['--main-pack', str(project / 'icons.pck'), *validator], 'packed')
        (project / 'hidden-ui').rename(project / 'ui')
        for descriptor in (project / 'ui/icons').glob('*.import'):
            descriptor.unlink()
        (project / 'ui/icons/save.svg').unlink()
        run('missing-resource', validator, 'missing', True)
        (project / 'ui/icons/save.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"/>')
        run('empty-damaged-resource', validator, 'damaged', True)
        (project / 'ui/icons/save.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"/>')
        run('empty-resource-import', ['--import'])
        run('empty-imported-resource', validator, 'damaged', True)
    (args.log_dir / 'results.json').write_text(json.dumps({'checks': results, 'resource_pck_sha256': pack_sha}, indent=2) + '\n')


if __name__ == '__main__':
    main()
