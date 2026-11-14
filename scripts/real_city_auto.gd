extends RefCounted
## Automatic real-city choices from the PBF lookup context (`importers/pbf_places.py`):
## the country's traffic convention and default architecture, and the map extent
## around a named place. These
## are Editor defaults, not survey data; explicit wizard and recipe values win.
##
## Places fill a centre; the default geodesic radius is 2km source distance.
const M_PER_DEGREE := 111320.0
## Largest source radius (circle) or half-side (square) a centred extent accepts.
const MAX_RADIUS_KM := 2.5
## ISO 3166-1 alpha-2 codes driving on the left. A `driving_side` tag on the
## country boundary in the PBF wins over this table.
const LEFT_HAND := ["AG","AI","AU","BB","BD","BM","BN","BS","BT","BW","CC","CK","CX","CY","DM","FJ","FK","GB","GD","GG","GY","HK","ID","IE","IM","IN","JE","JM","JP","KE","KI","KN","KY","LC","LK","LS","MO","MS","MT","MU","MV","MW","MY","MZ","NA","NF","NP","NR","NU","NZ","PG","PK","PN","SB","SC","SG","SH","SR","SZ","TC","TH","TK","TL","TO","TT","TV","TZ","UG","VC","VG","VI","WS","ZA","ZM","ZW"]
## Countries whose signal heads are mostly horizontal; everywhere else vertical.
const HORIZONTAL_SIGNALS := ["JP","KP","KR","TW"]
## Countries whose centre lines are mostly white; everywhere else yellow
## (the Americas, Korea, China, Taiwan, Norway, Finland, Iceland, ...).
const WHITE_CENTRE := ["AD","AL","AT","AU","BA","BE","BG","BY","CH","CY","CZ","DE","DK","DZ","EE","ES","FR","GB","GG","GR","HK","HR","HU","ID","IE","IM","IN","IT","JE","JP","LI","LT","LU","LV","MA","MC","MD","ME","MK","MT","MY","NL","NZ","PL","PT","RO","RS","RU","SE","SG","SI","SK","SM","TN","TR","UA","VA","XK","ZA"]

## Catalogue architecture of a country's typical city buildings (regional_catalog.json).
## A default only: explicit profiles, regions, corrections and source tags win;
## countries not listed keep the catalogue default (`modern`).
const ARCHITECTURES := {
	"KR":"korean_modern", "KP":"korean_modern", "JP":"japanese_modern",
	"CN":"chinese_modern", "TW":"chinese_modern", "HK":"chinese_modern", "MO":"chinese_modern",
	"SG":"shophouse", "MY":"shophouse",
	"TH":"southeast_asian", "VN":"southeast_asian", "KH":"southeast_asian", "LA":"southeast_asian", "MM":"southeast_asian", "PH":"southeast_asian", "ID":"southeast_asian", "BN":"southeast_asian",
	"IN":"south_asian", "PK":"south_asian", "BD":"south_asian", "LK":"south_asian", "NP":"south_asian",
	"AE":"middle_eastern", "SA":"middle_eastern", "QA":"middle_eastern", "KW":"middle_eastern", "BH":"middle_eastern", "OM":"middle_eastern", "YE":"middle_eastern", "IQ":"middle_eastern", "IR":"middle_eastern", "JO":"middle_eastern", "SY":"middle_eastern", "LB":"middle_eastern", "IL":"middle_eastern", "PS":"middle_eastern", "EG":"middle_eastern", "LY":"middle_eastern", "TN":"middle_eastern", "DZ":"middle_eastern", "MA":"middle_eastern", "AF":"middle_eastern",
	"US":"north_american_suburb", "CA":"north_american_suburb", "AU":"north_american_suburb", "NZ":"north_american_suburb",
	"MX":"latin_colonial", "GT":"latin_colonial", "HN":"latin_colonial", "SV":"latin_colonial", "NI":"latin_colonial", "CR":"latin_colonial", "PA":"latin_colonial", "CU":"latin_colonial", "DO":"latin_colonial", "PR":"latin_colonial", "CO":"latin_colonial", "VE":"latin_colonial", "EC":"latin_colonial", "PE":"latin_colonial", "BO":"latin_colonial", "CL":"latin_colonial", "AR":"latin_colonial", "UY":"latin_colonial", "PY":"latin_colonial", "BR":"latin_colonial",
	"GB":"british_terrace", "IE":"british_terrace", "IM":"british_terrace", "JE":"british_terrace", "GG":"british_terrace",
	"FR":"parisian", "MC":"parisian", "NL":"european_brick", "BE":"european_brick", "DK":"european_brick",
	"DE":"european_stone", "AT":"european_stone", "CH":"european_stone", "LI":"european_stone", "LU":"european_stone", "CZ":"european_stone", "SK":"european_stone", "HU":"european_stone", "PL":"european_stone", "SI":"european_stone", "HR":"european_stone",
	"IT":"mediterranean", "SM":"mediterranean", "VA":"mediterranean", "ES":"mediterranean", "PT":"mediterranean", "AD":"mediterranean", "GR":"mediterranean", "CY":"mediterranean", "MT":"mediterranean", "TR":"mediterranean",
	"NO":"nordic_timber", "SE":"nordic_timber", "FI":"nordic_timber", "IS":"nordic_timber", "FO":"nordic_timber", "GL":"nordic_timber",
	"RU":"east_european_panel", "BY":"east_european_panel", "UA":"east_european_panel", "MD":"east_european_panel", "EE":"east_european_panel", "LV":"east_european_panel", "LT":"east_european_panel", "RO":"east_european_panel", "BG":"east_european_panel", "RS":"east_european_panel", "BA":"east_european_panel", "ME":"east_european_panel", "MK":"east_european_panel", "AL":"east_european_panel", "XK":"east_european_panel", "GE":"east_european_panel", "AM":"east_european_panel", "AZ":"east_european_panel", "KZ":"east_european_panel", "UZ":"east_european_panel", "KG":"east_european_panel", "TJ":"east_european_panel", "TM":"east_european_panel", "MN":"east_european_panel",
	"AQ":"polar_station"}

## The country's catalogue architecture, or "" for an unknown or unlisted country.
static func architecture(country: Variant) -> String:
	return str(ARCHITECTURES.get(str(country.get("code", "")) if country is Dictionary else "", ""))

## {driving_side, signal_style, centre_line, country, basis}; an unknown country keeps
## the Editor's right-hand / horizontal / yellow defaults with basis "default".
static func traffic(country: Variant) -> Dictionary:
	var code := str(country.get("code", "")) if country is Dictionary else ""
	if code == "": return {"driving_side":"right", "signal_style":"horizontal", "centre_line":"yellow", "country":"", "basis":"default"}
	var side := str(country.get("driving_side", ""))
	if side not in ["left", "right"]: side = "left" if code in LEFT_HAND else "right"
	return {"driving_side":side, "signal_style":"horizontal" if code in HORIZONTAL_SIGNALS else "vertical", "centre_line":"white" if code in WHITE_CENTRE else "yellow", "country":code, "basis":str(country.get("basis", ""))}

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
	return circle(point, 2.0, scale, cell_cm)

static func circle(point: Array, radius_km: float, scale: int, cell_cm: int) -> Dictionary:
	# Conservative scan rectangle; Python constructs the exact WGS84 disk.
	var scan := box(point, radius_km * 2020.0)
	return {"kind":"circle", "center":point, "radius_km":radius_km, "bbox":scan, "cells":cells(scan, scale, cell_cm)}

## Square of side 2·radius_km, axis-aligned in the map (UTM) frame of its centre.
## The scan rectangle allows for grid convergence and scale factor; Python builds
## the exact square.
static func square(point: Array, radius_km: float, scale: int, cell_cm: int) -> Dictionary:
	var scan := box(point, radius_km * 2120.0)
	return {"kind":"square", "center":point, "radius_km":radius_km, "bbox":scan, "cells":cells(box(point, radius_km * 2000.0), scale, cell_cm)}

## `circle` or `square` around point; any other shape is a caller error.
static func shaped(shape: String, point: Array, radius_km: float, scale: int, cell_cm: int) -> Dictionary:
	return square(point, radius_km, scale, cell_cm) if shape == "square" else circle(point, radius_km, scale, cell_cm)

## Source km² of a shaped extent.
static func area_km2(choice: Dictionary) -> float:
	var r := float(choice.radius_km)
	return 4.0 * r * r if choice.get("kind") == "square" else PI * r * r

## Rough load guidance for a shaped extent, scaled by source area from measured
## 2km-circle, 1:3 runs with DEM (12.6 km²: about 7–32 minutes, 1–5 MB packages;
## dense downtowns sit at the upper end). Not a promise: density and the machine
## dominate. Level: "normal" up to the 2km circle, "high" above.
const REFERENCE_KM2 := 12.566
const REFERENCE_MINUTES := [7.0, 32.0]
const REFERENCE_MB := [1.0, 5.0]
static func estimate(choice: Dictionary) -> Dictionary:
	var ratio := area_km2(choice) / REFERENCE_KM2
	return {"area_km2":area_km2(choice), "cells":int(choice.get("cells", 0)),
		"minutes":[REFERENCE_MINUTES[0] * ratio, REFERENCE_MINUTES[1] * ratio],
		"package_mb":[REFERENCE_MB[0] * ratio, REFERENCE_MB[1] * ratio],
		"level":"high" if ratio > 1.01 else "normal"}

## Multi-line load guidance for the wizard.
static func guidance(choice: Dictionary) -> String:
	var I18N := preload("./locale_text.gd")
	var e := estimate(choice)
	var text: String = I18N.t("Area %.1f km² · about %d cells · generation about %d–%d min · package about %.0f–%.0f MB") % [e.area_km2, e.cells, roundi(e.minutes[0]), roundi(e.minutes[1]), e.package_mb[0], e.package_mb[1]]
	if e.level == "high": text += "\n" + I18N.t("Larger than the recommended 2 km circle: generation, game loading and phone memory grow with the area; dense downtowns take longest.")
	return text

## One line for the wizard and recipe report.
static func describe(choice: Dictionary) -> String:
	var I18N := preload("./locale_text.gd")
	if choice.get("kind") == "square": return I18N.t("%.2f km square half-side · %d cells") % [choice.radius_km, choice.cells]
	return I18N.t("%.2f km radius · %d cells") % [choice.radius_km, choice.cells]
