# World theme authoring — planned scope

The requested themes describe places around the world, not building uses within
one Korean town. The initial seven are polar, metropolis, countryside, Middle
Eastern, desert, jungle and Southeast Asian. They are starting profiles, not an
exhaustive classification of countries or a claim that a whole region has one
architectural style. These profiles and the sign workflow below are **not yet
implemented**.

## Initial profiles

| Profile | Authoring identity | Representative differences |
| --- | --- | --- |
| Polar | Snow/ice, exposed rock, sparse settlement | Snow banks, ice forms, compact utility buildings, wind shelters and sparse vegetation |
| Metropolis | Dense contemporary city | Towers and podiums, transit frontage, broad paved streets, plazas and service alleys |
| Countryside | Low-density agricultural settlement | Fields, farm buildings, fences, ditches, local roads and scattered homes |
| Middle Eastern | Selected regional built environments | Courtyard compounds, shaded streets, arcades, plaster/stone surfaces and market structures |
| Desert | Arid natural terrain | Dunes or rocky ground, dry channels, sparse plants and occasional road/service structures |
| Jungle | Dense humid forest | Layered canopy, undergrowth, roots, wet ground and narrow clearings |
| Southeast Asian | Selected tropical built environments | Deep eaves, shaded shopfronts, verandas, raised floors where appropriate, dense planting and drainage |

Climate/terrain, regional architecture and settlement type are separate authoring
choices. A Southeast Asian metropolis or a Middle Eastern countryside is a valid
combination; choosing Middle Eastern must not automatically mean desert, nor
must Southeast Asian mean jungle. Each concrete sample records which local
references it uses. Additional temperate forest, alpine or coastal profiles can
be evaluated later; they are not part of the initial seven's completion claim.

Shopping, residential, market, office, hotel and plaza remain **land-use/layout
variants** within these profiles. The current [town v6](CITY_THEMES.md) is a
Korean-themed sample with six such variants, not the world theme library.

## Common assets and map-specific writing

The planned common library uses language-neutral building bodies, materials,
signboards and pictograms. This is not an English-only default. Reusable base
meshes/textures must not permanently embed a shop name or other language text.
Visual identity comes from geometry, surfaces, vegetation, street structure and
props rather than lettering alone.

A map author can attach a map-specific sign image or other explicit sign asset
to a designated facade surface. The reusable body stays unchanged; the map owns
the sign's content, language(s), location and dependencies. Its source records
the editable text when authored as text, font/image provenance and license,
layout/direction, and the resulting asset identity. Exact fields and supported
rendering/import formats belong to subsequent implementation, not this document.

Authoring must allow both importing an already prepared sign image and producing
one from text with a suitable licensed font. The latter must correctly shape
and lay out the supported scripts, including right-to-left and combining text
where applicable, and report missing glyphs. Do not silently draw arbitrary
Unicode with the current small Hangul stroke table. Font choice, sizing and
layout belong to the map authoring step. Recipient machines must not need an
installed font or network service to reproduce the exported map.

An exported map includes every required sign image/asset with its hashes and
license metadata. Save As, reopen and export preserve them. Map-specific data
participates in existing package validation, bounds and memory accounting; it
does not justify raising limits or omitting image-decoder costs. A blank or
pictogram sign is an explicit author choice, not a silent replacement for a
missing dependency. A fully baked localized GLB is still a map-specific variant,
not a language-neutral common asset.

Map writing and the application's UI language are independent. Opening a map
with another UI locale must not change its signs, asset hashes or world content.
Korean, Arabic, Thai or mixed-language signs are allowed when deliberately
authored for that map; region selection does not force one language.

## Current implementation and required evidence

`scripts/shop_block.py` embeds the six Hanbit names as mesh strokes;
`scripts/city_themes.py` embeds `한빛시장` and reuses the Hanbit shops elsewhere
in the same town. These are existing map-specific examples, **not image textures
or a general multilingual sign authoring API**. Merely documenting this scope
does not separate the meshes or add sign attachment support. Keep the v3/v4/v5
baselines and current v6 package/lock as historical comparison evidence.

MapEditor owns the authoring choices, per-map sign creation/import and sample
layouts. MapKit owns reusable common assets/rendering and public package
validation. The standalone public editor must not depend on game repositories.

Implementation evidence must include:

- Seven visibly distinct representative scenes, each with terrain, structures,
  vegetation and props appropriate to its scope; a palette swap is insufficient.
- Language-neutral common assets reused by maps with different writing, without
  changing the common body or its collision. Explicit map-specific variants
  must not be counted as new common base assets.
- At least Korean, a Latin-script example and relevant Arabic/Thai shaping or
  prepared-image examples; distinguish imported-image support from editable text
  generation and never claim all languages from a few sample strings.
- Save As → reopen → export → offline consumer display, unchanged signs across
  UI locales, missing-dependency diagnostics and complete byte/license accounting.
- Actual traversable routes, matching collision, cell transitions and retirement
  under the existing budgets. No new snow/ice/wet-ground physics is implied by
  visual theme selection; any such gameplay change is a separate runtime task.
