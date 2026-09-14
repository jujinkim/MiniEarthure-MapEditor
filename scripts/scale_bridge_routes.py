"""Explicit source-preserving bridge shuttles and native graded stopping audit."""
import copy
import math
from scale_routes import corridor, obstacle_boxes, overlap
from scale_turn_routes import bounds, covered
from scale_hill_routes import native_reference


def source_routes(doc, metadata):
    size_m = metadata.get('size_m', 0)
    if type(size_m) not in (int, float) or not math.isfinite(size_m) or not 288 <= size_m <= 10000:
        raise ValueError('bridge profile requires an existing scale map >=288m')
    size = size_m*100
    if doc.get('bounds') != dict(min=[0,0],max=[size,size]) or doc.get('cell_size_cm') != 1600:
        raise ValueError('explicit scale world bounds and execution grid required')
    roads = [r for r in doc['roads'] if r['id'] == 'speed-bridge']
    if len(roads) != 1:
        raise ValueError('unique explicit scale bridge required')
    road = roads[0]
    expected = [[0,0,800],[1600,0,800],[4800,300,800],
                [size-4800,300,800],[size-1600,0,800],[size,0,800]]
    nodes = {n['id']: n['position'] for n in doc['nodes']}
    if (road['kind'] != 'bridge' or road['points'] != expected
            or road['widths_cm'] != [600]*5 or road['surfaces'] != ['asphalt']*5
            or nodes.get(road['from']) != expected[0] or nodes.get(road['to']) != expected[-1]):
        raise ValueError('explicit connected scale bridge geometry/material required')
    # Preserve the original full profile. New bounded routes are independently
    # clipped/audited, never a distance override of its waypoint list.
    full = corridor(doc, metadata, 'bridge-full-shuttle', [road['id']], 1600)
    specs = []
    if full['distance_m'] <= 256:
        specs.append(('bridge-full-shuttle',1600,size-1600))
    specs.append(('bridge-east-ramp-shuttle',size-17600,size-1600))
    result = []
    for ident, low, high in specs:
        route = copy.deepcopy(full)
        route['id'] = ident
        segments = []
        for segment in full['segments']:
            a, b = segment['start_cm'], segment['end_cm']
            lo, hi = max(low,a[0]), min(high,b[0])
            if lo >= hi:
                continue
            def point(x):
                return [x,a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0]),a[2]]
            segments.append(dict(segment,start_cm=point(lo),end_cm=point(hi)))
        route.update(start_cm=segments[0]['start_cm'],end_cm=segments[-1]['end_cm'],
                     segments=segments,distance_m=(high-low)/100)
        strip = [0,500,size,1100]
        sweep = bounds([low-1200,0,800],[high+1200,0,800],110)
        if not covered(sweep,[strip]):
            raise ValueError('bridge vehicle/stopping sweep outside source road')
        blocked = [name for name, box in obstacle_boxes(doc) if overlap(sweep,box)]
        if blocked:
            raise ValueError('bridge stopping obstacle envelope: '+','.join(blocked[:8]))
        # Interior controlled stop: retain twelve metres entirely on the same
        # descending ramp, before completing the route and reversing at its end.
        brake_start = size-4000
        brake_end = brake_start+1200
        if not low < brake_start < brake_end < high:
            raise ValueError('complete downhill braking interval required')
        route['mode'] = 'l02-bridge-shuttle-v1'
        route['source_graph'] = dict(road_id=road['id'],points_cm=copy.deepcopy(road['points']),
                                    **{'from':road['from'],'to':road['to']})
        route['source_obstacles'] = dict(corridor_half_width_m=1.1,vehicle_radius_m=.35,
                                        swept_bounds_cm=[sweep],overlaps=[])
        route['shuttle'] = dict(format='l02-graded-shuttle-v1',stopping_margin_m=12,
            bounds_cm=sweep,overlaps=[],braking=dict(id='downhill-service-stop',direction=1,
                start_cm=[brake_start,225,800],end_cm=[brake_end,112.5,800],
                max_distance_m=12,max_start_lateness_m=.5,maximum_target_m_s=11,
                minimum_target_seconds=5))
        route['scope'] = ('complete small bridge with both ramps' if ident=='bridge-full-shuttle'
                          else 'complete named east 160m ramp route; not the full large bridge')+'; forward/stop/reverse and separately measured downhill braking'
        result.append((route,dict(road=road,sweep=[sweep],world_bounds=copy.deepcopy(doc['bounds']),
                                 supports=[dict(road_id=road['id'],bounds_cm=strip)])))
    return result


def floor_at(triangles, x, z):
    """Interpolate supplied native faces; never generate or fit road geometry."""
    for triangle in triangles:
        a, b, c = triangle['vertices_cm']
        ux, uy, uz = [b[i]-a[i] for i in range(3)]
        vx, vy, vz = [c[i]-a[i] for i in range(3)]
        determinant = ux*vz-uz*vx
        if abs(determinant) < 1e-9:
            continue
        s = ((x-a[0])*vz-(z-a[2])*vx)/determinant
        t = (ux*(z-a[2])-uz*(x-a[0]))/determinant
        if min(s,t) < -1e-9 or s+t > 1+1e-9:
            continue
        nx, ny, nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        length = math.sqrt(nx*nx+ny*ny+nz*nz)
        sign = 1 if ny > 0 else -1
        return dict(height_cm=a[1]+s*uy+t*vy,
                    normal=[sign*n/length for n in [nx,ny,nz]], grade_x=-nx/ny)
    raise ValueError('native bridge floor probe missing support')


def probe_reference(route, native):
    """Bounded diagnostic probes supplement source envelopes and native audit.

    These samples are not continuous collision/vehicle acceptance. The complete
    native faces remain in the sidecar for the later actual wheel observations.
    """
    triangles = native['floor_triangles_cm']
    points = route['source_graph']['points_cm']
    low, zlow, high, zhigh = route['shuttle']['bounds_cm']
    brake = route['shuttle']['braking']
    checkpoints = sorted({low, high, *[s[k][0] for s in route['segments'] for k in ['start_cm','end_cm']],
                          brake['start_cm'][0], brake['end_cm'][0]})
    count = math.ceil((high-low)/25)
    stations = sorted(set(checkpoints+[low+(high-low)*i/count for i in range(count+1)]))
    if len(stations)*3 > 4096:
        raise ValueError('bounded native bridge probes required')
    heights, errors, normals, brake_grades, recorded = [], [], [], [], []
    for x in stations:
        a, b = next((a,b) for a,b in zip(points,points[1:]) if a[0] <= x <= b[0])
        expected = a[1]+(b[1]-a[1])*(x-a[0])/(b[0]-a[0])
        for z in [zlow,800,zhigh]:
            hit = floor_at(triangles,x,z)
            error = abs(hit['height_cm']-expected)
            if error > 10 or hit['normal'][1] <= .9:
                raise ValueError('native bridge probe height/normal mismatch')
            if brake['start_cm'][0] <= x <= brake['end_cm'][0]:
                if hit['grade_x'] >= -.05:
                    raise ValueError('native bridge stopping interval must remain downhill')
                brake_grades.append(hit['grade_x'])
            heights.append(hit['height_cm'])
            errors.append(error)
            normals.append(hit['normal'][1])
            if x in checkpoints:
                recorded.append(dict(position_cm=[x,hit['height_cm'],z],normal=hit['normal']))
    if max(heights)-min(heights) < 285:
        raise ValueError('native bridge probes require three metre relief')
    return dict(format='l02-bridge-floor-probes-v1',samples=len(heights),
                maximum_station_spacing_cm=25,lateral_offsets_cm=[-110,0,110],
                minimum_height_cm=min(heights),maximum_height_cm=max(heights),
                maximum_height_error_cm=max(errors),minimum_normal_y=min(normals),
                downhill_grade_range=[min(brake_grades),max(brake_grades)],
                checkpoints=recorded,
                scope='diagnostic native probes only; continuous four-wheel driving and braking remain unverified')


def bridge_routes(doc, metadata, package, mapkit, native_output):
    from pathlib import Path
    sources = source_routes(doc,metadata)
    output = Path(native_output)
    output.mkdir(parents=True,exist_ok=False)
    result = []
    for route, source in sources:
        route['native_reference'] = native_reference(package,mapkit,output/route['id'],source,300,'bridge')
        route['native_reference']['floor_probes'] = probe_reference(route,route['native_reference'])
        result.append(route)
    return result
