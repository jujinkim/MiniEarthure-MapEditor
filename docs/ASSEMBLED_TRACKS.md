# Seed Track

Seed Track creates a new unsaved document through MapKit's cancellable worker.
Explicit Save/discard/Cancel protects the previous document and original files.
Document and request epochs reject obsolete results. Saved settings, source,
resolved placements and fingerprints survive reopen. The generated source can
be edited with the [track workspace](TRACK_AUTHORING.md).

## Current controls and lifetime

The native catalogue supplies seed, circuit/sprint, 60/90/120-second reference
duration, easy/normal/hard difficulty and driving/gimmick/action categories.
All categories are candidates; no family or obstacle is mandatory. The base
route must meet the generator's ±10% reference-time bound. Actual driving time
depends on the vehicle and inputs. New panels choose a random representable seed;
reopening restores the saved one. Empty categories and stale catalogues show an
error without an old-format fallback.

Progress follows request ID, revision and actual MapKit stage/counts. Search is
indeterminate; saving bytes does not mean collision/display or AI is ready.
Cancellation, failure or superseding work preserves the last valid selection.
Controls use the common scrolling/layout and current catalogue dimensions.
Generated pipes use 2/3/4 m bores; manual 2/3/4/6 m bores come from MapKit.

Generation, source-preservation, cancellation, settings restoration and package
reentry have scoped automated coverage. Detailed generation UX, actual complete
races and device acceptance remain user checks. All own formats stay v1.
