# UI languages

The standalone editor starts in English independently of the OS language.
**View → Language** offers English, 한국어 and 日本語. A selection is saved in this
app's `user://ui_language.cfg` and applies on the next launch. The current screen,
new dialogs and command search retain the startup language. A notice reports the
save result and asks for a restart; the editor never exits or restarts itself.
An unsuccessful atomic write preserves the previous file and selection. Corrupt,
unknown or unavailable language preferences fall back to English.

This editor owns `scripts/localization.gd`, its display adapters and
`translations/{en,ko,ja}.json`. Their schema is a data-only object containing
`schema`, `locale`, `name` and `messages`. There is no private Client dependency,
custom-pack loader or live-switch compatibility API. Worker processes retain raw
English diagnostics and protocol values. Runtime/MapKit APIs are unchanged.

## Display boundaries

English source keys translate before insertion of numbers and names. Command
registration retains its original ID, label, description, shortcut and context;
menus, palettes and search display translated copies. Search accepts translated
names/descriptions, original names/descriptions and stable IDs. Favorites and
shortcut settings retain their existing identifiers.

Built-in option IDs resolve to translated display keys; OptionButton metadata
holds the original value. Authored names, paths, addresses, document IDs, sign
text, raw source metadata and license originals remain verbatim, including names
that happen to equal a translation key. File filters translate descriptions only.
Document serialization, history and hashes do not depend on UI language.

`locale_text.gd` and `diagnostic_text.gd` translate known local and native diagnostics
at presentation boundaries. The latter recognizes a bounded list of formatted
model/worker messages and inserts captured arguments into translated templates.
It does not rewrite worker responses or translate their path/ID arguments.
Known native error codes have translated summaries; unrecognized diagnostics
retain the original text with localized guidance. Import-review summaries are
localized, while exact metadata browsing stays read-only and verbatim.

## Fonts and export

Each UI theme owns fresh Latin and Noto Sans CJK 2.004 KR/JP Regular font caches.
Japanese uses JP and the other startup languages use KR. System fallback is
disabled; canvas labels use the theme font. Source URLs, hashes, copyright and
license are in [NOTICE](../fonts/NOTICE.txt) and [OFL](../fonts/OFL.txt).
Both export presets include catalogs, fonts and notices. Map sign authoring
continues to use the user's explicitly chosen licensed font.

## Verification

Run `python3 scripts/check_translations.py` and the isolated
`tests/localization_validator.gd` with Godot 4.7.2. The static audit checks catalog
key parity, duplicate/empty entries, length/size limits, interpolation signatures,
UI helpers, scenes, command declarations, built-in labels, diagnostic prose and
font hashes. Console messages, licenses and persisted processing contracts are
explicitly excluded. The unit test also audits dynamically registered commands,
restart persistence/failures, search in three languages, document/shortcut
identity, authored text preservation and every shipped CJK glyph without system
fallback. Dynamic diagnostic tests preserve path and ID arguments.

Keep implementation, scoped automated results, known failures and remaining
user acceptance separate. Basic app startup is the limit of actual app
verification; detailed editing, test driving, IME, devices and export matrices
remain user checks.
