extends RefCounted
## Automatic real-city choices from the PBF lookup context (`importers/pbf_places.py`):
## the country's traffic convention and the map extent around a named place. These
## are Editor defaults, not survey data; explicit wizard and recipe values win.
##
## Extent: the largest administrative area containing the place whose bbox fits
## MAX_CELLS at the chosen 1:D and cell size and covers at least MIN_AREA_SHARE of
## the fallback box; otherwise a square of box_side_m() source metres centred on it.
const MAX_CELLS := 512
const BOX_M := 5000.0
const MIN_AREA_SHARE := 0.25
const M_PER_DEGREE := 111320.0
## ISO 3166-1 alpha-2 codes driving on the left. A `driving_side` tag on the
## country boundary in the PBF wins over this table.
const LEFT_HAND := ["AG","AI","AU","BB","BD","BM","BN","BS","BT","BW","CC","CK","CX","CY","DM","FJ","FK","GB","GD","GG","GY","HK","ID","IE","IM","IN","JE","JM","JP","KE","KI","KN","KY","LC","LK","LS","MO","MS","MT","MU","MV","MW","MY","MZ","NA","NF","NP","NR","NU","NZ","PG","PK","PN","SB","SC","SG","SH","SR","SZ","TC","TH","TK","TL","TO","TT","TV","TZ","UG","VC","VG","VI","WS","ZA","ZM","ZW"]
## Countries whose signal heads are mostly horizontal; everywhere else vertical.
const HORIZONTAL_SIGNALS := ["JP","KP","KR","TW"]

## {driving_side, signal_style, country, basis}; an unknown country keeps the
## Editor's right-hand / horizontal defaults with basis "default".
static func traffic(country: Variant) -> Dictionary:
	var code := str(country.get("code", "")) if country is Dictionary else ""
	if code == "": return {"driving_side":"right", "signal_style":"horizontal", "country":"", "basis":"default"}
	var side := str(country.get("driving_side", ""))
	if side not in ["left", "right"]: side = "left" if code in LEFT_HAND else "right"
	return {"driving_side":side, "signal_style":"horizontal" if code in HORIZONTAL_SIGNALS else "vertical", "country":code, "basis":str(country.get("basis", ""))}

## Map cells of a [west, south, east, north] box at 1:scale with cell_cm map cells.
static func cells(box: Array, scale: int, cell_cm: int) -> int:
	var cell_m := cell_cm / 100.0 * scale
	var width := (float(box[2]) - float(box[0])) * M_PER_DEGREE * cos(deg_to_rad((float(box[1]) + float(box[3])) * 0.5))
	var height := (float(box[3]) - float(box[1])) * M_PER_DEGREE
	return int(ceil(width / cell_m)) * int(ceil(height / cell_m))

## Fallback square side in source metres: BOX_M, smaller when it would exceed MAX_CELLS.
static func box_side_m(scale: int, cell_cm: int) -> float:
	return minf(BOX_M, floorf(sqrt(MAX_CELLS)) * cell_cm / 100.0 * scale)

static func box(point: Array, side_m: float) -> Array:
	var half_lat := side_m * 0.5 / M_PER_DEGREE
	var half_lon := half_lat / maxf(cos(deg_to_rad(float(point[1]))), 0.01)
	var result := [float(point[0]) - half_lon, float(point[1]) - half_lat, float(point[0]) + half_lon, float(point[1]) + half_lat]
	return result.map(func(v): return snappedf(v, 0.000001))

## {kind:"area", area:{name, source_id, admin_level, bbox, issue}, cells} or
## {kind:"bbox", bbox, side_m, cells} for a place at `point` with its lookup context.
static func extent(context: Variant, point: Array, scale: int, cell_cm: int) -> Dictionary:
	var side := box_side_m(scale, cell_cm)
	var areas: Array = context.get("areas", []) if context is Dictionary else []
	for area: Dictionary in areas:
		var count := cells(area.bbox, scale, cell_cm)
		if count <= MAX_CELLS and float(area.km2) * 1000000.0 >= MIN_AREA_SHARE * side * side:
			return {"kind":"area", "area":{"name":area.name, "source_id":area.source_id, "admin_level":area.admin_level, "bbox":area.bbox, "issue":""}, "cells":count}
	var square := box(point, side)
	return {"kind":"bbox", "bbox":square, "side_m":side, "cells":cells(square, scale, cell_cm)}

## One line for the wizard / reports, e.g. "Chuo (admin 8) · 64 cells".
static func describe(choice: Dictionary) -> String:
	if choice.get("kind") == "area": return "%s (admin %s) · %d cells" % [choice.area.name, choice.area.admin_level, choice.cells]
	return "%.1f × %.1f km square · %d cells" % [choice.side_m / 1000.0, choice.side_m / 1000.0, choice.cells]
