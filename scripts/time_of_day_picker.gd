extends OptionButton
## Hourly list, displayed as a clock; values remain hours for environment APIs.
signal value_changed(value: float)
var value: float:
	get:return float(get_selected_id())/60.0
	set(next):select(posmod(roundi(next),24))
func _init() -> void:
	fit_to_longest_item=false
	custom_minimum_size.y=44
	for minute in range(0,1440,60):add_item("%02d:%02d"%[minute/60,minute%60],minute)
	item_selected.connect(func(_index:int):value_changed.emit(value))
