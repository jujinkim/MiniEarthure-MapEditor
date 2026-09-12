#!/usr/bin/env python3
"""Create read-only L02 route evidence beside an unchanged synthetic source/package.

The sidecar is test metadata, never a map contract or a native audit receipt.
Only straight connected road corridors are supported; no pathfinding is inferred.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package_identity(package, source_hashes, restored):
    with Path(package).open('rb') as stream:
        header = stream.read(48)
        if len(header) != 48 or header[:8] != b'MKREGN01':
            raise ValueError('indexed package required')
        length = struct.unpack('<Q', header[8:16])[0]
        if not 0 < length <= 4 * 1024 * 1024:
            raise ValueError('bounded index required')
        raw = stream.read(length)
    if hashlib.sha256(raw).digest() != header[16:]:
        raise ValueError('index hash mismatch')
    index = json.loads(raw)
    records = index['records']
    if records[index['authoring_source']]['sha256'] != digest(Path(restored)/'document.json'):
        raise ValueError('package authoring source mismatch')
    if set(index['payloads']) != set(source_hashes) - {'document.json'}:
        raise ValueError('package payload set mismatch')
    for name, record in index['payloads'].items():
        if records[record]['sha256'] != source_hashes[name]:
            raise ValueError('package payload identity mismatch: ' + name)
    return dict(sha256=digest(package), world_content_hash=index['world_content_hash'],
                storage_m=index['side_cells'] * 16,
                scope='front-index/source identity only; Runtime still performs full native audit')


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def obstacle_boxes(doc):
    """Conservative source envelopes; never duplicate procedural tree generation."""
    assets = {a['id']: a for a in doc['assets']}
    if doc['repetitions']:
        raise ValueError('repetition obstacle audit unsupported')
    for placement in doc['placements']:
        x, height, z = placement['position']
        turn = placement['quarter_turns'] % 4
        for box in assets[placement['asset_id']]['collision']:
            cx, cy, cz = box['center']
            sx, sy, sz = box['size_cm']
            if height + cy + sy / 2 <= 10:
                continue  # Authored flush paving, not a vertical obstacle.
            for _ in range(turn):
                cx, cz = -cz, cx
                sx, sz = sz, sx
            yield placement['id'], [x+cx-sx/2, z+cz-sz/2, x+cx+sx/2, z+cz+sz/2]
    for obj in [*doc['zones'], *doc['buildings']]:
        polygon = obj['polygon']
        xs, zs = zip(*polygon)
        yield obj['id'], [min(xs), min(zs), max(xs), max(zs)]
    # Forest hill interiors are excluded from clear road corridors. Their height
    # and tree placements are not inferred from the neighboring flat road.
    for terrain in doc['heightmaps']:
        x, z = terrain['cell']['x']*1600, terrain['cell']['y']*1600
        yield 'terrain:'+str(terrain['cell']), [x, z, x+1600, z+1600]


def corridor(doc, metadata, ident, road_ids, trim_cm=800):
    roads = {road['id']: road for road in doc['roads']}
    nodes = {node['id']: node['position'] for node in doc['nodes']}
    chain = [roads[key] for key in road_ids]
    for road in chain:
        if nodes[road['from']] != road['points'][0] or nodes[road['to']] != road['points'][-1]:
            raise ValueError('road endpoint/node mismatch')
        if road['kind'] not in ('ground', 'bridge') or min(road['widths_cm']) < 400:
            raise ValueError('unsupported road kind or insufficient corridor width')
    for a, b in zip(chain, chain[1:]):
        if a['to'] != b['from'] or a['points'][-1] != b['points'][0]:
            raise ValueError('disconnected road graph')
    start, end = chain[0]['points'][0], chain[-1]['points'][-1]
    axis = 0 if end[0] != start[0] else 2
    other = 2 if axis == 0 else 0
    if end[axis] <= start[axis] or any(p[other] != start[other] for r in chain for p in r['points']):
        raise ValueError('only increasing straight corridors are supported')
    low, high = start[axis] + trim_cm, end[axis] - trim_cm
    if high <= low:
        raise ValueError('empty trimmed route')
    segments = []
    for road in chain:
        for index, (a, b) in enumerate(zip(road['points'], road['points'][1:])):
            if b[axis] <= a[axis]:
                raise ValueError('nonmonotonic road')
            lo, hi = max(low, a[axis]), min(high, b[axis])
            if hi <= lo:
                continue
            def point(at):
                value = list(a)
                value[axis] = at
                value[1] = a[1]+(b[1]-a[1])*(at-a[axis])/(b[axis]-a[axis])
                return value
            first, last = point(lo), point(hi)
            if road['kind'] == 'ground' and (first[1] != 0 or last[1] != 0):
                raise ValueError('ground terrain profile unsupported')
            mid = [(first[i]+last[i])/2 for i in range(3)]
            lots = [lot for lot in metadata['lots'] if lot['bounds_cm'][0] <= mid[0] <= lot['bounds_cm'][2]
                    and lot['bounds_cm'][1] <= mid[2] <= lot['bounds_cm'][3]]
            segments.append(dict(road_id=road['id'], road_kind=road['kind'],
                surface=road['surfaces'][index], start_cm=first, end_cm=last,
                adjacent_lot_ids=[lot['id'] for lot in lots],
                adjacent_kinds=sorted({lot['kind'] for lot in lots})))
    first, last = segments[0]['start_cm'], segments[-1]['end_cm']
    bounds = [min(first[0],last[0])-100,min(first[2],last[2])-100,
              max(first[0],last[0])+100,max(first[2],last[2])+100]
    blocked = [name for name, box in obstacle_boxes(doc) if overlap(bounds, box)]
    if blocked:
        raise ValueError('route obstacle envelope: '+','.join(blocked[:8]))
    for a, b in zip(segments, segments[1:]):
        if a['end_cm'] != b['start_cm']:
            raise ValueError('route segment gap')
    heights = [p[1] for s in segments for p in [s['start_cm'],s['end_cm']]]
    return dict(id=ident, start_cm=first, end_cm=last, spawn_surface=segments[0]['road_id'],
                heading_degrees=-90 if axis == 0 else 0, axis=axis,
                distance_m=(high-low)/100, lateral_tolerance_m=0.75,
                expected_height_range_m=(max(heights)-min(heights))/100,
                segments=segments, source_obstacles=dict(corridor_half_width_m=1, overlaps=[]),
                scope='road corridor next to authored lots; not lot-interior, visibility or forest-hill acceptance')


def routes(doc, metadata):
    n = metadata['tiles_per_side']
    half = n // 2
    if metadata['condition'] != 'mixed' or n < 4 or n % 2:
        raise ValueError('mixed scale map with even grid >=4 required')
    def ns(x, first, last):
        return [f'grid-ns-{x}-{y}' for y in range(first,last)]
    specs = [('residential',ns(half+1,0,half)), ('rural',ns(1,half,n)),
             ('forest',ns(half+1,half,n)), ('residential-forest',ns(half+1,0,n)),
             ('urban-rural',ns(1,0,n)),
             ('rural-forest',[f'grid-ew-{x}-{half+1}-{arm}' for x in range(n) for arm in ['a','b']]),
             ('bridge-grades',['speed-bridge'])]
    # The bridge's ground ramp endpoints are 16m from the map edge. Stop there,
    # preserving both full grades and additional braking room inside the map.
    result = [corridor(doc,metadata,ident,ids,1600 if ident=='bridge-grades' else 800)
              for ident,ids in specs]
    for route in result:
        actual = {kind for segment in route['segments'] for kind in segment['adjacent_kinds']}
        expected = set() if route['id'] == 'bridge-grades' else set(route['id'].split('-'))
        if actual != expected:
            raise ValueError('authored density coverage mismatch: '+route['id'])
    return result


def document_semantics(doc):
    result = dict(doc)
    # Native packing sorts top-level record collections and omits empty optional
    # collections. Do not sort geometry, road points, collision shapes or tags.
    for key in ['nodes','roads','buildings','zones','assets','placements',
                'repetitions','heightmaps','surface_areas','attributions']:
        result[key] = sorted(doc.get(key,[]),key=lambda value:json.dumps(value,sort_keys=True))
    return result


def create(source, package, output, restored):
    source, package, output = Path(source), Path(package), Path(output)
    metadata = json.loads((source/'scale.json').read_text())
    for name, expected in metadata['source_hashes'].items():
        path = (source/name).resolve()
        if not path.is_relative_to(source.resolve()) or digest(path) != expected:
            raise ValueError('source identity mismatch: '+name)
    doc = json.loads((source/'document.json').read_text())
    restored_doc = json.loads((Path(restored)/'document.json').read_text())
    if document_semantics(doc) != document_semantics(restored_doc):
        raise ValueError('restored package/source semantics mismatch')
    result = dict(format='l02-road-routes-v1', metadata_sha256=digest(source/'scale.json'),
                  source_sha256=metadata['source_hashes']['document.json'],
                  package=package_identity(package,metadata['source_hashes'],restored),routes=routes(doc,metadata))
    with output.open('x') as stream:
        json.dump(result,stream,indent=2)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('package',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--restored',type=Path,required=True,help='new directory from native mapkit unpack-regions')
    args = parser.parse_args()
    result = create(args.source,args.package,args.output,args.restored)
    print(json.dumps({'routes':[r['id'] for r in result['routes']], 'package':result['package']},indent=2))
