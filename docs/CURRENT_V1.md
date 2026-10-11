# Current v1 authoring and imports

New documents, saves and exports use the current MapKit v1 definition; there is no
recipe selector or feature-driven promotion. Do not increment format/protocol
versions without explicit user approval. Preserved historical packages are neither
upgraded nor loaded automatically.

Each import adapter has one current shape: GeoJSON `geojson-v1`, OSM crop/loop/
structural provenance, Overture transportation with exact spans, and Copernicus
`copernicus-dem-v1` for a single COG or mosaic. Profiles and limits are in
[IMPORTS](IMPORTS.md); the OSM city profile ([IMPORT_CITY](IMPORT_CITY.md)) emits
ordinary v1 geometry. Compressed history is private Editor state
([DOCUMENTS](DOCUMENTS.md)).

Projects, regional packages, supported external inputs and recovery snapshots remain
supported. Original files and generated user artifacts are never removed.
