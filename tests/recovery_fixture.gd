extends RefCounted
## Test-only retained recovery files from before explicit-save policy. Never a UI action.
## Inside the running validator's own scratch folder when it has one
## (tests/validator_scratch.gd), so the files go with it on exit.
static func path(store: RefCounted) -> String:
	var loop := Engine.get_main_loop()
	var scratch: Variant = loop.get("scratch") if loop != null else null
	var folder: String = scratch if scratch is String and scratch != "" else "user://fixtures"
	return folder.path_join("recovery-%s-%s.json" % [store.get_instance_id(),store.session_id])
static func write(store: RefCounted) -> String:
	# JSON round trip: integers read back as floats, so the digest must cover that form.
	var draft: Dictionary = JSON.parse_string(JSON.stringify(store.track_source() if store.draft_pending() else {}))
	var value := {"recovery_version":1,"document":store.document,"project_path":store.project_path,
		"base_sha256":store._disk_digest,"document_sha256":JSON.stringify(store.document).sha256_text(),
		"draft":draft,"draft_revision":store.draft_revision,"validated_revision":store.validated_revision,
		"draft_sha256":JSON.stringify(draft).sha256_text()}
	var text := JSON.stringify(value)
	if store.files.digest(path(store)) == text.sha256_text(): return ""
	return store.files.write(path(store),text,store.files.digest(path(store)))
