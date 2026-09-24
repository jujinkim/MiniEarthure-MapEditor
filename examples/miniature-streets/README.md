# Miniature streets

Seven new MIT sources replace the default distribution with another roughly 50%
reduction in width, depth and terrain height. Historical compact-driving,
regional-districts and regional-miniatures sources/packages remain intact.
Shared authoring geometry and rendering belong to MapKit; Editor owns these
sources, street infill, route records, bridge approaches and graded start areas.

| Map | Size (m) | New street infill | Optional challenges |
| --- | --- | --- | --- |
| Haeon | 256 × 256 | 53 | 8 |
| Belmont | 320 × 224 | 125 | 4 |
| Nord | 352 × 160 | 156 | 4 |
| Safra | 224 × 224 | 128 | 9 |
| Red Wadi | 352 × 192 | 126 | 3 |
| Kanupi | 320 × 224 | 41 | 6 |
| Bansai | 288 × 192 | 99 | 5 |

Every map retains four district records and regional asset palettes. Ordinary
roads are at least 2.8 m; start roads widen to 6 m with independently graded
pads. Two new bridges per map have flat connecting aprons and approaches below
20 degrees. Each has an authored crossing underpass with 2.4 m clearance and
straight portal mouths; graph connectivity and 1 cm terrain joins are validated.
Active obstacles/ramps are restricted to technical streets, leaving at least
1.4 m safe bypass. Ramp entry vertices meet sampled terrain, including crossfall.

Intro/technical/sprint authored length targets are 175–300 / 250–450 / 300–500 m.
Checkpoints use a 3 m radius appropriate to these maps; format numbers and units
are unchanged. Vehicle-specific course sealing/grid admission is a consumer task.
The game distribution marks every new course unverified until user completion.

Generate only to a new directory, from the superproject Python environment:

```sh
rtk proxy .venv/bin/python map-editor/scripts/miniature_streets.py /tmp/new-miniature-streets --kit map-kit
rtk proxy map-kit/target/debug/mapkit pack /tmp/new-miniature-streets/haeon /tmp/new-miniature-streets/haeon.memap
rtk proxy env MAPKIT_ROOT="$PWD/map-kit" .venv/bin/python -m unittest discover -s map-editor/tests -p test_miniature_streets.py
```

The focused test reproduces all seven source/package bytes, checks hashes, terrain
seams, connected routes, widths, bridge grades/clearance and challenge placement,
and confirms historical source bytes remain untouched. Native validate-cells
passes all seven maps. Fixed overview/street rendering uses the public renderer;
instanced leaf tint is included. Detailed art/driving/editor acceptance is left
to users. Embedded font notices stay with the original source assets/packages.
No memory/cell admission caps are raised.

New structure editing uses MapKit’s current zero-step templates. The native
gimmick authoring validator passes (including new ramp save and undo). Existing
source/library artifacts are preserved.
