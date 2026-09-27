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

func _ready() -> void:
	var bridge: RefCounted = ClassDB.instantiate("MapKitBridge")
	var catalogue: Dictionary = JSON.parse_string(bridge.track_catalogue()).data
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
	var labels := {"slope":"경사","zigzag":"지그재그","cylinder":"원통","loop":"수직 루프","spiral_up":"상승 나선","spiral_down":"하강 나선","jump":"점프","fixed_obstacle":"고정 장애물","moving_obstacle":"이동 장애물","rotating_obstacle":"회전 장애물","acceleration_panel":"가속 패널","boost_chain":"연속 부스터","air_ring":"공중 링"}
	for piece: Dictionary in catalogue.pieces:
		if piece.id in catalogue.basic_piece_ids: continue
		var check := CheckBox.new()
		check.text = labels.get(piece.id,piece.id)
		check.button_pressed = piece.id in _defaults.gimmicks
		grid.add_child(check)
		selections[piece.id] = check
	note = Label.new()
	note.text = "기본 조각에 완만한 경사·지그재그가 포함됩니다. 선택한 기믹 중 일부가 배치됩니다. 시간은 참고값이며 차량과 운전에 따라 달라집니다. 동일 조각은 최대 4개 연속입니다."
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
	var enabled: Array = []
	for id: String in selections:
		if selections[id].button_pressed: enabled.append(id)
	return {"seed":int(seed_input.text),"circuit":circuit.button_pressed,"duration_seconds":duration.get_selected_id(),
		"difficulty":["easy","normal","hard"][difficulty.selected],"time_minutes":roundi(time_input.value*60.0),"gimmicks":enabled}

func restore(value: Dictionary) -> void:
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
		var label := "약 %d초" % int(item.seconds) if int(item.seconds)<60 else "약 %d분" % (int(item.seconds)/60)
		if circuit.button_pressed: label += " / 한 바퀴 · 최대 %d바퀴" % int(item.max_laps)
		duration.add_item(label,int(item.seconds))
	for i in duration.item_count:
		if duration.get_item_id(i)==seconds: duration.select(i); return
	duration.select(0)
