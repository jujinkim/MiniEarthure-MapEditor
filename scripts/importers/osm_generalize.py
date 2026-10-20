"""Deterministic, scale-aware derived city geometry. Original sources are immutable.

Only compatible ground chains and local polygon groups are combined. Road
corridors, named/tall buildings, source junctions and vertical roads are protected.
The output is ordinary current-v1 geometry, not a special runtime map format.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import json
import math

import numpy as np
import shapely
from shapely.geometry import shape, mapping, Polygon, LineString, box
from shapely.ops import transform, unary_union
from shapely.strtree import STRtree
from shapely.errors import GEOSException

from projection import Coordinates
from osm_extract import PEDESTRIAN

PROFILE = "scale-aware-city-v1"
SCALE = 8
MAX_GROUP = 128
MAX_WORK = 4_000_000
LEVELS = (0, 2, 4, 8, 16, 32, 64)  # Source metres, bounded by the local road/land barriers.
SURFACES = {"asphalt":"asphalt", "concrete":"concrete", "dirt":"dirt", "gravel":"gravel", "grass":"grass",
            "paved":"asphalt", "paving_stones":"concrete", "sett":"concrete", "cobblestone":"concrete",
            "concrete:plates":"concrete", "concrete:lanes":"concrete", "compacted":"gravel",
            "fine_gravel":"gravel", "pebblestone":"gravel", "unpaved":"dirt", "ground":"dirt",
            "earth":"dirt", "sand":"dirt", "mud":"dirt", "wood":"concrete", "metal":"concrete"}
PAINT_CELL = 3200  # Map centimetres: one native cell partitions pedestrian paint.
PAINT_VERTICES = 256
WIDTHS = {"motorway":12,"trunk":10,"primary":8,"secondary":8,"tertiary":6,"residential":6,
          "living_street":4,"service":3,"track":3,"path":1.6,"footway":1.6,"cycleway":2.4,"pedestrian":4,"steps":1.6}


def parts(geometry, kind="Polygon"):
    if geometry.is_empty:
        return []
    if geometry.geom_type == kind:
        return [geometry]
    if hasattr(geometry, "geoms"):
        return [p for g in geometry.geoms for p in parts(g, kind)]
    return []


def positions(geometry):
    return int(shapely.get_num_coordinates(geometry))


def moved(geometries, function):
    """Apply an x/y array function to every coordinate in one call. The same
    per-point arithmetic as a scalar transform, without per-vertex Python calls."""
    return shapely.transform(geometries, lambda xy: np.column_stack(function(xy[:,0], xy[:,1])))


def road_buffers(geometries, widths):
    # Built once per geometry list; barrier queries only clip and union them.
    return shapely.buffer(np.array(geometries, dtype=object), np.array(widths)/2+0.8, quad_segs=16, cap_style="square", join_style="mitre")


def source_ids(feature):
    return feature["properties"].get("_city_sources", [feature["properties"]["osm_source_id"]])


def _key(geometry):
    return (*geometry.bounds, geometry.normalize().wkb_hex)


def strict_rings(geometry):
    rings = [geometry.exterior, *geometry.interiors]
    return all(ring.is_simple and len(set(ring.coords[:-1])) == len(ring.coords)-1 for ring in rings) and not any(a.intersects(b) for i,a in enumerate(rings) for b in rings[i+1:])


def is_building(feature, geometry):
    p = feature["properties"]
    return geometry.geom_type != "LineString" and not (p.get("osm_region") or p.get("_city_paint") or p.get("landuse") in ("forest","orchard"))


def clear_width(feature):
    """Width buildings keep clear of; estimated structures add 1.6 m (20 map cm)
    each side for native bridge/tunnel safety furniture."""
    p = feature["properties"]
    return float(p.get("width_m", 8)) + (3.2 if "_city_estimated_m" in p else 0.0)


def is_walking(feature, structural=frozenset()):
    """Ground pedestrian ways, including closed loops not joined to a structure."""
    p = feature["properties"]
    if p.get("_city_road_tags", {}).get("highway") not in PEDESTRIAN or p.get("road_kind", "ground") != "ground" or "elevations_m" in p:
        return False
    if "_city_estimated_m" in p:
        return False
    return "osm_node_refs" not in p or ("osm_loop_range" in p and structural.isdisjoint(p["osm_node_refs"]))


class Generalizer:
    def __init__(self, collection, options, review=None):
        from osm_review import Review
        self.review = review if review is not None else Review()
        self.excluded_sources = set()
        self.collection = collection
        self.projection = Coordinates(options)
        self.remaining = MAX_WORK
        self.features = []
        self.surface_mappings = Counter()
        self.widened_roads = 0
        self.estimated_widths = Counter()
        # Meter precision in the source frame, before the single 1:8 adoption.
        # Scalars or coordinate arrays; arrays give the same per-point values.
        def project(x, y, z=None):
            xx, yy = self.projection.transformer.transform(np.asarray(x, dtype=float), np.asarray(y, dtype=float), errcheck=True)
            return xx - self.projection.origin_xy[0], yy - self.projection.origin_xy[1]
        self.project = project
        from pyproj.enums import TransformDirection
        def inverse(x, y, z=None):
            return self.projection.transformer.transform(np.asarray(x, dtype=float) + self.projection.origin_xy[0], np.asarray(y, dtype=float) + self.projection.origin_xy[1], direction=TransformDirection.INVERSE, errcheck=True)
        self.inverse = inverse
        for feature in collection["features"]:
            feature = deepcopy(feature)
            geometry = shape(feature["geometry"])
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError("City optimization requires valid original geometry; no automatic repair")
            geometry = moved(geometry, project)
            if geometry.geom_type == "LineString":
                p = feature["properties"]
                if "width_m" not in p:
                    road_class = p.get("_city_road_tags",{}).get("highway","road")
                    p["width_m"] = WIDTHS.get(road_class,8)
                    self.estimated_widths[road_class] += 1
                original = p.get("surface", "asphalt")
                mapped = SURFACES.get(original, "asphalt")
                if mapped != original:
                    self.surface_mappings[(original, mapped)] += 1
                    p["surface"] = mapped
                if float(p.get("width_m", 8)) < 1.6:
                    p["width_m"] = 1.6  # Current-v1 minimum width: 20 map cm.
                    self.widened_roads += 1
            self.features.append((feature, geometry))
        self.before = self.counts(self.features)
        self.level_structures = sum(bool(f["properties"].get("_city_level_structure")) for f,g in self.features)
        self.road_geometries = [g for f, g in self.features if g.geom_type == "LineString"]
        self.road_widths = [max(0.01, float(f["properties"].get("width_m", 8))) for f,g in self.features if g.geom_type == "LineString"]
        self.road_tree = STRtree(self.road_geometries)
        self.road_buffers = road_buffers(self.road_geometries, self.road_widths)
        self.ground_geometries = [g for f,g in self.features if g.geom_type == "LineString" and f["properties"].get("road_kind","ground") == "ground"]
        self.ground_widths = [clear_width(f) for f,g in self.features if g.geom_type == "LineString" and f["properties"].get("road_kind","ground") == "ground"]
        self.ground_buffers = road_buffers(self.ground_geometries, self.ground_widths)
        self.protected_areas = [g for f,g in self.features if g.geom_type != "LineString" and (f["properties"].get("protected") or f["properties"].get("landuse") in ("water","wetland","forest","orchard","park","nature_reserve"))]
        self.area_tree = STRtree(self.protected_areas)
        self.area_array = np.array(self.protected_areas, dtype=object)
        # Projection can invalidate a source area; its overlay may then fail
        # and must fail inside the group, as an eagerly built barrier does.
        self.invalid_areas = ~shapely.is_valid(self.area_array) if len(self.area_array) else np.zeros(0, dtype=bool)
        self.barrier_buffers = self.road_buffers
        self.barrier_tree = self.road_tree
        self.max_width = max(self.road_widths, default=0)
        self.input_ids = sorted({s for f,g in self.features for s in source_ids(f)})
        self.uses = Counter(ref for f,g in self.features if g.geom_type == "LineString"
                            for ref in set(f["properties"].get("osm_node_refs", f["properties"].get("_city_refs", []))))
        self.trim_windows = {}
        self.context = {}
        self.reviewed = len(self.review.excluded)

    def spend(self, count=1):
        self.remaining -= count
        if self.remaining < 0:
            raise ValueError("City optimization spatial work budget exceeded; protected geometry was not discarded")

    @staticmethod
    def counts(items):
        counts = dict(features=len(items), positions=0, roads=0, buildings=0, areas=0)
        for feature, geometry in items:
            counts["positions"] += positions(geometry)
            counts["roads" if geometry.geom_type == "LineString" else "areas" if feature["properties"].get("osm_region") or feature["properties"].get("_city_paint") or feature["properties"].get("landuse") in ("forest", "orchard") else "buildings"] += 1
        return counts

    def barrier(self, geometry, extra=0):
        """Query and charge the barrier now; return a cached builder of its union,
        which callers need only when filling or simplification can add area."""
        window = geometry.envelope.buffer(extra + self.max_width / 2 + 0.8).envelope
        ids = self.barrier_tree.query(window)
        self.spend(len(ids))
        # A buffer's envelope lies within its source bounds grown by the distance,
        # so an empty query of that box is the same as the exact (costly) query.
        x0, y0, x1, y1 = geometry.bounds
        reach = extra + 0.16 + 1e-6
        areas = self.area_tree.query(box(x0-reach, y0-reach, x1+reach, y1+reach))
        if len(areas):
            areas = self.area_tree.query(geometry.buffer(extra+0.16).envelope)
        self.spend(len(areas))
        # Gap filling must not regrow into a junction surface the trim cleared.
        junctions = self.junction_tree.query(window)
        self.spend(len(junctions))
        union = []
        def build():
            if not union:
                union.append(unary_union(list(shapely.intersection(self.barrier_buffers[ids], window)) + list(shapely.intersection(self.area_array[areas], window)) + [self.junction_disks[i] for i in junctions]))
            return union[0]
        if self.invalid_areas[areas].any():
            build()
        return build

    def simplified_line(self, feature, geometry, tolerance):
        p = feature["properties"]
        refs = p.get("_city_refs")
        if tolerance == 0 or len(geometry.coords) <= 2 or not refs or len(refs) != len(geometry.coords) or "osm_node_refs" in p:
            return geometry
        # All source incidence, including junctions inside a way, stays fixed.
        cuts = [0] + [i for i in range(1, len(refs)-1) if self.uses[refs[i]] > 1] + [len(refs)-1]
        points = []
        for a,b in zip(cuts,cuts[1:]):
            segment = LineString(list(geometry.coords)[a:b+1])
            candidate = segment.simplify(tolerance, preserve_topology=True)
            if not candidate.is_simple:
                candidate = segment
            # Do not create a crossing with a road the source did not cross.
            ids = self.road_tree.query(candidate.envelope)
            self.spend(len(ids))
            if any(candidate.intersects(self.road_geometries[i]) and not segment.intersects(self.road_geometries[i]) for i in ids):
                candidate = segment
            points.extend(list(candidate.coords)[bool(points):])
        return LineString(points)

    def roads(self, gap):
        ordinary, fixed = [], []
        for f, g in self.features:
            if g.geom_type != "LineString":
                continue
            if "osm_node_refs" in f["properties"] or "_city_estimated_m" in f["properties"]:
                # Source graph and estimated structure profiles keep every vertex.
                fixed.append((deepcopy(f), g))
            else:
                ordinary.append((deepcopy(f), self.simplified_line(f, g, min(4.0, gap / 4))))
        endpoints = defaultdict(list)
        for index, (feature, geometry) in enumerate(ordinary):
            refs = feature["properties"].get("_city_refs")
            if refs:
                endpoints[refs[0]].append((index, 0))
                endpoints[refs[-1]].append((index, 1))
        def signature(feature):
            return json.dumps({k:v for k,v in feature["properties"].items() if not k.startswith("_city") and k != "osm_source_id"} | {"tags":feature["properties"].get("_city_road_tags", {})}, sort_keys=True)
        signatures = [signature(f) for f,g in ordinary]
        seen, output = set(), []
        for index, (feature, geometry) in enumerate(ordinary):
            if index in seen:
                continue
            seen.add(index)
            p = feature["properties"]
            refs = p.get("_city_refs")
            points = list(geometry.coords)
            sources = set(source_ids(feature))
            if refs:
                ends = [refs[0], refs[-1]]
                for side in (0, 1):
                    while self.uses[ends[side]] == 2 and len(endpoints[ends[side]]) == 2:
                        options = [(j,end) for j,end in endpoints[ends[side]] if j not in seen and signatures[j] == signatures[index]]
                        if len(options) != 1:
                            break
                        j, end = options[0]
                        other, shape_j = ordinary[j]
                        other_refs = other["properties"]["_city_refs"]
                        far = other_refs[0 if end == 1 else -1]
                        if far == ends[1-side]:
                            break  # Never create a self-loop that the native road contract cannot express.
                        new_points = list(shape_j.coords)
                        if end == side:
                            new_points.reverse()
                        if (new_points[-1] if side == 0 else new_points[0]) != points[0 if side == 0 else -1]:
                            break
                        if len(points) + len(new_points) > 1024:
                            break
                        points = new_points[:-1] + points if side == 0 else points + new_points[1:]
                        ends[side] = far
                        sources.update(source_ids(other))
                        seen.add(j)
                        self.spend()
                p["_city_ends"] = [str(ref) for ref in ends]
            p["_city_sources"] = sorted(sources)
            quantized = []
            for point in points:
                snapped = self.snap(point)
                if not quantized or snapped != quantized[-1]: quantized.append(snapped)
            if len(quantized) >= 2: points = quantized
            joined_geometry = LineString(points)
            if not joined_geometry.is_simple or points[0] == points[-1]:
                # Distinct OSM endpoint IDs can coincide geometrically. Keep
                # every edge in maximal simple paths, never weld those IDs or
                # discard a self-crossing source way.
                chains, chain = [], [points[0]]
                for point in points[1:]:
                    self.spend(len(chain))
                    trial = chain + [point]
                    if len(chain) > 1 and (trial[0] == trial[-1] or not LineString(trial).is_simple):
                        chains.append(chain)
                        chain = [chain[-1],point]
                    else:
                        chain = trial
                chains.append(chain)
                for chain in chains:
                    piece = deepcopy(feature)
                    piece["properties"].pop("_city_ends",None)
                    output.append((piece,LineString(chain)))
            else:
                output.append((feature, joined_geometry))
        # The exact importer splits a closed ground way at every source vertex.
        # Rejoin consecutive pieces without hiding an incident source junction
        # or creating a from==to road. Original traversal ranges survive.
        fixed.sort(key=lambda item:(item[0]["properties"].get("osm_way_id",0),item[0]["properties"].get("osm_loop_range",[0])[0]))
        joined = []
        for feature, geometry in fixed:
            p = feature["properties"]
            if joined and "osm_loop_range" in p and p.get("road_kind") == "ground" and "elevations_m" not in p:
                previous, previous_geometry = joined[-1]
                q = previous["properties"]
                if q.get("osm_way_id") == p.get("osm_way_id") and "osm_loop_range" in q and "elevations_m" not in q and len(q["osm_node_refs"])+len(p["osm_node_refs"])-1<=1024 and q["osm_loop_range"][1] == p["osm_loop_range"][0] and q["osm_node_refs"][-1] == p["osm_node_refs"][0] and self.uses[p["osm_node_refs"][0]] == 2 and q["osm_node_refs"][0] != p["osm_node_refs"][-1]:
                    q["osm_node_refs"] += p["osm_node_refs"][1:]
                    q["osm_loop_range"][1] = p["osm_loop_range"][1]
                    previous["geometry"]["coordinates"] += feature["geometry"]["coordinates"][1:]
                    joined[-1] = (previous,LineString(list(previous_geometry.coords)+list(geometry.coords)[1:]))
                    continue
            joined.append((feature,geometry))
        for index,(feature,geometry) in enumerate(joined):
            p=feature["properties"]
            if gap == 0 or "osm_loop_range" not in p or p.get("road_kind") != "ground" or "elevations_m" in p or len(geometry.coords)<=2:
                continue
            candidate=geometry.simplify(min(4.0,gap/4),preserve_topology=True)
            if not candidate.is_simple or len(candidate.coords)==len(geometry.coords): continue
            ids=self.road_tree.query(candidate.envelope)
            self.spend(len(ids))
            if any(candidate.intersects(self.road_geometries[i]) and not geometry.intersects(self.road_geometries[i]) for i in ids): continue
            # Douglas-Peucker retains original vertices. Record their exact
            # source positions, including fractional crop ends, so removed
            # degree-two bends never erase original traversal or junctions.
            original=list(geometry.coords)
            lookup={}
            for i,point in enumerate(original): lookup.setdefault(point,i)
            indices=[lookup[point] for point in candidate.coords]
            if indices!=sorted(set(indices)): continue
            start,end=p["osm_loop_range"]
            p["_city_loop_positions"]=[start if i==0 else end if i==len(original)-1 else math.floor(start)+i for i in indices]
            p["osm_node_refs"]=[p["osm_node_refs"][i] for i in indices]
            feature["geometry"]["coordinates"]=[feature["geometry"]["coordinates"][i] for i in indices]
            joined[index]=(feature,candidate)
        for index,(feature,geometry) in enumerate(joined):
            p = feature["properties"]
            if "_city_estimated_m" not in p: continue
            # Estimated structures share ground nodes with quantized roads. Snap
            # them to the same lattice, dropping a vertex (and its height) that
            # collapses onto its predecessor; ends never move apart.
            points, heights, refs = [], [], []
            for i, point in enumerate(geometry.coords):
                snapped = self.snap(point)
                if points and snapped == points[-1]:
                    if i == len(geometry.coords) - 1: points.pop(); heights.pop(); refs.pop()
                    else: continue
                points.append(snapped); heights.append(p["_city_estimated_m"][i]); refs.append(p["_city_refs"][i])
            if len(points) < 2: continue
            p["_city_estimated_m"], p["_city_refs"] = heights, refs
            joined[index] = (feature, LineString(points))
        return joined + output

    def snap(self, point):
        """Nearest whole 1:8 map centimetre in this projection's local metres."""
        snapped = []
        for axis,value in enumerate(point[:2]):
            cm = round((value+self.projection.local[axis])*100)
            game_cm = math.copysign(math.floor(abs(cm)/8+0.5),cm)
            snapped.append(game_cm*0.08-self.projection.local[axis])
        return tuple(snapped)

    def polygon_group(self, group, gap, buildings):
        try:
            return self._polygon_group(group, gap, buildings)
        except GEOSException:
            # A failed derived operation cannot repair, erase or relabel source
            # geometry. Keep that complete group unmerged and disclose the cost.
            self.retained_groups += 1
            return self.unmerged(group)

    def unmerged(self, group):
        # Unmerged members still use the map-centimetre lattice; an erased one
        # is restored by the source coverage step.
        snapped = [(f,shapely.set_precision(g, 0.08)) for f,g in group]
        return [(deepcopy(f),g) for f,g in snapped if not g.is_empty]

    def _polygon_group(self, group, gap, buildings):
        # Bound each GEOS operation independently; dense tiles split in source
        # order, never allocate an all-city pairwise distance/union matrix.
        if len(group) > MAX_GROUP:
            return [item for start in range(0, len(group), MAX_GROUP)
                    for item in self.polygon_group(group[start:start+MAX_GROUP], gap, buildings)]
        self.spend(len(group))
        shapes = [g for f,g in group]
        original = unary_union(shapes)
        protected_holes = unary_union([Polygon(ring) for g in shapes for part in parts(g) for ring in part.interiors]).difference(original)
        candidate = original
        barrier = self.barrier(original, gap) if buildings else None
        if gap and buildings and len(group) > 1:
            # Closing may fill only short gaps, and can never add solid geometry
            # inside a source road corridor or an existing courtyard.
            closed = unary_union([g.buffer(gap/2, quad_segs=1, join_style="mitre") for g in shapes]).buffer(-gap/2, quad_segs=1, join_style="mitre")
            filler = closed.difference(original).difference(barrier()).difference(protected_holes)
            candidate = unary_union(parts(original.union(filler)))
        tolerance = min(4.0 if buildings else 8.0, gap / 4)
        simpler = candidate.simplify(tolerance, preserve_topology=True)
        if buildings:
            grown = simpler.difference(candidate)
            if (not grown.is_empty and not grown.intersection(barrier()).is_empty) or not simpler.intersection(protected_holes).is_empty:
                simpler = candidate
        if not simpler.is_valid or simpler.is_empty:
            raise GEOSException("Derived polygon is invalid; retain the complete original group")
        # The final 1:8 map has whole centimetres. Snap derived boundaries to
        # that same lattice before inverse projection, so sub-centimetre buffer
        # slivers cannot become duplicate vertices during native adoption.
        snapped = shapely.set_precision(simpler, 0.08)
        if snapped.is_empty:
            self.retained_groups += 1
            return self.unmerged(group)
        simpler = snapped
        strict = all(strict_rings(g) for g in parts(simpler))
        if not strict and not protected_holes.is_empty:
            # Open, rather than fill, a courtyard which touches an outer edge
            # after map-centimetre rounding. At most two game centimetres of
            # additional clearance; original open space remains open.
            simpler = shapely.difference(simpler, protected_holes.buffer(0.16, join_style="mitre"), grid_size=0.08)
            strict = all(strict_rings(g) for g in parts(simpler))
        geometries = sorted(parts(simpler), key=_key)
        # Large/complex merged courtyards stay as smaller valid source groups.
        too_complex = not strict or any(buildings and (len(g.interiors) > 16 or positions(g) > 512) for g in geometries)
        if len(group) > 1 and too_complex:
            middle = len(group)//2
            return self.polygon_group(group[:middle], gap, buildings) + self.polygon_group(group[middle:], gap, buildings)
        output = []
        members = np.array(shapes, dtype=object)
        for geometry in geometries:
            contributors = [group[i] for i in np.flatnonzero(shapely.intersects(members, geometry.buffer(0.08)))]
            if not contributors:
                # GEOS closing can leave an isolated floating-point filler
                # sliver. It is newly derived, never an original component.
                # Do not invent a building for it; source coverage is checked
                # independently on the complete output below.
                continue
            feature = deepcopy(contributors[0][0])
            p = feature["properties"]
            p["_city_sources"] = sorted({identity for f,g in contributors for identity in source_ids(f)})
            if buildings and len(contributors) > 1:
                total = sum(g.area for f,g in contributors)
                p["height_m"] = round(sum(float(f["properties"].get("height_m", 12))*g.area for f,g in contributors)/total, 2)
                p["_city_estimated_height"] = True
            output.append((feature, geometry))
        return output

    def polygons(self, gap):
        if "groups" not in self.context:
            start, retained = self.remaining, self.retained_groups
            self.context.update(zip(("prepared", "fixed", "groups"), self.prepare()), trimmed=set(self.trimmed_buildings),
                                prepare_work=start-self.remaining, prepare_retained=self.retained_groups-retained)
        else:
            # Same road space: replay the work charges and disclosures. Review
            # exclusions are already recorded (idempotent) in the shared sets.
            self.spend(self.context["prepare_work"])
            self.retained_groups += self.context["prepare_retained"]
            self.trimmed_buildings.update(self.context["trimmed"])
        self.prepared, groups = self.context["prepared"], self.context["groups"]
        output = list(self.context["fixed"])
        for building, group in groups:
            output.extend(self.polygon_group(group, gap, building))
        return output

    def prepare(self):
        """Road-trimmed sources, protected buildings and aggregation groups. They
        depend on the derived road space only, not on the gap being filled."""
        groups, fixed = defaultdict(list), []
        prepared = []
        for index, (f,g) in enumerate(self.features):
            if g.geom_type == "LineString":
                continue
            p = f["properties"]
            building = not (p.get("osm_region") or p.get("landuse") in ("forest", "orchard"))
            if building:
                if index not in self.trim_windows:
                    self.trim_windows[index] = g.buffer(self.max_width/2+0.8).envelope
                ids = self.ground_tree.query(self.trim_windows[index])
                self.spend(len(ids))
                road_space = unary_union([self.ground_barriers[i].intersection(g.envelope) for i in ids])
                trimmed = g.difference(road_space)
                if trimmed.is_empty:
                    for identity in source_ids(f):
                        self.review.reject(identity, "Building footprint is entirely inside derived ground-road space; it cannot retain a solid at 1:8 without blocking the road. Road widths may be estimates. Explicit source exclusion is required.")
                        self.excluded_sources.add(identity)
                    continue
                if not trimmed.is_empty and trimmed.area < g.area-0.0001:
                    self.trimmed_buildings.update(source_ids(f))
                    g = trimmed
            prepared.append((f,g,building))
        for f,g,building in prepared:
            # Exclude the whole source object, including other multipart pieces,
            # only through the existing explicit ID/reason review contract.
            if self.excluded_sources.intersection(source_ids(f)):
                continue
            p = f["properties"]
            protected = building and (p.get("_city_name") or p.get("_city_landmark") or float(p.get("height_m", 12)) >= 40 or p.get("usage") in ("public", "hospital", "school", "church", "cathedral"))
            if protected:
                # Preserve identity/height and keep it separate. Quantization
                # still uses the same map-centimetre lattice as other geometry.
                fixed.extend(self.polygon_group([(f,g)],0,True))
                continue
            properties = {k:v for k,v in p.items() if not k.startswith("_city") and k not in ("osm_source_id", "height_m")}
            height_band = math.floor(float(p.get("height_m", 12))/8) if building else 0
            # A fixed source-metre grid bounds aggregation extent independently
            # of the city, output origin, crop size or source object order.
            centre = g.centroid
            key = (building, math.floor(centre.x/256), math.floor(centre.y/256), height_band, json.dumps(properties, sort_keys=True))
            groups[key].append((f,g))
        return [(f,g) for f,g,building in prepared], fixed, [(key[0], sorted(groups[key], key=lambda item:(source_ids(item[0]), _key(item[1])))) for key in sorted(groups)]

    def native_polygon_parts(self, geometry, depth=0):
        result = []
        for part in parts(geometry):
            self.spend(positions(part))
            if positions(part) <= 512 and len(part.interiors) <= 16 and strict_rings(part):
                result.append(part)
                continue
            if depth >= 16: raise ValueError("City building partition budget exceeded")
            x0,y0,x1,y1 = part.bounds
            axis = 0 if x1-x0 >= y1-y0 else 1
            middle = round(((x0+x1) if axis == 0 else (y0+y1))/2/0.08)*0.08
            rectangles = [box(x0-1,y0-1,middle-0.16,y1+1),box(middle+0.16,y0-1,x1+1,y1+1)] if axis == 0 else [box(x0-1,y0-1,x1+1,middle-0.16),box(x0-1,middle+0.16,x1+1,y1+1)]
            for rectangle in rectangles:
                result.extend(self.native_polygon_parts(shapely.intersection(part,rectangle,grid_size=0.08),depth+1))
        return result

    def paint_parts(self, geometry, depth=0):
        # Native surface areas are simple and hole-free. Cut through each hole
        # (or the middle of an oversized part) along a whole map-centimetre line.
        result = []
        for part in parts(geometry):
            self.spend(positions(part))
            holes = [h for h in part.interiors if max(h.bounds[2]-h.bounds[0], h.bounds[3]-h.bounds[1]) >= 2]
            part = Polygon(part.exterior, holes)  # Sub-centimetre holes are painted over.
            if not holes and positions(part) <= PAINT_VERTICES + 1:
                result.append(part)
                continue
            if depth >= 32: raise ValueError("City paint partition budget exceeded")
            x0,y0,x1,y1 = holes[0].bounds if holes else part.bounds
            axis = 0 if x1-x0 >= y1-y0 else 1
            cut = math.floor(((x0+x1) if axis == 0 else (y0+y1))/2)
            x0,y0,x1,y1 = part.bounds
            halves = [box(x0-1,y0-1,cut,y1+1),box(cut,y0-1,x1+1,y1+1)] if axis == 0 else [box(x0-1,y0-1,x1+1,cut),box(x0-1,cut,x1+1,y1+1)]
            for half in halves:
                result.extend(self.paint_parts(shapely.intersection(part,half,grid_size=1),depth+1))
        return result

    def paint(self, walking):
        """Paths, footways and cycleways become ground paint, not road records.

        Their source-width ribbons are united on the 1:8 map-centimetre lattice and
        cut per native cell, so the pieces never overlap. Each piece keeps every
        source way it covers; its surface is the one covering most of its area.
        """
        if not walking:
            return []
        lx, ly = self.projection.local
        to_map = lambda x, y: ((x+lx)*12.5, (y+ly)*12.5)
        from_map = lambda x, y: (x*0.08-lx, y*0.08-ly)
        owners = []
        for feature, geometry in walking:
            self.spend(positions(geometry))
            owners.append((source_ids(feature), feature["properties"].get("surface", "concrete")))
        ribbons = shapely.buffer(np.array([g for f,g in walking], dtype=object), np.array([float(f["properties"].get("width_m", 1.6)) for f,g in walking])/2, quad_segs=2)
        ribbons = list(shapely.set_precision(moved(ribbons, to_map), 1))
        tree = STRtree(ribbons)
        cells = defaultdict(list)
        for index, ribbon in enumerate(ribbons):
            x0,y0,x1,y1 = ribbon.bounds
            for i in range(math.floor(x0/PAINT_CELL), math.floor(x1/PAINT_CELL)+1):
                for j in range(math.floor(y0/PAINT_CELL), math.floor(y1/PAINT_CELL)+1):
                    cells[(i,j)].append(index)
        output = []
        for i, j in sorted(cells):
            cell = box(i*PAINT_CELL, j*PAINT_CELL, (i+1)*PAINT_CELL, (j+1)*PAINT_CELL)
            self.spend(len(cells[(i,j)]))
            local = shapely.intersection(shapely.union_all([ribbons[k] for k in cells[(i,j)]], grid_size=1), cell, grid_size=1)
            for piece in self.paint_parts(local):
                sources, surfaces = set(), Counter()
                for k in tree.query(piece):
                    self.spend()
                    area = shapely.intersection(ribbons[k], piece).area
                    if area > 0:
                        sources.update(owners[k][0])
                        surfaces[owners[k][1]] += area
                if not sources:
                    continue  # A lattice sliver of a ribbon already covered elsewhere.
                surface = sorted(surfaces.items(), key=lambda item:(-item[1], item[0]))[0][0]
                output.append((dict(type="Feature", properties=dict(_city_paint=surface, _city_sources=sorted(sources), osm_source_id=min(sources)), geometry=None), piece))
        self.paint_ways = len(walking)
        return [(f,g) for (f,_),g in zip(output, moved([g for f,g in output], from_map))]

    def resolve_buildings(self, items):
        buildings = [(f,g) for f,g in items if is_building(f,g)]
        rest = [(f,g) for f,g in items if not is_building(f,g)]
        buildings.sort(key=lambda item:(-float(item[0]["properties"].get("height_m",12)),not bool(item[0]["properties"].get("_city_name")),-item[1].area,source_ids(item[0]),_key(item[1])))
        tree = STRtree([g for f,g in buildings])
        accepted = {}
        self.overlap_sources = set()
        for index,(feature,geometry) in enumerate(buildings):
            candidates = [int(i) for i in tree.query(geometry.buffer(0.16).envelope) if int(i) in accepted]
            self.spend(len(candidates))
            neighbors = [i for i in candidates if accepted[i][1].buffer(0.16,join_style="mitre").intersects(geometry)]
            if neighbors:
                occupied = unary_union([accepted[i][1].buffer(0.16,join_style="mitre") for i in neighbors])
                trimmed = shapely.difference(geometry,occupied,grid_size=0.08)
                self.overlap_sources.update(source_ids(feature))
                if trimmed.is_empty:
                    # A fully enclosed/duplicate building is represented by its
                    # enclosing volume. Keep every source ID and recorded name;
                    # the chosen taller envelope's height is disclosed as an
                    # approximation for the absorbed object, never a survey.
                    owner = max(neighbors,key=lambda i:(accepted[i][1].intersection(geometry).area,-i))
                    p = accepted[owner][0]["properties"]
                    p["_city_sources"] = sorted(set(source_ids(accepted[owner][0]))|set(source_ids(feature)))
                    names = set(p.get("_city_names",[])) | set(feature["properties"].get("_city_names",[]))
                    names.update(n for n in (p.get("_city_name"),feature["properties"].get("_city_name")) if n)
                    p["_city_names"] = sorted(names)
                    p["_city_estimated_height"] = True
                    continue
                geometry = trimmed
            accepted[index] = (feature,geometry)  # Owned by this candidate; parts copy below.
        for feature,geometry in accepted.values():
            rest.extend((deepcopy(feature),part) for part in self.separated_parts(geometry))
        return rest

    def separated_parts(self, geometry):
        # Native buildings may not even touch. Parts of one source geometry that
        # meet at a point keep the same 0.16 m clearance as other neighbours.
        kept = []
        for part in self.native_polygon_parts(geometry):
            self.spend(len(kept))
            near = [k for k in kept if k.intersects(part)]
            if not near:
                kept.append(part)
                continue
            trimmed = shapely.difference(part, unary_union([k.buffer(0.16, join_style="mitre") for k in near]), grid_size=0.08)
            kept.extend(p for p in self.native_polygon_parts(trimmed) if not any(p.intersects(k) for k in kept))
        return kept

    def road_space(self, gap):
        """Derived roads and the space buildings keep clear of; ground pedestrian
        ways are split off for paint."""
        roads = self.roads(gap)
        self.barrier_buffers = np.concatenate([self.road_buffers, road_buffers([g for f,g in roads], [max(0.01,float(f["properties"].get("width_m",8))) for f,g in roads])])
        self.barrier_tree = STRtree(self.road_geometries + [g for f,g in roads])
        ground = [(g,clear_width(f)) for f,g in roads if f["properties"].get("road_kind","ground") == "ground"]
        lines = list(zip(self.ground_geometries,self.ground_widths))+ground
        self.ground_barriers = list(self.ground_buffers) + list(road_buffers([g for g,w in ground], [w for g,w in ground]))
        # A junction surface is the hull of its approach mouths, which reaches up to
        # √2 × the widest half width from the node; keep buildings outside it too.
        ends = defaultdict(list)
        for g,w in lines:
            for x,y in (g.coords[0], g.coords[-1]):
                ends[(round(x,2),round(y,2))].append(w)
        self.junction_disks = [shapely.Point(point).buffer(max(widths)/2*math.sqrt(2)+0.8, quad_segs=4)
                               for point,widths in sorted(ends.items()) if len(widths) > 1]
        self.junction_tree = STRtree(self.junction_disks)
        self.ground_barriers += self.junction_disks
        self.ground_tree = STRtree(self.ground_barriers)
        # Pedestrian ways still keep merged buildings and derived road space
        # clear above, but are represented as painted ground below.
        structural = frozenset(ref for f,g in roads if f["properties"].get("road_kind","ground") != "ground" or "elevations_m" in f["properties"]
                               for ref in f["properties"].get("osm_node_refs", []))
        return [(f,g) for f,g in roads if not is_walking(f, structural)], [(f,g) for f,g in roads if is_walking(f, structural)]

    def candidate(self, gap):
        self.remaining = MAX_WORK
        self.retained_groups = 0
        self.trimmed_buildings = set()
        # Road space depends on the gap only through the line tolerance, equal for
        # 16-64 m gaps. Reuse it and everything derived from it (trimmed sources,
        # protected buildings, groups, paint), replaying their work charges.
        shared = ("barrier_buffers", "barrier_tree", "ground_barriers", "junction_disks", "junction_tree", "ground_tree")
        tolerance = min(4.0, gap/4)
        if self.context.get("tolerance") == tolerance:
            self.spend(self.context["road_work"])
            for name in shared:
                setattr(self, name, self.context[name])
        else:
            # Exclusions come only from the road space of the candidate kept.
            self.excluded_sources = set()
            self.review.restore(self.reviewed)
            start = self.remaining
            driving, walking = self.road_space(gap)
            self.context = dict(tolerance=tolerance, driving=driving, walking=walking, road_work=start-self.remaining,
                                **{name: getattr(self, name) for name in shared})
        driving, walking = self.context["driving"], self.context["walking"]
        items = driving + self.polygons(gap)
        # A multipart source remains fully represented by separate native
        # polygons. Touching components must not be misrepresented as holes.
        items = [(deepcopy(f),native) for f,g in items for part in ([g] if g.geom_type == "LineString" else parts(g))
                 for native in ([part] if part.geom_type == "LineString" or is_building(f,part) else self.native_polygon_parts(part))]
        # A source erased by merging or quantization keeps its road-trimmed shape
        # on the map-centimetre lattice, then meets the same overlap partition.
        covered = {identity for f,g in items + walking for identity in source_ids(f)}
        for f,g in self.prepared:
            if set(source_ids(f)) <= covered or self.excluded_sources.intersection(source_ids(f)):
                continue
            snapped = shapely.set_precision(g, 0.08)
            if snapped.is_empty:
                continue
            self.retained_groups += 1
            covered.update(source_ids(f))
            items.extend((deepcopy(f),part) for part in (parts(snapped) if is_building(f,snapped) else self.native_polygon_parts(snapped)))
        items = self.resolve_buildings(items)
        if "paint" in self.context:
            self.spend(self.context["paint_work"])
        else:
            start, self.paint_ways = self.remaining, 0
            self.context.update(paint=self.paint(walking))
            self.context.update(paint_work=start-self.remaining, paint_ways=self.paint_ways)
        self.paint_ways = self.context["paint_ways"]
        # Output features are completed in place below; cached paint gets copies.
        items += [(dict(f, properties=dict(f["properties"], _city_sources=list(f["properties"]["_city_sources"]))), g) for f,g in self.context["paint"]]
        self.trimmed_buildings.difference_update(self.excluded_sources)
        def order(item):
            feature, geometry = item
            p = feature["properties"]
            traversal = (0,p.get("osm_loop_range",[p.get("_city_crop_feature",0)])[0]) if "osm_node_refs" in p else (1,_key(geometry))
            return geometry.geom_type,source_ids(feature),traversal
        items.sort(key=order)
        # Every supported source object remains represented, including split
        # parts. Unsupported exclusions are a separate, explicitly reviewed list.
        retained = {identity for f,g in items for identity in source_ids(f)}
        expected = set(self.input_ids) - self.excluded_sources
        missing = expected - retained
        if missing:
            # Quantization or a derived courtyard clearance must not erase a
            # small source island. Keep those original features unmerged; they
            # still face the ordinary native geometry/output budget checks.
            for feature, geometry in self.features:
                if missing.intersection(source_ids(feature)):
                    items.append((deepcopy(feature),geometry))
                    self.retained_groups += 1
            items.sort(key=order)
            retained = {identity for f,g in items for identity in source_ids(f)}
        if retained != expected:
            raise ValueError("City optimization source coverage mismatch")
        result = {k:deepcopy(v) for k,v in self.collection.items() if k != "features"}
        result["features"] = []
        groups = []
        # Protected graph geometry must preserve its exact source order and
        # values; recomputing it would invalidate loop/crop height provenance.
        derived = iter(moved([g for f,g in items if "osm_node_refs" not in f["properties"]], self.inverse))
        for feature, geometry in items:
            p = feature["properties"]
            p["_city_sources"] = source_ids(feature)
            groups.append(dict(source_ids=p["_city_sources"], name=p.get("_city_name", ""), names=p.get("_city_names",[]), estimated_height=bool(p.get("_city_estimated_height"))))
            if "osm_node_refs" not in p:
                feature["geometry"] = json.loads(json.dumps(mapping(next(derived))))
            result["features"].append(feature)
        meta = dict(profile=PROFILE, scale_denominator=SCALE, gap_m=gap, grid_m=0.08,
                    vegetation_spacing_m=32, vegetation_density_per_mille=750,
                    surface_mappings=[dict(source=s,target=t,features=n) for (s,t),n in sorted(self.surface_mappings.items())],
                    widened_roads=self.widened_roads, minimum_road_width_m=1.6,
                    estimated_road_widths=dict(sorted(self.estimated_widths.items())),
                    road_clearance_m=0.8, trimmed_building_sources=sorted(self.trimmed_buildings),
                    building_clearance_m=0.16, polygon_partition_gap_m=0.32, overlap_adjusted_sources=sorted(self.overlap_sources),
                    line_tolerance_m=min(4.0, gap/4), polygon_tolerance_m=min(8.0, gap/4),
                    before=self.before, after=self.counts(items), source_ids=sorted(expected),
                    unmerged_numeric_groups=self.retained_groups, painted_pedestrian_ways=self.paint_ways,
                    level_structures=self.level_structures,
                    estimated_structure_roads=sum("_city_estimated_m" in f["properties"] for f,g in items),
                    groups=groups, protected_buildings=sum(bool(f["properties"].get("_city_name") or f["properties"].get("_city_landmark") or float(f["properties"].get("height_m",12))>=40) for f,g in items if is_building(f,g)))
        return result, meta


def candidates(collection, options, review=None):
    """Largest gap first: it merges and simplifies most. Callers take the first
    candidate that fits; smaller gaps are built only after a failure. A gap whose
    work budgets or road space cannot be met yields (None, failure) instead."""
    worker = Generalizer(collection, options, review)
    # Dense sources skip the 0–2 m gaps: a 4 m source gap is only 0.5 m on the
    # 1:8 map; all protected geometry and final admission still apply.
    for gap in reversed(LEVELS[2 if worker.before["features"] > 20000 else 0:]):
        try:
            result = worker.candidate(gap)
        except ValueError as exc:
            # Own work/partition budgets, or a building the straighter road covers; a
            # smaller gap keeps more bends. The review's aggregate quota stays fatal.
            if not (str(exc).startswith("City ") and "budget" in str(exc)) and "Explicit source exclusion is required" not in str(exc):
                raise
            result = None, dict(gap_m=gap, failure=str(exc))
        yield result
