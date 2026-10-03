# Continuous-clearance dependency refresh — 2026-10-03

MapKit pin: `47a07f13d7e05ede6fe8d6376b0665df12f4db2f`; starting Editor `6e85d37e`.
macOS arm64, Godot 4.7.2 Mono and isolated user data. Native bridge/CLI bytes
were built once from the pinned source and installed in the Editor checkout.
No Editor product logic or format changes.

The existing source and package were preserved before compiling `source.json`
into a new directory. [Recompile](practice-recompile.log), [unpack](practice-unpack.log)
and [CLI validation](practice-validate.log) pass. An exact recursive document
comparison finds only seven generator/derived identity fields changed;
[the comparison](practice-comparison.json) records each. Original source,
geometry, paths, actions, 8m/6m corners, courses and dimensions are unchanged.
Package/entry SHA256: `36c07f812f9436d53798e1e542f9edf2d8e6e39f4a962b7390b5148784cc652b`.

The installed-addon [source validator](editor/editor-practice_source_validator.log)
passes native open/unpack, source/project reopen, unmodified compilation,
save/reopen and exact source identity with strict diagnostics.
The installed-addon [standalone initial screen](editor-initial/editor-initial_screen_validator.log)
also passes strict diagnostics; its captured initial workbench was visually inspected.
A single isolated import was reused for the unchanged startup check.
The capture and preserved old bundles remain local to the integration workspace.

No full test suite, long benchmark, detailed editing, real driving, platform matrix
or recursive clone was run. Human completion remains unverified. Prior evidence
and unrelated known failures remain intact. The 500ms editing target is not
remeasured or claimed resolved by this dependency refresh.
