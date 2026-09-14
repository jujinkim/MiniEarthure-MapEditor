"""Bounded test-only turns on explicit source graph edges; no route search.

The polyline is the driving target, not generated road geometry. Its conservative
swept boxes must fit the source road union and avoid every source obstacle.
"""
import math

from scale_routes import obstacle_boxes, overlap


def bounds(a, b, padding):
    return [min(a[0], b[0])-padding, min(a[2], b[2])-padding,
            max(a[0], b[0])+padding, max(a[2], b[2])+padding]


def covered(box, rectangles):
    """Exact rectangular-union containment, including disconnected/slit gaps."""
    rectangles = [r for r in rectangles if overlap(box, r)]
    xs = sorted({box[0], box[2], *(v for r in rectangles for v in [r[0], r[2]] if box[0] < v < box[2])})
    zs = sorted({box[1], box[3], *(v for r in rectangles for v in [r[1], r[3]] if box[1] < v < box[3])})
    return all(any(r[0] <= (x+xx)/2 <= r[2] and r[1] <= (z+zz)/2 <= r[3] for r in rectangles)
               for x, xx in zip(xs, xs[1:]) for z, zz in zip(zs, zs[1:]))


def add(a, v, amount):
    return [a[i]+v[i]*amount for i in range(3)]


def authored_turn(doc, metadata, ident, edges):
    if not 3 <= len(edges) <= 32 or len({e[0] for e in edges}) != len(edges):
        raise ValueError('bounded unique explicit road edges required')
    roads = {r['id']: r for r in doc['roads']}
    nodes = {n['id']: n['position'] for n in doc['nodes']}
    chain = []
    for road_id, direction in edges:
        if type(direction) is not int or direction not in [-1, 1] or road_id not in roads:
            raise ValueError('explicit existing road and direction required')
        road = roads[road_id]
        if (len(road['points']) != 2 or road['kind'] != 'ground'
                or road['surfaces'] != ['asphalt'] or len(road['widths_cm']) != 1
                or road['widths_cm'][0] < 400 or any(p[1] != 0 for p in road['points'])):
            raise ValueError('turns require flat straight ground asphalt edges >=4m wide')
        if nodes[road['from']] != road['points'][0] or nodes[road['to']] != road['points'][-1]:
            raise ValueError('road endpoint/node mismatch')
        a, b = road['points'][::direction]
        delta = [b[i]-a[i] for i in range(3)]
        if (delta[0] == 0) == (delta[2] == 0):
            raise ValueError('orthogonal nonempty source edge required')
        length = math.dist(a, b)
        if length < 1600:
            raise ValueError('source edge needs turn and braking clearance')
        unit = [d/length for d in delta]
        start_node, end_node = (road['from'], road['to']) if direction > 0 else (road['to'], road['from'])
        if chain and (chain[-1]['to'] != start_node or chain[-1]['end_cm'] != a):
            raise ValueError('disconnected explicit directed road graph')
        # No longitudinal end cap is assumed: only the real strip interior.
        rectangle = bounds(a, b, 0)
        lateral = 1 if delta[0] else 0
        rectangle[lateral] -= road['widths_cm'][0]/2
        rectangle[lateral+2] += road['widths_cm'][0]/2
        midpoint = add(a, unit, length/2)
        lots = [lot for lot in metadata['lots'] if lot['bounds_cm'][0] <= midpoint[0] <= lot['bounds_cm'][2]
                and lot['bounds_cm'][1] <= midpoint[2] <= lot['bounds_cm'][3]]
        chain.append(dict(road_id=road_id, direction=direction, start_cm=list(a), end_cm=list(b),
                          **{'from':start_node, 'to':end_node}, unit=unit, bounds_cm=rectangle,
                          adjacent_lot_ids=[lot['id'] for lot in lots],
                          adjacent_kinds=sorted({lot['kind'] for lot in lots})))
    corners = {}
    for i, (a, b) in enumerate(zip(chain, chain[1:])):
        dot = sum(x*y for x, y in zip(a['unit'], b['unit']))
        if dot == -1:
            raise ValueError('U-turn/retraced edges unsupported')
        if dot == 0:
            corners[i] = len(corners)
    if not corners:
        raise ValueError('explicit turn required')
    junction_nodes = {e[key] for e in chain for key in ['from','to']}
    supports = []
    for road in doc['roads']:
        if not junction_nodes.intersection([road['from'],road['to']]):
            continue
        if (len(road['points']) != 2 or road['kind'] != 'ground' or road['surfaces'] != ['asphalt']
                or any(p[1] != 0 for p in road['points'])):
            continue
        a,b = road['points']
        if (a[0] == b[0]) == (a[2] == b[2]):
            continue
        if nodes[road['from']] != a or nodes[road['to']] != b:
            raise ValueError('junction road endpoint/node mismatch')
        rectangle = bounds(a,b,0)
        lateral = 0 if a[0] == b[0] else 1
        rectangle[lateral] -= road['widths_cm'][0]/2
        rectangle[lateral+2] += road['widths_cm'][0]/2
        supports.append(dict(road_id=road['id'],bounds_cm=rectangle,
                             **{'from':road['from'],'to':road['to']}))
    if len(supports)>128:
        raise ValueError('bounded junction support roads required')
    segments, turns = [], []
    distance = 0.0

    def segment(a, b, edge_indices, turn_index=-1):
        nonlocal distance
        length = math.dist(a, b)/100
        if length <= 0:
            raise ValueError('nonempty ordered target segment required')
        source = chain[edge_indices[0]]
        allowed = ([r['road_id'] for r in supports if chain[edge_indices[0]]['to'] in [r['from'],r['to']]]
                   if turn_index >= 0 else [source['road_id']])
        segments.append(dict(start_cm=a, end_cm=b, start_m=distance, end_m=distance+length,
                             road_ids=allowed, turn_index=turn_index,
                             adjacent_lot_ids=source['adjacent_lot_ids'] if turn_index < 0 else [],
                             adjacent_kinds=source['adjacent_kinds'] if turn_index < 0 else []))
        distance += length

    for i, edge in enumerate(chain):
        a = add(edge['start_cm'], edge['unit'], 800 if i == 0 else (200 if i-1 in corners else 0))
        b = add(edge['end_cm'], edge['unit'], -800 if i == len(chain)-1 else (-200 if i in corners else 0))
        segment(a, b, [i])
        if i not in corners:
            continue
        next_edge = chain[i+1]
        end = add(edge['end_cm'], next_edge['unit'], 200)
        center = add(b, next_edge['unit'], 200)
        turn_start = distance
        previous = b
        for step in range(1, 9):
            angle = step*math.pi/16
            point = [center[j] + 200*(-next_edge['unit'][j]*math.cos(angle) + edge['unit'][j]*math.sin(angle))
                     for j in range(3)] if step < 8 else end
            segment(previous, point, [i, i+1], corners[i])
            previous = point
        # x/northing cross product: positive is a physical left turn.
        cross = edge['unit'][0]*next_edge['unit'][2]-edge['unit'][2]*next_edge['unit'][0]
        turns.append(dict(node_id=edge['to'], incoming_edge=i, outgoing_edge=i+1,
                          direction='left' if cross > 0 else 'right', start_m=turn_start, end_m=distance,
                          entry_cm=b, exit_cm=end, incoming=edge['unit'], outgoing=next_edge['unit'],
                          radius_m=2, polyline_steps=8))
    # 0.75m tracking error plus a <=0.35m orientation-independent vehicle radius.
    # The entire box of each chord is tested, not just sparse sample points.
    rectangles = [e['bounds_cm'] for e in supports]
    swept = [bounds(s['start_cm'], s['end_cm'], 110) for s in segments]
    for point, unit, sign in [(segments[0]['start_cm'],chain[0]['unit'],-1),
                              (segments[-1]['end_cm'],chain[-1]['unit'],1)]:
        swept.append(bounds(point, add(point, unit, sign*400), 110))
    obstacles = list(obstacle_boxes(doc))
    for box in swept:
        if not covered(box, rectangles):
            raise ValueError('turn swept vehicle/stopping corridor leaves source road union')
        blocked = [name for name, obstacle in obstacles if overlap(box, obstacle)]
        if blocked:
            raise ValueError('turn swept obstacle envelope: '+','.join(blocked[:8]))
    return dict(id=ident, mode='l02-directed-turns-v1', start_cm=segments[0]['start_cm'],
                end_cm=segments[-1]['end_cm'], heading_degrees=math.degrees(math.atan2(-chain[0]['unit'][0],chain[0]['unit'][2])),
                spawn_surface=chain[0]['road_id'], distance_m=distance, lateral_tolerance_m=.75,
                expected_height_range_m=0, edges=chain, support_roads=supports, segments=segments, turns=turns,
                source_obstacles=dict(corridor_half_width_m=1.1, vehicle_radius_m=.35,
                                      swept_bounds_cm=swept, overlaps=[]),
                stopping=dict(margin_m=4, bounds_cm=swept[-2:]),
                scope='complete directed flat connected turns; no routing/access, reverse shuttle or hill/bridge acceptance')


def turn_routes(doc, metadata):
    n = metadata['tiles_per_side']
    if metadata['condition'] not in ['mixed', 'dense'] or n < 4 or n % 2:
        raise ValueError('turn profile requires mixed/dense even grid >=4')
    x, y = n//2, n//2-1
    ids = [f'grid-ns-{x}-{y}', f'grid-ew-{x}-{y+1}-a',
           f'grid-ew-{x}-{y+1}-b', f'grid-ns-{x+1}-{y+1}']
    return [authored_turn(doc,metadata,'connected-turns-outbound',[(key,1) for key in ids]),
            authored_turn(doc,metadata,'connected-turns-return',[(key,-1) for key in reversed(ids)])]
