# Supported local imports and atomic adoption

**Import OSM / PBF** guides PBF selection → area selection → review → Apply using
the city profile at the chosen 1:D scale (default 1:3, [IMPORT_CITY](IMPORT_CITY.md)), budgets and explicit exclusions. An empty track
project proposes fitted bounds; populated maps retain their extent. Bounds,
composition and layer adoption share one Undo; cancel/failure preserves the map.
Ordinary vehicle roads split where they share original OSM nodes with other vehicle
roads before optimization; paths, footways, cycleways and pedestrian streets (and, in
the city profile, steps) keep independent ends (`osm_pedestrian_roads`), and the city profile paints the ground ones
instead ([IMPORT_CITY](IMPORT_CITY.md)). Surviving source endpoints retain identity
through crop/quantization; new cuts remain independent. Adoption asks MapKit for
ordinary source junctions it cannot build (for example a way doubling back) and turns
only those into separate road ends at the same position (`separated_junctions` in the
attribution). A junction with a bridge or tunnel arm keeps that arm joined to its
straightest partner (another structure first) and separates only the other arms, so a
ramp foot or deck joint gets no deck cap; when that pair still fails, every arm
separates and the `structure_end_separated` warning reports it. Explicit structural
junctions still fail review. Selection never rewrites geometry or infers height. See
[3D road editing](WORKBENCH.md).

Editor owns the MIT import adapters and document adoption; public MapKit owns native
geometry validation. Obtain source files separately and choose the source format
explicitly. Importing never overwrites source files, PBF/DEM, receipts, projects or
packages. The automatic OSM city profile is described in [IMPORT_CITY](IMPORT_CITY.md).

## Contract and units

[CURRENT_V1](CURRENT_V1.md) defines one shape per adapter; there is no recipe
selector or automatic converter. An ImportLayer adds nodes, roads, buildings, zones,
city ground paint (`surface_areas`), city barriers and building parts, and facility POIs with source provenance under a new 128-bit namespace, even when
the same bytes are reimported. References to existing objects, arbitrary map-value
mutation and deletions are rejected; the only map values an adoption sets are the
extent of an empty map, `free_roam` and, for a city layer on a map without one,
`ground_surface: concrete` (a different existing surface is kept with a warning;
Undo restores its absence).

Custom maps use real metres. OSM adoption divides coordinates, widths, heights,
clearances, barrier heights/thicknesses and vegetation spacing by the map scale denominator D once: the city
scale (1–8), or 8 for exact OSM. `authored_units` records `source_denominator: D`
and the profile `osm-import-1to{D}-v1` (`osm-import-1to8-v1` at 1:8); readers
accept only a profile matching the stored D and refuse unknown values or OSM
layers with different scales. Staged input keeps source units. Adopted vehicle road segments narrower than 150 cm (`road_width_floor_cm`,
about 2.5 widths of the 61 cm car) widen to it; pedestrian roads keep their estimate, each side stopping 20 cm (plus
sidewalk, and 20 cm safety furniture on structures) before the nearest new or existing building edge or courtyard wall; wider segments never change. Linked DEM uses the same stored D (map position × D for lookup,
relative elevation ÷ D). Standalone DEM, GeoJSON and Overture use their declared
units. Undo/Redo/save operate on adopted coordinates and never reapply the factor.

## Supported profiles

| Input | Supported | Refused or unresolved |
| --- | --- | --- |
| GeoJSON `geojson-v1` | Local metres or WGS84; LineString/MultiLineString ground roads; Polygon/MultiPolygon buildings or forest/orchard with holes; bounded nested GeometryCollection | Point semantics, legacy CRS, Z, structural heights/graph IDs, empty/unsupported leaves |
| OSM XML/PBF `osm-extract-v1` | Bounded snapshot or selected-area streaming; supported highways/buildings/vegetation; source-node loops; explicit bridge/tunnel heights with ground anchors | Unsupported tags, missing metric heights without a supplement, heights inferred from `layer`, invalid original topology |
| Local Overture | Building parts/courtyards, ground transportation with exact spans/connectors, forest land cover; areas ≤0.2° per side (warning above 0.02°) | Structural transportation without metric height/datum/clearance, unbounded selections |
| PNG heightmap | 16-bit full-cell PNG with explicit extent, offset/step and shared-edge validation | Undeclared units, bad cell edges, arbitrary CRS/resampling |
| Copernicus COG `copernicus-dem-v1` | One bounded array of local COGs (single file or atomic mosaic) | Remote acquisition, arbitrary raster/nodata/warp profiles |
| Facility CSV `facility-csv-v1` | UTF-8/CP949/EUC-KR, header mapping, WGS84 name/position/category/source | Invalid coordinates become review rows; nothing is geocoded or guessed |

Every whole candidate is validated before adoption. Repeated keys, missing
coordinates, invalid rings, conflicting identities and unsupported members reject
the candidate instead of flattening it. Source SHA, bytes, license, accuracy,
extent, counts, estimates and bounded warning samples are retained.

## DEM mosaics and building bases

Copernicus mosaics allow up to 1024 cells of any aspect ratio, 16 source tiles of
at most 256 MiB each, 512 MiB of decoded full-resolution COG blocks, 4096² total
samples, 513 samples per cell side and 2 GiB of derived terrain. Above 256 cells,
four tiles, 64 MiB per tile, 64 MiB decoded, 1025² samples or 64 MiB derived terrain
the review records limit warnings and continues. There is no time limit; after 120 s
a running-time warning appears and Cancel remains. A review older than 10 minutes is
checked again with a warning. Review reads only the tile headers to find the blocks
the sample support touches and refuses a hard excess before hashing or copying; the
review lists each tile's blocks and decoded/compressed bytes, and the captured copies must touch the same blocks. Whole
tiles are still hashed and copied for their identity. The adopted source notice names each tile
file with its bytes and SHA-256; local source and capture paths stay out of the map
(the capture folder keeps its own review sidecars). DEM is optional: a region beyond
the hard bounds is refused with that explanation and keeps its flat terrain. **Use imported OSM coordinates and full
map extent** copies the imported frame, selects all cells and uses 4 m map spacing
when the grid allows. On an OSM-scaled map (the review sends `osm_denominator`) the
mosaic samples become a bare-earth estimate before quantization: a morphological
opening of 150 source m removes buildings and trees, then a 60 source m Gaussian
smooths the relief, over the whole mosaic so shared cell edges stay identical.
Relief stays true to scale ÷D. The sampling record adds `ground`
(`osm-dem-bare-earth-v1`); other maps keep the raw DSM.

**Place zero-base OSM buildings on this DSM (estimated)** is optional. It changes
only imported OSM buildings whose base is still zero and whose footprint (and every
part) the mosaic covers fully; the lowest DSM sample at vertices and edge midpoints
sets the base of each solid (a part keeps its own base when it differs).
This is a disclosed surface estimate (roof/tree bias possible), not surveyed ground.
Shapes, heights and other bases are unchanged. The receipt
lists every changed base and uncovered count; terrain and buildings adopt as one Undo.

Imported city water (`import-` water bodies) is fitted after the structures, in
the same candidate. A narrow piece (mean width `2 · area / perimeter` under 600 cm,
without islands and not already cut) whose shore heights span more than 30 cm is
a sloped stream: it is cut into stretches on a square grid whose lines lie off
the DEM sample lines (half a grid, or half a spacing for whole spacings), a
quarter of a spacing to four spacings wide so a stretch falls about 30 cm on the
piece's mean slope; every grid crossing becomes a shared seam vertex first, so
neighbouring stretches meet exactly. Parts of one piece sharing a seam longer than
twice the piece's mean width (a stream running along a grid line, split
lengthwise) keep one level, and parts under one map square metre join a
neighbour, preferring one that is no sliver. Touching pieces and stretches then
share levels, wide pieces first, each most similar first, while the median shore
height of every wide member stays within 100 cm of the joined level (a lake keeps
one level even where its DSM shore rises over trees and embankments, which split
lake pieces whose own shore spanned more than 100 cm before) and every shore
height of a tight member (a stretch, or a piece narrower than 360 cm, two MapKit
banks, which cannot sink its bed far under its banks) within 30 cm. A 400 cm inlet
therefore joins its lake; a 250 cm creek whose shore lies 65 cm above the lake
keeps its own level and steps down at the mouth. A level is the lowest
shore terrain of its members, sampled at every vertex and along every edge at the
DEM spacing, and the surface lies 8 cm below it, so the water never floats above
a sampled bank of its stretch (a median level did on sloped shores). The stretches
of one piece at one level join again; a piece left in several parts keeps its ID
for the first and gains `<id>-s<k>` bodies (the next free `k`) for the others (the
native-job guard accepts only level changes and stretches inside the original
outline with its other fields). A body already cut (a stretch, or a piece with
stretches) is refitted whole, so adopting a DEM again only changes levels; levels
already in place produce no patch. Should the stretches pass MapKit's 1,024
bodies, the drop per stretch doubles (to at most 240 cm, then no cut). The bottom
lies 60 cm below the surface. DEM samples are not carved: MapKit sinks an earth
basin under OSM-city water when it generates ground (banks fall 68 cm per 180 cm
for the 60 cm import depth, about 21° as on flat maps, down to the bottom up to
12 m from the shore; a body narrower than two banks falls to its bed at 2/5 of its
shore width, no steeper than 68 cm per 60 cm; where water of different levels
meets, the ground rises to the upper surface in a lip instead of a terrain bank,
so the upper stretch neither floats nor is dammed; terrain kept under roads). A
dipped sample at a culvert or road edge only makes that water shallower. Pieces
partly outside the DEM keep their flat heights. The notice adds `water_fit`
(`osm-water-dem-fit-v1`, counts, `level: lowest-shore-sample`, `cut_pieces`,
`stretches` (parts of cut pieces), `added_bodies`, `stretch_range_cm`,
`stretch_drop_cm` used; its carve counts stay zero), and the summary lists the cut
streams.

Estimated city bridges and tunnels (`osm_estimated_structures`) assume flat ground,
so adopting a DEM fits them to the DSM in the same candidate, before grounding:
each ground anchor gets one level terrain pad under its junction fan (overlapping
pads share the median), level leads and adjoining ground vertices take the pad
height (a level vertex is inserted when an arm is too short), and each profile keeps
its height above a base interpolated between its own anchors. Terrain is cut under
decks (ground roads beneath keep 5 m at 1:D, or their flat clearance when smaller)
and filled over tunnels where ground roads cross. Pad levels iterate within those
bounds. Any conflict, an anchor outside the DEM, an edit beyond 64 m at 1:D, a
designed or explicit-height joint, mixed terrain spacing or a DEM reviewed at
another scale refuses the whole fit and the map keeps its flat terrain. The summary
discloses counts and the largest change; the notice adds `structure_fit`
(`osm-estimated-structure-dem-fit-v1`, counts and the edit hash). Explicit-height
structures never change. A city with estimated structures cannot be imported onto a
map that already has terrain heightmaps: adopt the city on flat terrain first, then
the DEM.

## Choosing a geographic area

Open **Import vector source → OSM crop**, choose the PBF (the picker's `*.pbf`
filter also accepts `.osm.pbf`), enter an administrative name or recorded alias and
press **Find area by name**. If an English search fails, try the local name; no
translation is invented. Results show relation IDs, exact extents and simplified
outlines (the best 32 matches; outlines thinned to 20,000 display points; names over
256 characters shortened). More matches, thinning and more than 200,000 boundary
references warn; 10 million references are refused. Missing outer geometry is
reported, never guessed. The same lookup lists up to 16 named features whose name
is exactly the query (anchors with their position), and for each area centre and
anchor the complete administrative boundaries containing it and its country (ISO
code, `driving_side` tag and basis); above 8 million context references it warns
and lists none. The real-city wizard uses them ([IMPORT_CITY](IMPORT_CITY.md#automatic-extent-and-traffic)).

Selecting a result fills outward-rounded W/S/E/N fields and centres the WGS84
origin. **Add selected area** combines up to 64 results (warning above eight; for
example neighbouring districts): the fields become their combined extent and the PBF
streaming import clips to the exact union of their boundaries, read from the same captured PBF
(`--osm-areas`, crop `region` `administrative-union-v1` with the area IDs and names in
the receipt). Missing or open boundaries, or areas outside the rectangle, reject the
import. Click the diagram to move the origin or drag a rectangle; dragging returns
to a plain rectangle crop, which includes territory outside the named boundary. The
origin maps to the map centre after 1:D adoption and is placed again when the scale
changes (a typed origin is kept). Manual coordinates remain available. On macOS the in-app file
chooser is used because the system Open panel can leave confirmation disabled.

**Review and exclude unsupported source objects** is an explicit PBF option.
By default unsupported selected objects reject the import. With review enabled,
exact source IDs and reasons are retained and the adoption checkbox must be
checked. Excluded area members never reappear as standalone polygons.

## Facilities

Choose **Facility CSV**, set license, source reference and encoding, map the
name/latitude/longitude headers and supply the category. **Use imported OSM
coordinates** reuses the existing origin. Rows share the import origin and the
map's stored scale (1:1 without OSM, otherwise its 1:D); the OSM crop can filter rows besides map bounds. Invalid
rows must be explicitly excluded. More than 20,000 rows, files above 32 MiB, fields
above 16 KiB or more than 128 columns warn; 256 MiB files, 1 MiB fields and 1024
columns are refused.

Facilities appear in the Facilities list and the shared pin/label renderer.
Current-v1 `pois` keep names, classes, local coordinates and source/row
provenance through Undo/Redo, save, export and reopen. Pins have no height or
collision.

## Topology, structures and heights

GeoJSON multipart lines keep independent endpoints and are never welded by position.
Collections preserve order and inherited properties (64 levels; warning above 40,000
nodes / 20,000 leaves, refused at 4 million / 2 million). OSM connections use
original node identity; crop cuts get local IDs and cannot connect by position.
Original topology and heights are validated before cropping, including incident ways
outside the area.

Structures need explicit source heights, vertical datum, clearance and two ground
anchors per connected component; the city profile levels those crossing no other road
and estimates heights for the rest ([IMPORT_CITY](IMPORT_CITY.md)). Snapshot-bound local height supplements may fill
missing values but never override source heights (≤16 MiB and 1 million nodes;
warning above 256 KiB / 4096 nodes). Native generation checks every affected
corridor at review and adoption (warning above 16 cells, at most 16,384). WGS84
height conversion needs explicit reference metadata; an EGM96→EGM2008 delta grid
(≤16 MiB, 1025 rows/columns and 10° per side; warning above 64 KiB, 33 and 1°) must
cover every vertex. Preparing grids from arbitrary geoid formats is unsupported.

## Worker, review and limits

One ImportJob owns one helper, request ID and scratch directory. Progress uses real
stage/count events; IPC is bounded (events ≤4 KiB, total ≤64 MiB, stderr ≤4 KiB).
There is no time limit: after 120 s (PBF streaming: 15 minutes) a running-time
warning appears and Cancel remains. Cancellation terminates the child and removes
only its scratch. Full failure text is in **Activity → Operation details…**.

Limits on the user's own data warn instead of refusing: each exceeded budget adds one
`Limit warning: <message> (<actual> > <limit>)`, listed first in the review, and the
import continues. A limit the game enforces adds "; the game refuses maps beyond
this" (for example over 200,000 objects or 1 million vertices). MapKit's native
checks at review and adoption run under its Authoring profile: its document and work
budgets warn the same way (merged by code with the Editor's) and refuse only above
its raised guards (1.6 million objects, 8 million vertices, 8× the work budgets).
Only those guards and memory/parser guards refuse. Malformed or unsupported data,
identity and topology errors still reject; only the city profile's exclusion review
lists an invalid source area (for example a self-intersecting land-cover ring) with
its reason and leaves it out whole, never repaired ([IMPORT_CITY](IMPORT_CITY.md#review-and-adoption)).

| Bound | Exact profile: warning above | Refused above |
| --- | --- | --- |
| Snapshot input | 32 MiB (PBF streaming 2 GiB) | 256 MiB (PBF streaming 64 GiB) |
| Result | 12 MiB, 20,000 features, 200,000 positions, 60,000 records | 1 GiB |
| Native check | 16 cells | 16,384 cells |
| PBF scan | 100 million entities, 80 million references, 2 GiB disk index | Disk quota: 3× source (≥2 GiB) within free disk |

Exact mode performs no generalization. Disk index bytes are logical reservations,
not RSS limits; low free disk warns, and a full disk fails the import. The scan
reads dense node IDs/locations and way references straight from the captured blocks
(each way checked against libosmium's ID and node count); only tagged nodes and
way/relation tags become Python objects, and the road incidence index keeps only
nodes that two or more highways share. A city import of a source above 512 MiB
first copies the crop's neighbourhood from the captured bytes into a regional PBF
(seven `extract_*` passes): every node within the crop + 5 km, every way touching
one of them with all its nodes, every relation with such a member and all member
ways of those multipolygons; the index and every later pass read that copy, and the
receipt keeps the original's bytes and hash (`regional` counts in the stream
metadata). Area boundaries are still read from the whole capture. The review candidate is immutable; source
recheck and command preparation run in owned workers, and late or stale results are
rejected. Adopt adds the whole layer in one Undo command (a command over 16 MiB is
applied without Undo); Discard releases the candidate. Layer visibility/lock are
view state. Saving stays explicit. Compressed history and native transfer limits are
in [DOCUMENTS](DOCUMENTS.md); PNG/asset adoption follows [AUTHORING](AUTHORING.md).

The importer needs Python 3.12+ with `requirements-import.txt` (NumPy 2.5.3).

## Known limits

- City output above 32 MiB warns that the game refuses the map
  ([IMPORT_CITY](IMPORT_CITY.md)); four Suwon districts adopt at 24.1 MB, which is
  not a claim for every city.
- The structure fit needs the whole map under one DEM (every anchor inside it), so
  a city larger than the DEM cell bound stays flat; the DSM is a surface estimate,
  so pads and cuts can leave visible terraces near structures.
- Overture/GIS completeness, broader OSM/Overture semantics, general POI/structural
  GeoJSON and geoid preparation are feature work.

For a change, run the affected `tests/test_osm*.py`, `test_collections.py` or
adapter test and the related Godot validator through the isolated checker. OS file
dialogs, real-region accuracy, large-area performance and Client driving are user
checks.
