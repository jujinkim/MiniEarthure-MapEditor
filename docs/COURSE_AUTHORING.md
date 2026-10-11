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
Save As retention and policy/hash preservation. Player completion and detailed
Editor/device use are user checks.
