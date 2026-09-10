# Physics test map v2

[physics-test.memap](../examples/physics-test.memap) is a synthetic MIT test map:
one actual **128 × 128 m** cell, 33×33 PNG16 height samples, 4 m spacing and 2,048
terrain triangles. Hills reach 2 m and 1 m. Custom authoring metres are game metres;
there is no display multiplier. No objects or visual detail were removed.

Start at X=64 m, Y=32 m, surface `terrain`; the hill approach is X=88 m, Y=64 m.
The surface is grass. Vehicle forces and driving acceptance belong to the consumer.

```sh
rtk proxy python3 scripts/physics_test_map.py /new/physics-test
rtk proxy /path/to/mapkit pack /new/physics-test /new/physics-test.memap
rtk proxy python3 scripts/check_driving_school.py --mapkit /path/to/mapkit --project /new/physics-test --output /new/physics-check
```

The package is 1,519 bytes. `tests/physics_test.lock.json` locks its source and cell.
[Old source](../examples/physics-test-v1/) and [package](../examples/physics-test-v1.memap)
remain intact; [previous evidence](archive/2026-09-11-loading-units/PHYSICS_TEST_MAP.md)
describes the former authored 1024 m / displayed 128 m convention.
