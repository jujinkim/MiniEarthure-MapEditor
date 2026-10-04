# Practice regeneration for curve sampling [18] — 2026-10-05

Generated with MapKit a9e2761 and the reproducible `scripts/practice_track.py`.
Same track dimensions, centreline, ports, gates and actions as the preserved
practice-track-rings-2026-10-04 source. Collinear cubic joins retain exact final
samples at each 3m checkpoint apron and the 4m pre-flight marker. Final sample
indices and compiler/derived identities change with the ordinary curve sampler.
No extra road objects or schema changes. Earlier sources/packages remain in place.

Package SHA256: `d6f5cf0606577b2b04185e9a62371a9941cced2ec7c1b0a5354da4373b715e85`.
`entry.json`, courses and native verification bind this exact package. Python
practice tests (4) pass deterministic regeneration, no-overwrite, exact gate/action
samples and CLI verification. The headless source validator passes package-source
open, edit/recompile, save/reopen with 11 checkpoints, 5 structures and 1 grind line.
Detailed editor use and driving remain user verification; no human completion
record is created. All own formats remain v1.
