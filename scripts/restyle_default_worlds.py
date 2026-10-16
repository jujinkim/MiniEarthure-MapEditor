#!/usr/bin/env python3
"""Create separate bright-sepia default worlds without reauthoring their layout.

Only bundled authored models are replaced. User imports, terrain, roads, placements,
collision proxies, routes and environmental authority remain exactly as authored.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
from default_worlds import World, THEMES, canonical


def material_names(data):
    size=struct.unpack_from('<I',data,12)[0]
    return [m.get('name','') for m in json.loads(data[20:20+size])['materials']]


def restyle(source, destination, theme, kit, cli):
    original=source/theme
    target=destination/theme
    package=destination/(theme+'.memap')
    if target.exists() or package.exists():
        raise FileExistsError('Use a fresh destination; original worlds are immutable')
    document=json.loads((original/'document.json').read_bytes())
    meta=json.loads((original/'region.json').read_bytes())
    library={record['id']:(record,files) for record,files,_ in World(theme,kit).library.values()}
    updated=copy.deepcopy(document);payloads={};replaced=set()
    lit={binding['asset_id'] for binding in document.get('environment',{}).get('lights',[])}
    for asset in updated['assets']:
        if asset['id'] not in library:continue
        record,files=library[asset['id']]
        # Solid geometry is unchanged; root beds stay exactly as in the old map.
        for field in ('collision','convex_collision'):
            old=asset.get(field,[]);new=record.get(field,[])
            buried=field=='collision' and old and all(c['center'][1]+c['size_cm'][1]/2<0 for c in old)
            if canonical(old)!=canonical(new) and not buried:
                raise ValueError('Physical model changed: '+asset['id']+' '+field)
        if asset['id'] in lit:
            for field in ('path','distant_path'):
                if material_names((original/asset[field]).read_bytes())!=material_names(files[record[field]]):
                    raise ValueError('Light material indices changed: '+asset['id'])
        for field in ('path','distant_path'):
            asset[field]=record[field]
        payloads.update(files);replaced.add(asset['id'])
    # Check the whole document, not a hand-picked subset of physics fields.
    invariant=copy.deepcopy(updated)
    for old,new in zip(document['assets'],invariant['assets']):
        for field in ('path','distant_path'):
            if field in old:new[field]=old[field]
    assert invariant==document, 'Restyling may only change model paths'
    if not replaced:raise ValueError('No built-in authored models in source')
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'.gdignore').write_text('')
    target.mkdir()
    # Copy non-model inputs byte for byte and only the referenced model payloads.
    for path in original.rglob('*'):
        if path.is_file() and 'assets' not in path.relative_to(original).parts:
            out=target/path.relative_to(original);out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,out)
    for asset in updated['assets']:
        for field in ('path','distant_path'):
            if not asset.get(field):continue
            path=asset[field];out=target/path;out.parent.mkdir(parents=True,exist_ok=True)
            out.write_bytes(payloads[path] if path in payloads else (original/path).read_bytes())
    (target/'document.json').write_bytes(canonical(updated))
    meta['authoring']['style']='bright-sepia-low-poly'
    meta['authoring']['source_document_sha256']=hashlib.sha256((original/'document.json').read_bytes()).hexdigest()
    meta['authoring']['model_sources_sha256']=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((kit/'scripts').glob('*assets.py')))).hexdigest()
    (target/'region.json').write_bytes(canonical(meta))
    # Refresh the compiler fingerprint through the current compiler, then prove
    # that every generated physical field is byte-equivalent to the source.
    if updated.get('assembled_track'):
        compiled=target/'recompiled.json'
        subprocess.run([str(cli.resolve()),'compose-world',str(target/'document.json'),
            str(target/'track-source.json'),str(target/'surface-attachments.json'),str(compiled)],check=True)
        candidate=json.loads(compiled.read_bytes());checked=copy.deepcopy(candidate)
        checked['assembled_track']['generator_fingerprint']=updated['assembled_track']['generator_fingerprint']
        if checked!=updated:raise ValueError('Current compiler changes physical geometry; cannot restyle')
        compiled.replace(target/'document.json')
    subprocess.run([str(cli.resolve()),'pack',str(target),str(package)],check=True)
    # No regeneration of road geometry: validate the new model/cell bindings.
    audit=subprocess.run([str(cli.resolve()),'validate-cells',str(package)],capture_output=True,text=True,check=True)
    cells=json.loads(audit.stdout)
    meta['validation']['native_generated_cells']=len(cells)
    meta['validation']['cell_hashes_sha256']=hashlib.sha256(canonical(cells)).hexdigest()
    (target/'region.json').write_bytes(canonical(meta))
    ids=[key for key in THEMES if (destination/(key+'.memap')).is_file()]
    (destination/'default-worlds.json').write_bytes(canonical(dict(format_version=1,maps=ids,owner='MapEditor')))
    print('RESTYLED_WORLD',theme,'models',len(replaced),'cells',len(cells),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','destination'):p.add_argument(name,type=Path)
    p.add_argument('--theme',choices=THEMES,required=True)
    p.add_argument('--kit',type=Path,required=True);p.add_argument('--cli',type=Path,required=True)
    a=p.parse_args();restyle(a.source,a.destination,a.theme,a.kit,a.cli)
