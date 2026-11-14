# Real-city location and source acquisition

**Create → New real-city map…** (`real_city_wizard.gd`) picks a location and the
sources for the [real-city recipe](IMPORT_CITY.md#real-city-maps-wizard-and-recipe).
Generation stays offline: the importers read only local files. Fetching happens in a
separate, explicit step that writes immutable local snapshots. Only
`scripts/acquire_city_sources.py` and `scripts/acquire_regional_sources.py` use the
network, and nothing contacts a service during play.

## Wizard flow

1. **Location.** You can set the centre in three ways:
   - Search a place. The search uses Nominatim on the web, or with **Use local files**
     the offline area/place lookup in the chosen PBF.
   - Click the map. Its location picker (`slippy_map.gd`) shows OpenStreetMap
     standard tiles.
   - Type latitude and longitude.

   Search results keep full coordinate precision. A map click is as precise as the
   view.
2. **Extent.** Choose a circle or square and a radius or half side of 0.1–2.5 km
   (default: a 2 km circle). The guidance line shows:
   - source area, cells and estimated generation time and package size
     (`real_city_auto.gd` `estimate`, scaled from measured 2 km-circle runs);
   - an orange warning above the 2 km circle, where generation, game loading and
     phone memory grow with the area.
3. **Data.** Choose one of two sources:
   - **Download automatically** needs the licence confirmation. It acquires
     OpenStreetMap and, with **Terrain from Copernicus DEM**, the GLO-30 tiles.
   - **Use local files** takes the user's PBF and optional Copernicus tile folder.
4. **Coverage check.** Both sources pass the same `preflight` before anything is
   built. A failure lists what is missing and builds nothing.
5. **Build.** The recipe runs: import → adopt → regional style (unless **Plain city
   buildings**) → DEM → save → export. Afterwards the
   map stays open for editing, and **Show exported map** reveals the package.

**Save recipe…** writes the same recipe. In download mode it acquires the snapshots
first, so the recipe names local files and reruns headless without the network.
Project and package paths default to `Documents/MiniEarthure maps/<place>-<time>/`
until edited. Traffic and **Architecture** follow the explicit selectors. Otherwise
they follow the country, which comes from the search result or from the snapshot's
containing boundaries ([automatic choices](IMPORT_CITY.md#automatic-extent-traffic-and-architecture)).

## Acquisition (`acquire_city_sources.py`)

The tool runs through `city_source_job.gd`. The job copies the tool and its offline
helper modules into `user://city-source-jobs/<id>`, reads one JSON progress object per
line, kills the child on Cancel and removes only its copies. All snapshots live under
`user://city-sources/` (**Open source cache folder**).

| Command | Behaviour |
| --- | --- |
| `search` | Nominatim `jsonv2` with address details. Explicit searches only (no autocomplete), at most one request per second, results cached for 30 days |
| `osm` | One Overpass extract of the extent plus a 1 km margin. Selects every node and way, the multipolygon, protected-area and site relations, and all of their members and way nodes, then `out meta`. Written as `osm/<query-hash>-<UTC>/extract.osm.pbf`, with the header box set to the fetched box and a `manifest.json` (query, `osm_base`, counts, bytes, SHA-256, licence, country). A matching snapshot is reused; `--fresh` fetches again |
| `dem` | Copernicus GLO-30 1°×1° COGs from the public AWS bucket, for the same tile envelope as the DEM review. Each tile is verified, stored in `copernicus-glo30/` with a `<tile>.json` record, and never overwritten. A tile Copernicus does not publish (open sea) gets `<tile>.absent.json`; such an extent builds flat |
| `preflight` | No network. The PBF header box (else the scanned node extent) must contain the extent bounds, and the folder must hold every needed tile name |

Request and failure rules:

- Requests carry only the fixed client name `MiniEarthure-MapEditor/1`.
- Overpass declares a 600 s timeout and a 1 GiB maxsize. A 429 or 502–504 answer is
  retried twice, after 20 s and then 60 s.
- A runtime `<remark>`, a truncated document or another HTTP failure publishes
  nothing.
- Leftover `.osm-acquire-*` and `.dem-acquire-*` folders older than six hours are
  removed. Other files are never touched.
- The country comes from an `is_in` lookup of administrative levels 2–4 (tags only).
  The snapshot holds no country boundary, so the wizard writes an explicit `traffic`
  and architecture.

The downloaded PBF and user PBFs go through the same city import, review, limits and
fingerprint. The snapshot's SHA-256 is the OSM input identity, so street-furniture
seeds differ from a different extract of the same area, while roads, buildings,
ground, water and zones match.

## Map tiles and licences

The picker follows the OSMF tile policy:

- only visible tiles are requested, at most four at a time, with no prefetch;
- tiles are kept in `user://map-tiles` for 14 days;
- the credit "© OpenStreetMap contributors" is always shown.

Headless runs request no tiles. Heavier use should move to another tile provider.

The licence notice covers:

- OSM data under ODbL 1.0;
- Nominatim search;
- the Copernicus GLO-30 credit.

Adopted sources keep their credits in the map's attributions. Publishing a map
built from OpenStreetMap carries ODbL attribution and share-alike duties (see the
root [real-city guide](../../docs/user/REAL_CITY_GUIDE.md)).

## Limits and checks

- **Size.** The radius cap keeps an Overpass extract near 7 × 7 km. Large extracts
  warn above 512 MiB of XML and are refused above 2 GiB.
- **Search and Overpass availability.** Both are best-effort public services; a
  local PBF remains the fallback.
- **Tests.** `tests/test_acquire_city_sources.py` uses recorded responses (no network
  in tests). `tests/real_city_recipe_validator.gd` covers the wizard (shape, cap,
  pin, outputs, snapshot traffic) and the job (coverage result, uncovered extent,
  cancellation, unknown commands).
- **User checks.** Real search, download and map interaction are checked by the user.
