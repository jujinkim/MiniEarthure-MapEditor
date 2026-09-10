extends "res://scripts/document_store.gd"
var forbid_preparation := false
var forbidden_calls := 0

func _validate(value: Dictionary) -> Dictionary:
	if forbid_preparation:
		forbidden_calls += 1
		return {"ok":false, "error":{"code":"TEST_UI_NATIVE", "message":"Final commit repeated native validation."}}
	return super._validate(value)

func _signature(value: Dictionary) -> String:
	if forbid_preparation:
		forbidden_calls += 1
		return "forbidden"
	return super._signature(value)

func record_id(field: String, record: Dictionary) -> String:
	if forbid_preparation:
		forbidden_calls += 1
		return "forbidden"
	return super.record_id(field, record)
