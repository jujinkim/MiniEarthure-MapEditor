"""Source-audited forest path and native floor reference; no terrain generator."""
import copy
import json
import math
from pathlib import Path
import subprocess
import time

from reference_maps import rectangle
from scale_routes import digest, obstacle_boxes, overlap
from scale_turn_routes import bounds, covered


def source_route(doc, metadata):
    spec = metadata.get('forest_hill', {})
    if spec.get('profile') != 'l02-forest-hill-v1':
        raise ValueError('separately authored forest hill source required')
    lot = next(l for l in metadata['lots'] if l['id'] == spec['lot_id'])
    if lot['kind'] != 'forest':
        raise ValueError('forest interior required')
    ox, oz, _, _ = lot['bounds_cm']
    x = ox+3960
    road = next(r for r in doc['roads'] if r['id'] == spec['road_id'])
    if (road['points'] != [[x, 0, oz], [x, 0, oz+6400]] or road['widths_cm'] != [400]
            or road['surfaces'] != ['asphalt'] or road['kind'] != 'ground'):
        raise ValueError('explicit terrain-conforming forest spine required')
    nodes = {n['id']: n['position'] for n in doc['nodes']}
    connections = []
    for node, point in [(road['from'], road['points'][0]), (road['to'], road['points'][-1])]:
        incident = [r for r in doc['roads'] if node in [r['from'], r['to']]]
        if nodes[node] != point or len(incident) != 3:
            raise ValueError('forest road disconnected from explicit grid junction')
        for arm in incident:
            if nodes[arm['from']] != arm['points'][0] or nodes[arm['to']] != arm['points'][-1]:
                raise ValueError('incident endpoint/node mismatch')
        connections.append(dict(node_id=node, position_cm=point, road_ids=[r['id'] for r in incident]))
    zone = next(z for z in doc['zones'] if z['id'] == spec['zone_id'])
    if (zone['polygon'] != rectangle(ox+800, oz+800, 4800, 4800)
            or zone['exclusions'] != [rectangle(x-300, oz+800, 600, 4800)]
            or zone['exclusions'][0] != spec['exclusion']):
        raise ValueError('explicit narrow forest exclusion required')
    cell = dict(x=(ox+3200)//1600, y=(oz+3200)//1600)
    terrain = [h for h in doc['heightmaps'] if h['cell'] == cell]
    if cell != spec['cell'] or len(terrain) != 1:
        raise ValueError('original forest hill terrain identity required')
    # Source ground road heights stay zero: MapKit owns terrain fitting.
    points = [[x, 0, oz+v] for v in [600, 800, 3200, 3600, 4000, 4400, 4800, 5600, 5800]]
    sweep = [bounds(points[0], points[-1], 110)]
    stopping = [bounds(points[0], [x, 0, oz+200], 110),
                bounds(points[-1], [x, 0, oz+6200], 110)]
    strip = [x-200, oz, x+200, oz+6400]
    other = copy.deepcopy(doc)
    other['zones'] = [z for z in other['zones'] if z['id'] != zone['id']]
    other['heightmaps'] = [h for h in other['heightmaps'] if h['cell'] != cell]
    obstacles = list(obstacle_boxes(other))
    for box in sweep+stopping:
        if not covered(box, [strip]):
            raise ValueError('hill sweep/stopping room leaves source road')
        blocked = [key for key, obstacle in obstacles if overlap(box, obstacle)]
        if blocked:
            raise ValueError('hill obstacle envelope: '+','.join(blocked[:8]))
    support_ids = {ident for c in connections for ident in c['road_ids']}
    supports = []
    for r in doc['roads']:
        if r['id'] not in support_ids:
            continue
        a, b = r['points']
        if r['kind'] != 'ground' or r['surfaces'] != ['asphalt'] or r['widths_cm'] != [400]:
            raise ValueError('explicit ground junction supports required')
        box = bounds(a, b, 0)
        lateral = 0 if a[0] == b[0] else 1
        box[lateral] -= 200
        box[lateral+2] += 200
        supports.append(dict(road_id=r['id'], bounds_cm=box))
    return dict(road=road, points=points, sweep=sweep+stopping, stopping=stopping, supports=supports,
                strip=strip, connections=connections, terrain=terrain[0], lot=lot, zone=zone)


def native_reference(package, mapkit, output, source):
    """Use existing public CLI to audit and generate; keep exact command/hash evidence."""
    package, mapkit, output = Path(package).resolve(), Path(mapkit).resolve(), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    before = digest(package)
    commands = []

    def run(name, args):
        started = time.monotonic()
        command = [str(mapkit), *map(str, args)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        (output/(name+'.log')).write_text(result.stdout+result.stderr)
        commands.append(dict(command=command, exit_code=result.returncode, elapsed_s=time.monotonic()-started))
        (output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        if result.returncode:
            raise ValueError('native hill '+name+' failed: '+result.stderr[:500])
        return json.loads(result.stdout)

    audit = run('audit', ['audit-regions', package, 1073741824])
    if audit.get('verification') != 'complete-source':
        raise ValueError('complete native source audit required')
    box = [min(b[0] for b in source['sweep']), min(b[1] for b in source['sweep']),
           max(b[2] for b in source['sweep']), max(b[3] for b in source['sweep'])]
    # Include adjacent ownership cells when testing native obstacle envelopes.
    cells = [(x, z) for x in range(math.floor(box[0]/1600)-1, math.floor(box[2]/1600)+2)
             for z in range(math.floor(box[1]/1600)-1, math.floor(box[3]/1600)+2)]
    if len(cells) > 64:
        raise ValueError('bounded hill reference cells required')
    references, floors, obstacles = [], [], {}
    for x, z in cells:
        target = output/f'cell-{x}-{z}.json'
        result = run(target.stem, ['generate-region-chunk', package, x, z, target.resolve(), 1073741824])
        if digest(target) != result['generated_sha256']:
            raise ValueError('native generated identity mismatch')
        generated = json.loads(target.read_text())
        references.append(dict(cell=[x, z], sha256=digest(target), bytes=target.stat().st_size))
        for triangle in generated['triangles']:
            vertices = triangle['vertices']
            ident = triangle['object_id']
            xs, heights, zs = zip(*vertices)
            if ident in {r['road_id'] for r in source['supports']}:
                if triangle['surface'] != 'asphalt' or not triangle['spawnable']:
                    raise ValueError('native ground road support identity mismatch')
                if overlap([min(xs), min(zs), max(xs), max(zs)], box):
                    floors.append(dict(road_id=ident, vertices_cm=vertices))
            elif ident != 'terrain':
                old = obstacles.get(ident, [math.inf, math.inf, -math.inf, -math.inf])
                obstacles[ident] = [min(old[0], min(xs)), min(old[1], min(zs)),
                                   max(old[2], max(xs)), max(old[3], max(zs))]
    blocked = [ident for ident, obstacle in obstacles.items() if any(overlap(obstacle, b) for b in source['sweep'])]
    if blocked:
        raise ValueError('native obstacle intersects hill sweep: '+','.join(blocked[:8]))
    if not 1 <= len(floors) <= 2048 or max(v[1] for t in floors for v in t['vertices_cm']) < 200:
        raise ValueError('bounded native two metre hill floors required')
    if before != digest(package):
        raise ValueError('package changed during native hill reference')
    return dict(package_sha256=before, cli_sha256=digest(mapkit), audit=audit,
                cells=references, road_id=source['road']['id'], floor_triangles_cm=floors,
                obstacle_overlaps=[], obstacle_objects_checked=len(obstacles))


def hill_routes(doc, metadata, package, mapkit, native_output):
    source = source_route(doc, metadata)
    native = native_reference(package, mapkit, native_output, source)
    result = []
    road = source['road']
    for direction, suffix in [(1, 'outbound'), (-1, 'return')]:
        points = source['points'][::direction]
        segments, distance = [], 0.0
        for a, b in zip(points, points[1:]):
            length = math.dist(a, b)/100
            segments.append(dict(start_cm=a, end_cm=b, start_m=distance, end_m=distance+length,
                road_ids=[road['id']], turn_index=-1, adjacent_kinds=['forest'], adjacent_lot_ids=[source['lot']['id']]))
            distance += length
        a, b = road['points'][::direction]
        endpoints = [road['from'], road['to']][::direction]
        result.append(dict(id='forest-hill-'+suffix, mode='l02-forest-hill-v1',
            start_cm=points[0], end_cm=points[-1], spawn_surface=road['id'],
            heading_degrees=0 if direction == 1 else 180, distance_m=distance,
            lateral_tolerance_m=.75, expected_height_range_m=2,
            edges=[dict(road_id=road['id'], direction=direction, start_cm=a, end_cm=b,
                        **{'from': endpoints[0], 'to': endpoints[1]})],
            support_roads=source['supports'],
            segments=segments, turns=[], native_reference=native,
            forest=dict(lot_id=source['lot']['id'], zone_id=source['zone']['id'],
                        bounds_cm=source['lot']['bounds_cm'], terrain=source['terrain'],
                        apex_offset_m=0.4, expected_centerline_peak_m=1.9,
                        exclusion=source['zone']['exclusions'][0], connections=source['connections']),
            source_obstacles=dict(corridor_half_width_m=1.1, vehicle_radius_m=.35,
                                  swept_bounds_cm=source['sweep'], overlaps=[]),
            stopping=dict(margin_m=4, bounds_cm=source['stopping'][::direction]),
            scope='complete forest interior climb/descent with native floor reference; independent forward leg, no U-turn or bridge acceptance'))
    return result
