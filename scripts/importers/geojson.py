#!/usr/bin/env python3
"""Explicit local-metre GeoJSON adapter. Emits a new layer; never edits source."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

MAX_BYTES = 32 * 1024 * 1024


def convert(value, source, license_name):
    if value.get('type') != 'FeatureCollection':
        raise ValueError('expected FeatureCollection')
    patches, warnings = [], []
    layer_id = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]

    def point(raw):
        if not isinstance(raw, list) or len(raw) < 2:
            raise ValueError('invalid coordinate')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in raw):
            raise ValueError('coordinates must be finite numbers')
        if any(abs(v) > 100_000 for v in raw):
            raise ValueError('coordinate exceeds local map profile')
        return [round(raw[0] * 100), round(raw[1] * 100)]

    def add(field, record):
        patches.append({'field': field, 'id': record['id'], 'before': None, 'after': record})

    features = value.get('features', [])
    if not isinstance(features, list) or len(features) > 20_000:
        raise ValueError('feature count exceeds import profile')
    for index, feature in enumerate(features):
        geometry = feature.get('geometry') or {}
        properties = feature.get('properties') or {}
        kind = geometry.get('type')
        coordinates = geometry.get('coordinates', [])
        identity = f'import-{layer_id}-{index}'
        if kind == 'LineString':
            points = [[p[0], round(float(properties.get('elevation_m', 0.2)) * 100), p[1]] for p in map(point, coordinates)]
            if len(points) < 2:
                raise ValueError('road requires two points')
            for suffix, p in [('from', points[0]), ('to', points[-1])]:
                add('nodes', {'id': identity + '-' + suffix, 'position': p, 'level': int(properties.get('level', 0))})
            add('roads', {'id': identity, 'from': identity + '-from', 'to': identity + '-to', 'points': points,
                          'widths_cm': [round(float(properties.get('width_m', 8)) * 100)] * (len(points) - 1),
                          'surfaces': [properties.get('surface', 'asphalt')] * (len(points) - 1), 'kind': 'ground',
                          'clearance_cm': None, 'sidewalk_cm': None})
            warnings.append(f'{identity}: disconnected endpoints retained; connect explicitly in editor')
        elif kind == 'Polygon':
            if len(coordinates) != 1:
                raise ValueError('polygon holes require explicit exclusion import; not silently flattened')
            polygon = list(map(point, coordinates[0]))
            if polygon and polygon[-1] == polygon[0]:
                polygon.pop()
            if properties.get('landuse') in ('forest', 'orchard'):
                add('zones', {'id': identity, 'polygon': polygon, 'kind': properties['landuse'], 'spacing_cm': 800,
                              'density_per_mille': 750, 'exclusions': []})
                warnings.append(f'{identity}: vegetation spacing/density estimated')
            else:
                add('buildings', {'id': identity, 'footprint': polygon, 'base_cm': round(float(properties.get('base_m', 0)) * 100),
                                  'height_cm': round(float(properties.get('height_m', 12)) * 100), 'usage': properties.get('usage', 'unknown'),
                                  'material': 'concrete', 'roof': 'flat'})
                if 'height_m' not in properties:
                    warnings.append(f'{identity}: building height estimated at 12 m')
        else:
            raise ValueError(f'unsupported geometry {kind}; no features imported')
    return {'layer_id': layer_id, 'source': source, 'license': license_name, 'coordinates': 'local-metres', 'patches': patches, 'warnings': warnings}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--coordinates', required=True, choices=['local-metres'])
    parser.add_argument('--license', required=True)
    args = parser.parse_args()
    if args.source.stat().st_size > MAX_BYTES:
        raise ValueError('input exceeds 32 MiB')
    data = args.source.read_bytes()
    if len(data) > MAX_BYTES:
        raise ValueError('input grew beyond 32 MiB')
    print(json.dumps({'stage': 'parse', 'completed': len(data), 'total': len(data), 'unit': 'bytes'}), flush=True)
    result = convert(json.loads(data), args.source.name, args.license)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, sort_keys=True, separators=(',', ':'), allow_nan=False)
    print(json.dumps({'stage': 'complete', 'completed': len(result['patches']), 'unit': 'records'}), flush=True)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, TypeError, KeyError, OverflowError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        sys.exit(1)
