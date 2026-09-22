# Public current-v1 course authoring

Courses are public MapKit records in the same document transaction/history as other
map records. A map may contain zero or multiple courses. The Courses authoring page
supports 3D height, sphere/upward hemisphere and radius, insertion/move/delete/order,
shared circuit start/finish and explicit ground/air heading, draft Undo/Redo, map Undo/Redo,
2D circles and a shared MapKit 3D preview. Ground placement samples current terrain;
manual height supports bridges, roofs and air. No private game or physics dependency exists.

An unverified course may be saved and exported. New drafts use a placeholder driving
hash until the game explicitly binds the current v1 definition to its selected map ID
and current package's driving content. That is a draft edit, not a historical converter.
Completion proof is created only by a player drive in the game. Its course export has
one `.mecourse` and relative `course-validation/<sha>.mevalidation`. Import checks the
public typed definition, same map ID, bounded opaque bytes and integrity hash, then
adopts through document history. Editor never creates or certifies game proof. Saved
projects/Save As/package exports retain referenced payloads, including undo history.

Geometry/start/map changes leave stale references available for the game to report
revalidation. Course/proof additions do not change the MapKit driving-content hash;
package integrity still includes them. Hosting lap count (1–10 circuit, one sprint)
is separate from authoring. Previous course layouts are not converted automatically.

`course_authoring_validator` and `document_history_validator` pass with isolated data:
height/shape/order, metadata Undo/Redo, real hemisphere radius, native project reload,
opaque proof import and Save As retention. This is authoring/unit verification, not
player completion or detailed Editor/device acceptance.
