# Practice refresh — 2026-10-03

Starting Editor `b968f100`, MapKit `0232724e`; final MapKit `e563b8d1`.
macOS arm64, Python 3.12 root virtualenv, Godot 4.7.2 Mono, isolated user data
and owning-source native bridge. Exact artifact/script hashes and final pin are
in [refresh-result.json](refresh-result.json).

The current pre-change CLI generation fingerprint was checked against its source.
It independently reproduced [stored invalid action](stored-before.log) and
[fresh-script corner clearance](script-before.log). The original four takeoffs
used sample 32 where current paths contain only 21 samples (0–20).
Both original bundles and sources were preserved locally before replacements;
the original tracked example also remains in the starting commit's history.

Final scoped checks passed:

- [Three Python tests](practice-source-tests.log): original course order, static
  beam/walls, 8m/6m corners, actual-path distance references, every file identical
  across two new output directories, existing-directory rejection without writes,
  recompile/package/source identity, entry hash and `human_completion: unverified`.
- [Fresh generation](regenerate.log) and [stored source recompilation](stored-after.log)
  succeeded. The recompiled package equals the installed example byte-for-byte.
  Removing only sample fields makes old and new authored sources identical.
- [Editor source validator](editor/editor-practice_source_validator.log): native
  package open, source unpack, original project reopen, unmodified recompile,
  save and reopen preserve the exact editable source. Strict diagnostics passed.

Package SHA256:
`4745728b36f1573c7f989732a6fe1c1b635779e40e41d52b34ed2a8727e5eebc`.
All four takeoffs now resolve to sample 17 and all checkpoints to sample 2;
these are observed outputs, not constants added to the script. The first entry
station is 286cm, the closest compiled sample to 3m on the 20m approach.
Source, project, package, courses and entry were regenerated together.

Command metadata retains times and exact isolated paths. Tracked logs trim only
trailing whitespace/blank EOF lines; original local logs remain preserved.
No format/API addition, auto-converter, safety-gate bypass or geometry redesign.
Detailed Editor interaction, ten-course human completion and platform/device
acceptance were not performed. Consumer physics and UI checks belong to their
own repositories and are not claimed by these public authoring results.
