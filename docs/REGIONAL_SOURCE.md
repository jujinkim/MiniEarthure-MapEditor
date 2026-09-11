# Regional map export and reopen

Choose **Export map**, then the `.mkregions` filter (or an explicit `.mkregions`
filename). Set **Regional export · cells per side** to 1–128 before starting.
This groups storage records; it does not change execution cell size, geometry,
assets or quality. The initial value 8 is a convenience, not a recommended
worldwide performance default. `.memap` export remains available.

The worker captures the current immutable editing snapshot, exports independent
regional sources and performs a complete dependency audit. The capacity report
shows the complete transfer size (all assets/index/source copies), expanded
records, shared asset bytes, audit peak, retained index/overview and largest
source validation allowance. Failed, cancelled or stale exports do not publish;
existing destination files are never overwritten.

**Reopen .mkregions** restores the original canonical document and every original
payload, including unused assets, into a new adjacent `<package>.source`
directory. The destination must not exist. After successful audit/recovery the
ordinary unsaved-document flow controls adoption. A cancelled or stale reopen
leaves a successfully restored directory intact and reports its path; it never
deletes the user's previous project or source package. If that path exists,
use ordinary Open or a differently named package copy.

The current Editor still authors one bounded document. Large-world source
streaming does not remove the existing document/object/Editor limits. Source LRU,
region network requests and L02 area/density acceptance are separate work.

`tests/regional_export_validator.gd` covers actual UI export/reopen, complete
audit, cancellation, byte-exact unused PNG recovery, corruption and refusal to
overwrite. Existing preview/export and editor regressions remain applicable.
