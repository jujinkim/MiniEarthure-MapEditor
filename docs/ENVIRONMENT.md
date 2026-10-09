# Environment design

Open **Authoring settings → Environment**. Choose a map concept, independent
architecture/climate/settlement dimensions, latitude/longitude, time zone and
sunrise/sunset defaults. Applying updates the current v1 document and supports Undo /
Redo, including restoring the absence of a profile on old source documents.

Regional overrides are ordered centimetre polygons. The first matching region
wins. The panel includes editable examples for region and light-binding arrays.
Light bindings use asset IDs and GLB material indices, with explicit bulb positions,
ranges and colors. Empty bindings add no buildings or lamps. Invalid metadata
cannot mutate the document; reopening refreshes stale edit state.

The public 3D preview uses the same MapKit materials and sky. Preview hour/weather
controls do not change source data. The new `examples/driving-school-atmosphere`
and `examples/world-themes-atmosphere/<concept>` projects provide muted original
surface tiles and retain the original geometry and attribution. Every example has
a separate .memap and a package lock. Old projects and packages remain available.

`tests/environment_validator.gd` verifies adoption, undo/redo and invalid edits;
`tests/test_atmosphere_assets.py` checks original geometry/payload preservation and
all seven new-destination-only upgrades. See MapKit's ENVIRONMENT contract.


## Hourly selectors — 2026-10-03

Generation, environment start time and the 3D preview now use the same 24-entry
00:00–23:00 picker. Fractional existing times round to the nearest displayed hour,
wrapping midnight; source minute values and environment hour APIs are unchanged.
Sunrise/sunset authoring remains minute-valued. The starting-time label is updated
in English/Korean/Japanese. No session weather field is added to generated packages.

`track_settings_validator` covers 24 values and rounding. `environment_validator`
passes adoption, undo/redo and invalid-edit rejection in `environment-final/`
under `validation/driving-map-2026-10-02/`. Its historical assumption that the
initial document lacked an environment was replaced by exact restoration of the
current document. An intermediate run had stale texture-import paths from shared
source metadata; a fresh isolated import resolved it. These failures remain in
`environment/` and `environment-fixed/`. Detailed Editor interaction is a user check.
