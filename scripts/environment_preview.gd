extends RefCounted
const PROFILE := preload("res://addons/mapkit/godot/environment_profile.gd")
var config := {"intensity":0.7,"sunset_minutes":1080,"sunrise_minutes":360,"aurora_probability":1.0,"celestial_mode":"simple"}
var profile: Dictionary = PROFILE.defaults()
var seconds := 43200.0
var elapsed := 0.0
var seed := 1
var weather := "clear"
var previous_weather := "clear"
var wet := 0
var snow := 0
func celestial() -> Dictionary: return PROFILE.celestial(seconds,config)
func blend() -> float: return 1.0
