# Special driving examples — 2026-09-26

These are new synthetic source projects and `.memap` format 2 packages. Original
miniature-streets and road-safety projects/packages remain untouched. Each of the
seven regional variants adds a small optional pad on one edge of a suitable road;
at least 1.6 m of normal road remains available. Red Wadi and Kanupi use launch
height pads; the others use 70% target-speed pads. Starts and route metadata are
preserved and consumers revalidate them against these packages.

`demo.memap` / `demo/document.json` contain all five features: target-speed pad,
3 m jump pad, directional air ring, variable-curvature loop and hollow cylinder.
The three test lanes connect to an ordinary outer bypass. The loop has a 70%
entry pad. Direction markers point along local +Z; the cylinder requires steering
into circumferential motion to reach its walls/ceiling. Axis speed alone does not
provide attachment. This is a demonstration source, not a completion certificate.

Editor controls include pitch/yaw/roll, strength, jump height, radius, loop width
and cylinder length. Arm surface placement and click a road or inner track face
in the preview to align the selected panel's contact point/normal. Its projected
forward direction is visible. Moving-prop attachment is intentionally outside
this authoring operation. Edits participate in undo/redo and save/reopen.

Reproduce into a **new** directory (never overwrite originals):

```sh
python scripts/special_driving_maps.py /tmp/new-special-driving --kit addons/mapkit
mapkit pack /tmp/new-special-driving/demo /tmp/new-special-driving/demo.memap
```

Pack each regional subdirectory in the same way. Geometry/cost validation can
reject a size or placement that exceeds existing admission limits. The shapes
and effects use the current MapKit contract; no older-format conversion occurs.

Focused verification: native package generation for all eight maps; deterministic
source reproduction/payload preservation/bypass test; authoring validator covering
controls, surface alignment, undo/redo, save/reopen and shared previews. Offline
fixed renders inspect final shapes. Detailed Editor interaction, game completion,
multiplayer and platform acceptance remain user checks. Prior completion evidence
is not attached to these variants.
