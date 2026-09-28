extends VBoxContainer
signal requested(settings: Dictionary)
signal cancelled
var seed_input: LineEdit
var circuit: CheckButton
var duration: OptionButton
var difficulty: OptionButton
var time_input: SpinBox
var selections := {}
var _defaults := {}
var _duration_options := {}
var note: Label
var catalogue_ready := false

func _load_catalogue() -> Dictionary:
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	return JSON.parse_string(bridge.track_catalogue()).data

func _ready() -> void:
	var catalogue := _load_catalogue()
	if not catalogue.get("selection_ids") is Array:
		note = Label.new()
		note.text = "트랙 생성 모듈이 현재 화면과 맞지 않습니다. 게임과 Godot Editor를 완전히 종료한 후 최신 빌드로 다시 실행해 주세요."
		note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		add_child(note)
		return
	catalogue_ready = true
	_defaults = catalogue.defaults
	_duration_options = catalogue.duration_options
	var toggle := Button.new()
	toggle.text = "Seed 트랙 생성"
	add_child(toggle)
	var form := VBoxContainer.new()
	add_child(form)
	form.hide()
	toggle.pressed.connect(func(): form.visible = not form.visible)
	seed_input = LineEdit.new()
	seed_input.placeholder_text = "Seed"
	seed_input.text = str(int(_defaults.seed))
	form.add_child(seed_input)
	var random_seed := Button.new()
	random_seed.text = "새 seed"
	random_seed.pressed.connect(func(): seed_input.text = str(randi()))
	form.add_child(random_seed)
	circuit = CheckButton.new()
	circuit.text = "순환 코스"
	circuit.button_pressed = _defaults.circuit
	form.add_child(circuit)
	duration = OptionButton.new()
	_refresh_duration(int(_defaults.duration_seconds))
	circuit.toggled.connect(func(_value: bool): _refresh_duration(duration.get_selected_id()))
	form.add_child(duration)
	difficulty = OptionButton.new()
	for title in ["초급","보통","고급"]: difficulty.add_item(title)
	difficulty.select(["easy","normal","hard"].find(_defaults.difficulty))
	form.add_child(difficulty)
	time_input = SpinBox.new()
	time_input.min_value = 0
	time_input.max_value = 23.75
	time_input.step = 0.25
	time_input.value = float(_defaults.time_minutes)/60.0
	time_input.suffix = "시 · 건조 / 무풍"
	form.add_child(time_input)
	var grid := GridContainer.new()
	grid.columns = 2
	form.add_child(grid)
	var labels := {"sprint_lane":"질주코스 · 16m","cylinder":"원통","loop":"수직 루프","spiral_up":"상승 나선","spiral_down":"하강 나선","jump":"점프","obstacles":"장애물","acceleration_panel":"가속 패널","boost_chain":"연속 부스터","air_ring":"공중 링","banked_chicane":"U자 뱅크 코너","overpass":"고가 지름길","roller_waves":"연속 롤러 언덕","offset_jump":"옆으로 착지 점프"}
	for id: String in catalogue.selection_ids:
		var check := CheckBox.new()
		check.text = labels.get(id,id)
		check.button_pressed = id in _defaults.gimmicks
		grid.add_child(check)
		selections[id] = check
	note = Label.new()
	note.text = "선택한 기믹은 모두 포함하며 필요하면 목표 시간보다 길어집니다. 도로와 원통 폭은 6·4·2m이고 seed에 따라 직선과 코너 비율이 달라집니다. 같은 기믹 계열은 최대 2개 연속입니다. 질주코스에는 자동 가속이 없습니다. 장애물은 기존 노면에 초급 약 64m·보통 32m·고급 16m당 하나씩 안전한 공간에 설치합니다."
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	form.add_child(note)
	var generate := Button.new()
	generate.text = "생성 / 재생성"
	generate.pressed.connect(func():
		if not seed_input.text.is_valid_int() or int(seed_input.text)<0 or int(seed_input.text)>9007199254740991:
			note.text = "Seed는 0~9007199254740991 정수입니다"
			return
		requested.emit(settings()))
	form.add_child(generate)
	var cancel := Button.new()
	cancel.text = "생성 취소"
	cancel.pressed.connect(func(): cancelled.emit())
	form.add_child(cancel)

func settings() -> Dictionary:
	if not catalogue_ready: return {}
	var enabled: Array = []
	for id: String in selections:
		if selections[id].button_pressed: enabled.append(id)
	return {"seed":int(seed_input.text),"circuit":circuit.button_pressed,"duration_seconds":duration.get_selected_id(),
		"difficulty":["easy","normal","hard"][difficulty.selected],"time_minutes":roundi(time_input.value*60.0),"gimmicks":enabled}

func restore(value: Dictionary) -> void:
	if not catalogue_ready: return
	seed_input.text = str(int(value.seed))
	circuit.button_pressed = value.circuit
	_refresh_duration(int(value.duration_seconds))
	difficulty.select(["easy","normal","hard"].find(value.difficulty))
	time_input.value = float(value.time_minutes)/60.0
	for id: String in selections: selections[id].button_pressed = id in value.gimmicks

func _refresh_duration(seconds: int) -> void:
	duration.clear()
	var choices: Array = _duration_options["circuit" if circuit.button_pressed else "sprint"]
	for item: Dictionary in choices:
		var label := "약 1분 30초" if int(item.seconds) == 90 else "약 %d분" % (int(item.seconds)/60)
		if circuit.button_pressed: label += " / 한 바퀴 · 최대 %d바퀴" % int(item.max_laps)
		duration.add_item(label,int(item.seconds))
	for i in duration.item_count:
		if duration.get_item_id(i)==seconds: duration.select(i); return
	duration.select(0)

func show_result(assembly: Dictionary) -> void:
	var seconds := float(assembly.estimated_msec) / 1000.0
	var excess := maxf(0.0, seconds - float(assembly.settings.duration_seconds))
	note.text = "생성 결과 · 길이 %.1fm · 예상 %.1f초 · 일반도로 직선 %.1f%%" % [float(assembly.length_cm)/100.0, seconds, 100.0*float(assembly.ordinary_straight_cm)/maxf(1.0,float(assembly.ordinary_length_cm))]
	if excess > 0.0: note.text += " · 요청보다 %.1f초 초과 (필수 기믹·연결 유지)" % excess
