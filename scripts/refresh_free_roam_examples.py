#!/usr/bin/env python3
"""Republish bundled Free Roam source into a new directory, preserving originals."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

IDS = ('village', 'neon-harbor', 'deep-forest', 'red-canyon', 'snow-mountain', 'machine-factory', 'sky-park', 'physics-test')

def refresh(source: Path, destination: Path):
    if destination.exists():
        raise ValueError(f'Refusing existing destination: {destination}')
    documents = {}
    for ident in IDS:
        document = json.loads((source / ident / 'document.json').read_text())
        if document.get('courses') or document.get('assembled_track'):
            raise ValueError(f'Refusing race source: {ident}')
        document['free_roam'] = True
        document['revision'] += 1
        document['provenance'].update(build_id='free-roam-world-v1', last_edited='2026-10-02T00:00:00Z')
        documents[ident] = document
    shutil.copytree(source, destination)
    for ident, document in documents.items():
        path = destination / ident / 'document.json'
        path.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n')
        metadata = path.parent / 'driving.json'
        if metadata.exists():
            value = json.loads(metadata.read_text())
            value.setdefault('source_files', {})['document.json'] = hashlib.sha256(path.read_bytes()).hexdigest()
            metadata.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return len(documents)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(f'Republished {refresh(args.source, args.destination)} Free Roam sources; originals preserved')
