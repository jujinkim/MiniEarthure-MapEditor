# map-editor

Independent public MIT code with no private repository dependency. Preserve source
and asset licenses. Use synthetic fixtures only; never publish user datasets or
secrets. Use `rtk` for shell commands when available.

Formats: `.memap` and all own format/protocol numbers are 1. Version changes require
explicit user approval. Runtime revisions, epochs and request IDs are not format
versions. No previous-format loaders, automatic conversion or legacy compatibility
branches. Preserve user datasets, original files and Git history.

Validation: check only changed areas and their direct/indirect dependencies; run the
affected feature/unit tests and needed syntax/build/load checks, keeping relevant
safety regressions. Docs-only work needs diff/reference/pin checks. Application
checks stop at standalone startup and the initial screen. Detailed interaction, test
driving, Godot Editor execution, OS/device and platform acceptance are the user's.
Full checks, recursive clean-clone, export matrices and long performance runs need an
explicit request. Record known failures and user checks separately.

Documentation: start from `docs/README.md`. Owning documents keep only current
contracts, usage, limits and essential validation; edit existing sections instead of
appending dated updates. Approved decision replacements are recorded only in the
root `docs/history/DECISIONS.md`; measurements and past comparisons live in Git
history. Active task notes belong in the root ignored `docs/tasks/`; integrate
results and delete finished notes without archiving them.

Commits: commit each verified task locally on main in dependency order, including
consumer pins and the root lock. Push after the approved scope and checks finish.
Never force-push or rewrite history.
