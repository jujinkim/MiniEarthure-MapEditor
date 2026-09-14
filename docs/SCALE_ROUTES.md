# L02 explicit road route evidence

`scripts/scale_routes.py` reads an existing mixed `scale_maps.py` source and
its unchanged indexed package. It writes a **new** `l02-road-routes-v1` test
sidecar. It does not modify `scale.json`, source geometry, packages, generation,
assets or any public MapKit contract. Normal MapKit/Runtime validation still
owns package admission. This tool is not pathfinding or a native audit receipt.

First restore the package into a new directory with the existing native CLI:

```sh
rtk proxy addons/mapkit/target/release/mapkit unpack-regions /existing/mixed.mkregions /new/restored 536870912
rtk proxy python3 scripts/scale_routes.py /existing/mixed-source /existing/mixed.mkregions /new/routes.json --restored /new/restored
rtk proxy python3 -B -m unittest discover -s tests -p 'test_scale_*.py' -v
```

Every source/payload hash must match the fixed source metadata. The package
index digest, native-restored document digest and payload record hashes bind
the sidecar to those exact bytes. The restored document must equal the source
semantically: only top-level record collection order and omitted empty optional
collections are normalized. Ordered road points, collision shapes and geometry
remain exact. Runtime subsequently audits all package records; front-index
identity checks cannot substitute for that audit.

The seven named routes use existing connected roads:

| Route | Road corridor | Coverage meaning |
| --- | --- | --- |
| `residential` | North/south grid one lot inside the eastern half, northern half | Roads adjacent to residential lots |
| `rural` | North/south grid one lot inside the western half, southern half | Roads adjacent to rural lots |
| `forest` | North/south grid one lot inside the eastern half, southern half | Roads adjacent to forest lots |
| `residential-forest` | Complete eastern north/south corridor | Ordered residential to forest transition |
| `urban-rural` | Complete western north/south corridor | Ordered urban to rural transition; avoids the blocked through-lot access street |
| `rural-forest` | East/west grid one lot inside the southern half | Ordered rural to forest transition |
| `bridge-grades` | Existing separate margin bridge, including both ramps | Actual 0→3→0 m support profile; no density-lot coverage |

Road IDs, shared graph endpoints, segment heights/materials, adjacent lot IDs
and kinds are retained in each segment. The grid road ends are trimmed by 8 m for spawn/stop clearance. The bridge
uses its ground ramp endpoints 16 m from each map edge, retaining both full
grades and additional braking room. A 2 km map yields 944 m single-density
corridors, 1,904 m transition corridors and a 1,968 m bridge route. These are straight
ordered waypoints, including changes of grade. Arbitrary turns and general
routing/access semantics are unsupported; flat reverse shuttles use the
additional source audit below.

The source audit requires at least a 4 m road width and checks a 2 m corridor
against transformed static collision boxes, building/vegetation envelopes and
heightmap-cell interiors. It does not reproduce procedural tree placement;
any intersecting vegetation envelope is conservatively rejected. Repetition
obstacles and nonzero ground-road heights are unsupported. The original forest
hill cells overlap planted areas and are deliberately not accepted by driving
the neighboring flat roads. Bridge ramps supply separate grade evidence.

Runtime collision rays and actual Client motion must still establish every
road's traversal, waypoint order and floor height. Static adjacency is neither
lot-interior traversal, visibility, human art approval nor all-density/platform
acceptance. Small-prefix runs must not claim complete corridor coverage.

Source and package bytes remain fixed. See [SCALE_MAPS](SCALE_MAPS.md) for the
original density/quality contract; the superproject's L02 route report owns
execution results, revisions, failed attempts and deferred acceptance.

## L02-RS stopping-room audit (2026-09-14)

New sidecars add `shuttle.format: l02-flat-shuttle-v1` to the six flat ground
asphalt corridors. Four metres outside each trimmed endpoint must remain on
the existing connected road. The same conservative obstacle audit extends its
bounds by four metres at both ends, preserving its one-metre half-width and
end padding. Any intersecting static object, vegetation or terrain envelope
rejects the sidecar. `stopping_margin_m`, audited `bounds_cm` and empty
`overlaps` accompany the capability. The tool never changes source/package
bytes to create space. Existing v1 sidecars without this field remain
forward-only; create a new destination to use timed reverse evidence.

Client independently checks the full corridor in each direction, actual
support, stopping positions and the unchanged native admission. This is
forward/reverse input along the same heading, not a 180-degree turn. Bridge
ramps have no shuttle capability; graded braking/turns and forest-interior
hill routes still need separate authoring and validation.

## L02-VR: separately authored 240 m shuttles (2026-09-14)

Use `--profile shuttle-240` with an existing mixed or dense source with an even
grid of at least eight lots. The default `full` profile and its original route
IDs/extents are unchanged. The new profile uses four connected 64 m lots with
8 m trimmed from each end, yielding a complete **240 m** route. It reuses the
same source/package/native-restoration identity, graph, obstacle and 4 m
stopping-room checks. Sources, packages, physics and speed/time limits stay fixed.

```sh
rtk proxy python3 scripts/scale_routes.py /existing/mixed-2000 /existing/mixed-256.mkregions /new/mixed-256-shuttles.json --restored /new/restored --profile shuttle-240
```

Mixed maps produce `urban-shuttle`, `residential-shuttle`, `rural-shuttle`,
`forest-shuttle`, `residential-forest-shuttle`, `urban-rural-shuttle` and
`rural-forest-shuttle`. Dense maps produce `urban-shuttle`. The four single-kind
routes are centered inside their quadrant; transitions span two lots on either
side of the original boundary. Exact source road IDs, endpoint trim, source
condition/size and `l02-shuttle-240-v1` profile are recorded in `authored_extent`.
Every segment retains its source height/surface and adjacent lot IDs/kinds.
Coverage is checked against the name, including both sides of each transition.

Select the new ID and `distance_m: 240` with `duration_s: 600` in the existing
Client runner. The current RC reverse cap permits a 240 m return in roughly
154 seconds before acceleration/stopping overhead. This makes a complete
round trip feasible; it is not an acceptance shortcut. Actual complete legs
in both directions, normal delta, four contacts/floor rays, zero rollback,
budget/retirement and stress speed/boundary evidence must still pass. Repeated
crossings of the same storage boundary do not demonstrate three distinct
storage regions or the entire 944/1,904 m original corridor.

No turns, bridge shuttles or forest-interior hill coverage is added. Short-route
sidecars are not native audit receipts, new public map formats or an assertion
that all source lots have been driven. Root L02-VR evidence owns measured scope;
the separate L02-V matrix owns remaining combinations and target-device gates.
