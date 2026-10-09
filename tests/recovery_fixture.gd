extends RefCounted
## Test-only retained recovery files from before explicit-save policy. Never a UI action.
static func path(store: RefCounted) -> String:
	return "user://fixtures/recovery-%s-%s.json" % [store.get_instance_id(),store.session_id]
static func write(store: RefCounted) -> String:
	var draft: Dictionary = store.track_source() if store.draft_pending() else {}
	var value := {"recovery_version":1,"document":store.document,"project_path":store.project_path,
		"base_sha256":store._disk_digest,"document_sha256":JSON.stringify(store.document).sha256_text(),
		"draft":draft,"draft_revision":store.draft_revision,"validated_revision":store.validated_revision,
		"draft_sha256":JSON.stringify(draft).sha256_text()}
	var text := JSON.stringify(value)
	if store.files.digest(path(store)) == text.sha256_text(): return ""
	return store.files.write(path(store),text,store.files.digest(path(store)))
