extends RefCounted
## Automatic real-city choices from the PBF lookup context (`importers/pbf_places.py`):
## the country's traffic convention and the map extent around a named place. These
## are Editor defaults, not survey data; explicit wizard and recipe values win.
##
## Places fill a centre; the default geodesic radius is 1.5km source distance.
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

static func box(point: Array, side_m: float) -> Array:
	var half_lat := side_m * 0.5 / M_PER_DEGREE
	var half_lon := half_lat / maxf(cos(deg_to_rad(float(point[1]))), 0.01)
	var result := [float(point[0]) - half_lon, float(point[1]) - half_lat, float(point[0]) + half_lon, float(point[1]) + half_lat]
	return result.map(func(v): return snappedf(v, 0.000001))

## Fixed centre/radius choice, independent of administrative boundaries.
static func extent(_context: Variant, point: Array, scale: int, cell_cm: int) -> Dictionary:
	return circle(point, 1.5, scale, cell_cm)

static func circle(point: Array, radius_km: float, scale: int, cell_cm: int) -> Dictionary:
	# Conservative scan rectangle; Python constructs the exact WGS84 disk.
	var scan := box(point, radius_km * 2020.0)
	return {"kind":"circle", "center":point, "radius_km":radius_km, "bbox":scan, "cells":cells(scan, scale, cell_cm)}

## One line for the wizard and recipe report.
static func describe(choice: Dictionary) -> String:
	return preload("./locale_text.gd").t("%.2f km radius · %d cells") % [choice.radius_km, choice.cells]
