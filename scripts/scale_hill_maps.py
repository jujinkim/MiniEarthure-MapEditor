#!/usr/bin/env python3
"""Derive one connected forest-hill road in a NEW synthetic L02 source."""
import argparse
import copy
import json
import math
from pathlib import Path

from reference_maps import canonical, rectangle, sha
from scale_routes import digest

PROFILE = 'l02-forest-hill-v1'
ROAD = 'forest-hill-spine'


def derive(original, metadata):
    doc, summary = copy.deepcopy(original), copy.deepcopy(metadata)
    n = summary['tiles_per_side']
    if (summary['profile'] != 'l02-area-density-v1' or summary['condition'] != 'mixed'
            or n < 4 or n % 2 or 'forest_hill' in summary):
        raise ValueError('original mixed L02 even grid >=4 required')
    ix = iy = n // 2
    lot = next(l for l in summary['lots'] if l['id'] == f'forest-{ix}-{iy}')
    ox, oz, _, _ = lot['bounds_cm']
    # Cross the original hill just beside its point apex. The 0.8m longitudinal
    # crown accommodates the actual four-wheel footprint without reshaping terrain.
    x = ox + 3960
    zone = next(z for z in doc['zones'] if z['id'] == lot['id']+'-forest')
    if zone['exclusions'] or zone['polygon'] != rectangle(ox+800, oz+800, 4800, 4800):
        raise ValueError('unchanged synthetic forest envelope required')
    exclusion = rectangle(x-300, oz+800, 600, 4800)
    zone['exclusions'].append(exclusion)
    changed_roads, added_roads, endpoints = [], [], []
    for y, z in [(iy, oz), (iy+1, oz+6400)]:
        road = next(r for r in doc['roads'] if r['id'] == f'grid-ew-{ix}-{y}-b')
        if road['points'] != [[ox+1600, 0, z], [ox+6400, 0, z]]:
            raise ValueError('original horizontal grid arm required')
        node = f'forest-hill-junction-{y}'
        point = [x, 0, z]
        tail = copy.deepcopy(road)
        tail.update(id=road['id']+'-hill-tail', points=[point, road['points'][-1]], **{'from': node})
        road.update(points=[road['points'][0], point], to=node)
        doc['nodes'].append(dict(id=node, position=point, level=0))
        doc['roads'].append(tail)
        changed_roads.append(road['id'])
        added_roads.append(tail['id'])
        endpoints.append(node)
    doc['roads'].append(dict(id=ROAD, points=[[x, 0, oz], [x, 0, oz+6400]],
        widths_cm=[400], surfaces=['asphalt'], kind='ground', sidewalk_cm=0,
        clearance_cm=None, **{'from': endpoints[0], 'to': endpoints[1]}))
    doc['map_id'] += '-forest-hill'
    doc['revision'] += 1
    doc['provenance'].update(tool_id='mapeditor-scale-hill-maps', build_id=PROFILE,
                             last_edited='2026-09-14T00:00:00Z')
    summary['forest_hill'] = dict(profile=PROFILE, road_id=ROAD, lot_id=lot['id'],
        zone_id=zone['id'], cell=dict(x=(ox+3200)//1600, y=(oz+3200)//1600),
        apex_offset_m=0.4, expected_centerline_peak_m=1.9,
        exclusion=exclusion, excluded_area_m2=288, original_zone_area_m2=2304,
        changed_roads=changed_roads, added_roads=added_roads+[ROAD], added_nodes=endpoints,
        baseline_source_hashes=copy.deepcopy(metadata['source_hashes']),
        preserved='all payloads, heightmaps, assets, placements, lots, seed and vegetation rules except one explicit exclusion')
    summary['counts'] = {key: len(doc[key]) for key in summary['counts']}
    summary['road_centerline_spatial_m'] = sum(math.dist(a, b)/100 for r in doc['roads']
                                              for a, b in zip(r['points'], r['points'][1:]))
    summary['road_m_per_km2'] = summary['road_centerline_spatial_m']/summary['area_km2']
    summary['source_document_bytes'] = len(canonical(doc))
    summary['source_hashes']['document.json'] = sha(canonical(doc))
    return doc, summary


def create(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    metadata = json.loads((source/'scale.json').read_text())
    payloads = {}
    for name, expected in metadata['source_hashes'].items():
        path = (source/name).resolve()
        if not path.is_relative_to(source.resolve()) or digest(path) != expected:
            raise ValueError('baseline source identity mismatch: '+name)
        payloads[name] = path.read_bytes()
    doc, summary = derive(json.loads(payloads.pop('document.json')), metadata)
    summary['forest_hill']['baseline_metadata_sha256'] = digest(source/'scale.json')
    destination.mkdir(parents=True, exist_ok=False)
    for name, data in {**payloads, 'document.json': canonical(doc),
                       'scale.json': (json.dumps(summary, indent=2)+'\n').encode()}.items():
        path = destination/name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    print(json.dumps(create(args.source, args.destination)['forest_hill'], indent=2))
