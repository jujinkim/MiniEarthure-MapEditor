# Environment design

Open **Authoring settings → Environment**. Choose a map concept, independent
architecture/climate/settlement dimensions, latitude/longitude, time zone and
sunrise/sunset defaults. Applying explicitly adopts recipe 8 and supports Undo /
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
