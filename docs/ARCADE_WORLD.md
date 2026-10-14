# Authored default worlds

`examples/default-worlds` contains seven compact, original v1 worlds. Each has
free roam and three recommended ordinary-road courses: **intro 600–900 m**, **tour
1,400–2,000 m**, **technical 1,000–1,500 m**. These are geometric distances from the
first gate to the finish, not completion-time promises. Map and course content
changes require fresh hashes and sealing; human completion remains unverified.

| Theme | Metres | Places and optional branch |
| --- | --- | --- |
| Village Driving Park | 640 × 512 | Clock market, garden cottages, orchard farm, willow bridges; low farm ramp |
| Neon Harbor | 960 × 768 | Neon street, warehouse alleys, cargo quays, channel bridges; dock rail |
| Deep Forest | 896 × 896 | Ranger clearing, layered canopy, lake camp, gorge bridges; raised rock-lane ramp |
| Red Canyon | 1152 × 640 | Strata corridor, natural arch, dry wash, quarry; raised jump lane |
| Snow Mountain | 832 × 1056 | Lodge village, fir valley, frozen lake, summit road; low snow-lane ramp |
| Machine Factory | 768 × 768 | Production halls, process pipes/tanks, maintenance, shipping; raised service rail |
| Sky Amusement Park | 960 × 800 | Entrance plaza, carousel, wheel terrace, coaster court; upper jump lane |

`default_worlds.py`, the seven `default_<theme>.py` recipes and
`compact_worlds.py` own the layouts. Major roads and facilities have explicit metre
coordinates. Irregular species/age clusters fill declared habitat polygons only;
road margins, water and optional branch corridors exclude scenery. Vehicles,
models and road widths retain their actual scale. Frontages use the model's depth
for service props. Paired primary/distant models belong to MapKit; solid landmarks
and boundaries remain visible on Low. General **New region** is independent.

Terrain uses one integer 2 m grid sliced into 32 m execution cells. Roads own their
cut/fill shoulders; bridge approaches separate structural decks from junctions.
Village water and riverbed share a straight sampled shore. The final native terrain,
including bridge crossings, is checked against the water edge. Ice is a static
surface appearance/solid, with existing physics.

## Roads, tracks and courses

**Roads & tracks** and **Terrain & scenery** edit one document. Moving a shared
road node updates its connected roads, track entry and attachments atomically;
Undo/Redo and save/reopen keep the source. Original heightmaps remain immutable.
See [road editing](TRACK_EDIT_PERFORMANCE.md) and [v1 contracts](CURRENT_V1.md).

Each special lane has an ordinary fork/merge, a separate continuous road bypass,
a connected track entry and an aligned exit/runout. Course gates lie outside the
whole branch; no route requires a ramp, jump or rail. The authoring tool submits
ordinary IDs and `track:<instance>` references to MapKit's existing v1 resolver.
`mapkit compose-world DOCUMENT.json SOURCE.json ATTACHMENTS.json NEW.json` applies
the source and attachments transactionally; the compiler owns all derived geometry.
`region.json.track_surfaces` records actual execution IDs for Runtime probes.

The source sidecars retain the authored track and attachment inputs. Unsafe
terrain, occupied space, road intersections and supports block export. Free roam
may retain route drafts; every distributed recommendation is sealed independently.

## Generate and publish

Always choose a fresh destination, preserving existing maps and user data:

```sh
rtk proxy .venv/bin/python map-editor/scripts/default_worlds.py /absolute/new-worlds --theme village --kit map-kit --cli map-kit/target/debug/mapkit
```

The authoring fingerprint includes common helpers and the owning model sources.
Generation compiles roads/tracks, audits road collision and validates every cell.
Client preparation checks all maximum-vehicle eight-car grid corners, course gates,
actual branch surfaces and fork/merge heights before sealing. Publish all seven
candidates only after actual rendering and hash checks. Distribution remains at
most **256 MiB**, with textures at most **512 px**. See
[Client delivery](../../client/docs/ARCADE_WORLD.md).

## Actual rendering and validation

Use the root `run_godot_checks.py --project client --script render_default_world
--rendered` with absolute `DEFAULT_WORLD_SOURCE` and a new `DEFAULT_WORLD_OUTPUT`.
Set `DEFAULT_WORLD_THEME`, **`DEFAULT_WORLD_CAPTURE=1`**, **`DEFAULT_WORLD_REPEATS=1`**
and explicitly list `DEFAULT_WORLD_VIEWS` when all views are required: Client's
default captures no PNG and measures the first perspective view only.
`DEFAULT_WORLD_QUALITY=0|1|2` selects quality; width/height, warmup/frames, occlusion,
revisit and timeout controls are described in [MapKit diagnostics](../../map-kit/docs/RENDER_DIAGNOSTICS.md).

Recipes include entry, road districts, landmark, optional branch, distance and
whole-layout views, plus harbor night and accumulated snow. Perspective cameras
use a 1.7 m road eye and the common 68° FOV. Environment values are explicit.
Renderer reports bind PNGs to package SHA-256. Editor preview timings do not
establish Client performance. Measure the heaviest actual perspective views at
Low/Medium/High without simultaneous build/import work; fixed-scene targets are
p95 ≤16.7 ms and p99 ≤33.3 ms. Preparation delays and driving remain separate.

`test_default_worlds.py` checks dimensions, all terrain seams, water/road clearance,
connected ordinary routes, distance ranges, optional gates, paired models and
immutable destinations. `default_river_bank_validator` checks final native shore
faces. Shared track/attachment and document regressions cover placement, connections,
save/reopen, execution geometry and resource retirement.

Detailed driving, actual completion, Android device performance and final art
acceptance remain user checks.
