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
ordered waypoints, including changes of grade; arbitrary turns, reverse
shuttles and general routing/access semantics are unsupported and rejected.

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
