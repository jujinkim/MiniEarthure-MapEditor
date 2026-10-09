# Environment design

Open **Authoring settings → Environment**. Choose a map concept, independent
architecture/climate/settlement dimensions, latitude/longitude, time zone and
sunrise/sunset defaults. Applying updates the current v1 document and supports Undo /
Redo, including restoring the absence of a optional profile on current source documents.

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


## Shared time selector

Generation, environment start and 3D preview share the six localized presets
09:00/12:00/17:00/18:00/21:00/06:00. Existing nonpreset times remain exact until
explicit selection; opening a picker never rounds or emits a change. Numeric
hour/minute APIs and sunrise/sunset authoring remain unchanged. Session weather
is not inserted into generated package settings.

Scoped track-settings/environment checks passed preset selection, arbitrary-time
preservation, adoption, Undo/Redo and invalid-edit rejection. Detailed Editor
interaction and devices remain user verification.
