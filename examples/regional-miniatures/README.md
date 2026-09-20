# Seven editable regional miniatures

Seven fictional, independently authored regions: Haeon Harbour, Belmont Valley,
Nord Harbour, Safra Hills, Red Wadi, Kanupi River Valley and Bansai Waterfront.
All are current v1 `.memap`, with 16 m cells and 110,592–114,688 m² footprints.

Each folder contains the editable `document.json`, continuous global-coordinate
heightmap tiles, self-contained GLB/sign assets, `package.lock.json` and
`region.json`. The adjacent `.memap` is the deterministic distributable. Regional
writing is baked into textures; recipients need no installed fonts or downloads.
Sign font attribution/OFL texts are included in the `signs` payloads. Geometry
and layout are original MIT work. Existing examples and user maps are preserved.

`region.json` records four land-use districts, three located landmarks (including
real road structures), actual terrain elevation range, starting points and three
road-surface waypoint paths. These paths are authoring metadata, **not a game
course format**. Circuit recommendations are distinct two-lap routes; the third
is a one-way ridge route. A consumer owns conversion to its own game codec.

`scripts/regional_maps.py` owns fixed networks, terrain profiles, river channels,
coastlines, district placement rules and landmark parcels. A fixed seed varies
building details and vegetation. MapKit owns reusable meshes, placement/road
validation, generation, package serialization and rendering.

From this repository, regenerate into a new destination:

```sh
python scripts/regional_maps.py /tmp/new-regional-sources --library addons/mapkit/examples/regional-library
addons/mapkit/target/debug/mapkit pack /tmp/new-regional-sources/haeon /tmp/new-regional-sources/haeon.memap
# Repeat pack for belmont, nord, safra, red-wadi, kanupi, bansai.
python -m unittest discover -s tests -p test_regional_maps.py
```

`MAPKIT_ROOT` can select a different public MapKit checkout for the source test.
Use the workspace's Python environment when working from a superproject.

`tests/render_regional_maps.gd` renders the actual packages through MapKit into
1120×760 overview and ground images. Set `REGIONAL_SOURCE` to this directory and
`REGIONAL_DESTINATION` to a separate image directory, then run the script with
Godot 4.7.2. This offline render is not gameplay or platform acceptance. The
source test checks deterministic bytes, seamless heights, connected roads,
route identity, full-cell generation and package repeatability.
