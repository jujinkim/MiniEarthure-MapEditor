# Practice course

Reproducible ten-course source: ordinary 6m-radius/8m-wide turns followed by
3m-radius/4m-wide sharp turns, then jump/glide/grind/air-turn/boost-climb sections.
See [track authoring](../../docs/TRACK_AUTHORING.md#reproducible-practice-course)
for the current contract and validation scope. Human completion is unverified.

From the MapEditor checkout, choose a new output directory:

```sh
python scripts/practice_track.py <new-directory> --mapkit addons/mapkit/target/debug/mapkit \
  --resource-path res://maps/practice-tight-corners/practice.memap
```

The package, entry hash, compiled document and checkpoint metadata are generated
together. Existing output is never overwritten; all formats remain v1.
