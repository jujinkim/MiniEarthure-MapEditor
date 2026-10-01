extends RefCounted
## Translate display copies only, before interpolation. Never translate authored text.
static func t(message: String) -> String:
	var translated := String(TranslationServer.translate(message))
	if translated == message and message.contains("\n"):
		var lines := message.split("\n")
		for i in lines.size(): lines[i] = String(TranslationServer.translate(lines[i]))
		return "\n".join(lines)
	return translated

static func display(message: String) -> String:
	return preload("./diagnostic_text.gd").translate(message)

static func diagnostic(message: String) -> String:
	if message.is_empty(): return ""
	var translated := display(message)
	if translated != message or TranslationServer.get_locale().begins_with("en"): return translated
	if message.begins_with("E_") and message.contains(": "):
		var split := message.find(": ")
		return message.substr(0, split) + ": " + error({"code":message.substr(0, split), "message":message.substr(split + 2)})
	return t("Operation details: %s") % message

const ERROR_MESSAGES := {
  "E_MEMORY_BUDGET": "Not enough memory for this operation",
  "E_CANCELLED": "Operation cancelled",
  "E_TIMEOUT": "Operation timed out",
  "E_IO": "Could not read or write the file",
  "E_IMPORT": "Could not import the source",
  "E_IMPORT_NATIVE": "Import validation failed",
  "E_DEM": "Terrain import failed",
  "E_TRACK": "Track generation failed",
  "E_COURSE": "Course validation failed",
  "E_GHOST": "Ghost could not be loaded",
  "E_CONNECTION": "Connection failed",
  "E_SCHEMA": "Invalid document data",
  "E_FORMAT": "Unsupported or damaged file",
  "E_EXPORT_IO": "Package export failed",
  "E_EXPORT_EXISTS": "The destination already exists",
  "E_STALE": "The operation is out of date",
  "E_IMPORT_STALE": "The operation is out of date",
  "E_DEM_STALE": "The operation is out of date",
  "E_RENDER_ASSET": "Could not prepare the display assets",
  "E_SPAWN": "Could not prepare the starting position",
  "E_RACE": "Race preparation failed",
  "E_BUDGET": "Not enough memory for this operation",
  "E_GRIND_BUDGET": "Not enough memory for this operation",
  "E_TRACK_BUDGET": "Not enough memory for this operation",
  "E_SURFACE_LIMIT": "Not enough memory for this operation",
  "E_LIMIT": "Not enough memory for this operation",
  "E_ARCHIVE": "Unsupported or damaged file",
  "E_ZIP": "Unsupported or damaged file",
  "E_JSON": "Unsupported or damaged file",
  "E_MANIFEST": "Unsupported or damaged file",
  "E_HASH": "Unsupported or damaged file",
  "E_VERSION": "Unsupported or damaged file",
  "E_DOCUMENT": "Invalid document data",
  "E_ID": "Invalid document data",
  "E_REFERENCE": "Invalid document data",
  "E_STATE": "Invalid document data",
  "E_USAGE": "Invalid document data",
  "E_PATH": "Invalid document data",
  "E_PROVENANCE": "Invalid document data",
  "E_ATTRIBUTION": "Invalid document data",
  "E_CHECKPOINT": "Course validation failed",
  "E_COURSE_BOUNDS": "Course validation failed",
  "E_COURSE_HASH": "Course validation failed",
  "E_COURSE_JSON": "Course validation failed",
  "E_COURSE_LIMIT": "Course validation failed",
  "E_COURSE_MAP": "Course validation failed",
  "E_COURSE_VALIDATION": "Course validation failed",
  "E_COURSE_VERSION": "Course validation failed",
  "E_COURSE_WORLD": "Course validation failed",
  "E_TRACK_ASSEMBLY": "Track generation failed",
  "E_TRACK_COURSE": "Track generation failed",
  "E_TRACK_DRAFT": "Track generation failed",
  "E_TRACK_DURATION": "Track generation failed",
  "E_TRACK_MODIFIED": "Track generation failed",
  "E_TRACK_REQUIRED": "Track generation failed",
  "E_TRACK_SETTINGS": "Track generation failed",
  "E_TRACK_SOURCE": "Track generation failed",
  "E_TRACK_SUPPORT": "Track generation failed",
  "E_CELL": "Map geometry validation failed",
  "E_GEOMETRY": "Map geometry validation failed",
  "E_GIMMICK": "Map geometry validation failed",
  "E_GRIND_CONNECTION": "Map geometry validation failed",
  "E_GRIND_SOURCE": "Map geometry validation failed",
  "E_HEIGHTMAP": "Map geometry validation failed",
  "E_INDEX": "Map geometry validation failed",
  "E_PLACEMENT": "Map geometry validation failed",
  "E_QUERY": "Map geometry validation failed",
  "E_ROAD": "Map geometry validation failed",
  "E_SEAM": "Map geometry validation failed",
  "E_WATER": "Map geometry validation failed",
  "E_ASSET": "Could not prepare the display assets",
  "E_ENVIRONMENT": "Environment settings could not be applied",
  "E_RELEASE": "Release compatibility could not be verified",
  "E_RACE_SIZE": "Race preparation failed"
}

static func error(value: Dictionary) -> String:
	var message := str(value.get("message", ""))
	var translated := display(message)
	if translated != message: return translated
	var code := str(value.get("code", ""))
	var summary := t(ERROR_MESSAGES.get(code, "Operation could not be completed"))
	return summary + "\n" + t("Operation details: %s") % message

static func result(value: Dictionary) -> String:
	var failure: Dictionary = value.get("error", value)
	return str(failure.get("code", "")) + ": " + error(failure)

const BUILTIN_NAMES := {
  "forest": "Forest",
  "orchard": "Orchard",
  "left": "Left",
  "right": "Right",
  "center": "Center",
  "ground": "Ground",
  "elevated": "Elevated",
  "bridge": "Bridge",
  "underpass": "Underpass",
  "tunnel": "Tunnel",
  "asphalt": "Asphalt",
  "concrete": "Concrete",
  "dirt": "Dirt",
  "gravel": "Gravel",
  "grass": "Grass",
  "residential": "Residential",
  "commercial": "Commercial",
  "industrial": "Industrial",
  "public": "Public",
  "brick": "Brick",
  "wood": "Wood",
  "flat": "Flat",
  "gable": "Gable",
  "raise": "Raise",
  "lower": "Lower",
  "flatten": "Flatten",
  "smooth": "Smooth",
  "default": "Default",
  "urban": "Urban",
  "rural": "Rural",
  "circuit": "Circuit",
  "sprint": "Sprint",
  "air": "Air",
  "manual": "Manual",
  "sphere": "Sphere",
  "hemisphere": "Hemisphere",
  "modern": "Modern",
  "adobe": "Adobe",
  "timber": "Timber",
  "tropical": "Tropical",
  "temperate": "Temperate",
  "polar": "Polar",
  "village": "Village",
  "sparse": "Sparse",
  "wilderness": "Wilderness",
  "countryside": "Countryside",
  "metropolis": "Metropolis",
  "desert": "Desert",
  "jungle": "Jungle",
  "ramp": "Ramp",
  "jump": "Jump",
  "humps": "Humps",
  "pipe": "Pipe",
  "log": "Log",
  "halfpipe": "Halfpipe",
  "rotate": "Rotate",
  "barrier": "Barrier",
  "platform": "Platform",
  "boost": "Boost",
  "launch": "Launch",
  "loop": "Loop",
  "cylinder": "Cylinder",
  "auto": "Automatic",
  "ltr": "Left to right",
  "rtl": "Right to left",
  "target_speed": "Target speed",
  "jump_height": "Jump height",
  "air_ring": "Air Ring",
  "middle-eastern": "Middle Eastern",
  "southeast-asian": "Southeast Asian",
  "builtin:tree": "Tree",
  "builtin:fence": "Fence",
  "builtin:streetlight": "Streetlight",
  "starting": "Starting",
  "starting native validation": "Starting native validation",
  "read": "Reading",
  "parse": "Parsing",
  "convert": "Converting",
  "write": "Writing",
  "complete": "Complete",
  "source": "Source",
  "snapshot": "Snapshot",
  "recheck": "Rechecking",
  "generate": "Generating",
  "prepare": "Preparing",
  "validate": "Validating",
  "cells": "cells",
  "bytes": "bytes",
  "steps": "steps",
  "features": "features",
  "records": "records"
}

static func builtin(id: String) -> String:
	return t(BUILTIN_NAMES.get(id, id))

static func filters(values: Array) -> PackedStringArray:
	var result := PackedStringArray()
	for value: String in values:
		var parts := value.split(";")
		if parts.size() > 1: parts[1] = t(parts[1].strip_edges())
		result.append(";".join(parts))
	return result
