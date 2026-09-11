# Fleet playground (MIT, synthetic)

128×128 authored metres, one cell, Recipe 6. A 70 m gentle ascending ramp reaches
a 3 m launch deck; a 12 m deck gap precedes the descending landing platform.
There is safe ground below and an asphalt bypass at map y=52 m. The rough lane is
at y=76 m, slalom posts at y=98 m, and a thin clearance probe at x=42.3/y=60.31 m.
These are test obstacles, not real geographic data or calibrated driving claims.

Open `document.json` in MapEditor, or from the superproject:

```sh
rtk proxy map-kit/target/debug/mapkit pack map-editor/examples/fleet-playground /tmp/fleet-playground-new.memap
```

In the game choose that `.memap`, select launch surface at x=600/y=4000 cm and
eastbound heading 270°. `driving.json` includes launch, bypass and rough presets.
Gliders deploy automatically after leaving support. Landing depends on approach
speed, attitude and input; the normal sedan may overturn on the 3 m drop and can
use the existing recovery control or the bypass. This is not G04 handling acceptance.

Reproduce into a **new** directory with `scripts/fleet_test_map.py`; it refuses
existing destinations. Source geometry, two tiny original GLBs and generator are
MIT under the MapEditor license. No private game dependency is required to author,
edit, pack or validate the project. Original maps and user datasets are untouched.
