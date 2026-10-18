# Public current-v1 course authoring

Courses are public MapKit records in the same document transaction/history as other
map records. A map may contain zero or multiple courses. The Courses authoring page
supports 3D height, sphere/upward hemisphere and radius, insertion/move/delete/order,
shared circuit start/finish and explicit ground/air heading, draft Undo/Redo, map
Undo/Redo, 2D circles and a shared MapKit 3D preview. Ground placement samples current
terrain; manual height supports bridges, roofs and air. No private game or physics
dependency exists.

Checkpoint edits reject overlaps before changing draft or history: add, move and
height/radius/shape edits use MapKit's sphere/hemisphere intersection. Track
checkpoint commands derive their bounds from the same public sample contract.
Existing overlapping source arrays give a stable first-wins editing/driving view;
opening never rewrites the source. Zero or one effective gate keeps a connected
map readable, while racing stays disabled.

The main **Course** tool previews MapKit's `suggest_track_course(source_json)` result
without changing the document. Existing track checkpoints change only with explicit
Apply, as one Undo. Proposals share the manual route's start/finish and common-path
rules; seed generation keeps its own established start policy. Disconnects,
undeclared branches, overlapping gates and the 64-gate budget remain diagnostics.
Proposal tokens bind the document session, command epoch and draft revision.

**New course on surfaces** adds gates from actual 3D road/terrain hits. Dragging,
height adjustment and deletion edit the draft until **Save course to map**. Existing
courses can be selected; advanced course controls retain exact shape, radius,
heading, ordering and proof import. **Test Drive** initializes the existing package
and Client launcher from the course start or a point chosen in the 3D view. Finish
certification remains owned by the game.

Maps with roads add **Suggest course on roads**: pick a duration (20–300 s at the
reference speed), then click a road; the camera direction picks the travel direction
and the **Circuit** toggle picks the mode. MapKit `suggest_road_course` returns gates
along the road graph (see map-kit ROAD_DESIGN). An applicable proposal becomes an
unsaved surface-course draft with its start direction; editing and **Save course to
map** work as above, as one Undo. Blocking diagnostics leave the draft unchanged.
Roads outside the course stay drivable. **Gimmicks** (0–16, default 4) asks for
seeded boosts, jumps, ramps and rails along the course (new seed per suggestion);
they preview with the gates. Saving applies the default alignment to unaligned host
roads (as **Apply alignment** would), the attachments and the course in one Undo.
**Shortcuts** (0–4, default 2) asks for ordinary-road corner cuts at course turns;
where buildings block a ground cut on a map without heightmaps, the seed picks an
elevated ramp or steep crest over the roofs instead. They preview as lines (elevated
ones at deck height), split the two course roads at new junctions on save and
remove the bypassed corner gates, in the same Undo step.
**Seed race on roads** uses the same duration, circuit, gimmick and shortcut settings
with a **Seed** (or **New seed**): MapKit `seed_road_course` picks the start road and
direction, then proposes gates and extras with that seed. The result becomes the same
unsaved draft, and the seed's time/weather set the preview environment only; the map
environment is never changed. Save adopts the course and extras in one Undo step.

## Validation and proof

An unverified course may be saved and exported. New drafts use a placeholder driving
hash until the game binds the current definition to its map ID and package driving
content. Completion proof is created only by a player drive in the game. A course
export has one `.mecourse` and relative `course-validation/<sha>.mevalidation`.
Import checks the public typed definition, same map ID, bounded opaque bytes and
integrity hash, then adopts through document history. Editor never creates or
certifies proof. Saved projects, Save As and package exports retain referenced
payloads, including those reachable only through Undo history.

Geometry/start/map changes leave stale references for the game to report as needing
revalidation. Course/proof additions do not change the MapKit driving-content hash;
package integrity still includes them. Hosting lap count (1–10 circuit, one sprint)
is separate from authoring.

## Free-roam finish policy

The required v1 boolean `free_roam` is edited by the **Free-roam map** checkbox in
document properties ("show the finish result, then return to free roam"). New manual
documents and Seed Track default to false; successful GeoJSON/OSM/PBF and PNG/DEM
map or terrain imports set true. Import review, cancel or failure leaves the
document unchanged; adding models/textures and opening native documents keep the
value.

The policy is part of ordinary command history, so Undo/Redo, recovery and Save As
preserve it; imported terrain and the policy change form one atomic command. It is
included in MapKit package contracts and content hashes. Policy edits on generated
tracks are verified with MapKit `reseal_track_document` and update the course hash
together; other source/course forgery is rejected. MapKit provides the arrival plaza
and recovery reference at the end of a Seed sprint.

`course_authoring_validator` and `document_history_validator` cover shape/order,
overlap rejection, Undo/Redo, hemisphere radius, native reload, opaque proof import,
Save As retention and policy/hash preservation. `road_course_validator` covers the
read-only road proposal, its one-Undo save with shortcuts, alignments and gimmicks
and far-start diagnostics;
`driving_osm_validator` proposes on imported OSM roads. Player completion and detailed
Editor/device use are user checks.
