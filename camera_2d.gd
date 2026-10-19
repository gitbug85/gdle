extends Camera2D

@export var move_speed: float = 500.0
@export var zoom_speed: float = 0.1
@export var min_zoom: float = 0.5
@export var max_zoom: float = 3.0

func _process(delta: float) -> void:
	# Move camera
	var direction := Vector2.ZERO

	direction.x = Input.get_axis("ui_left", "ui_right")
	direction.y = Input.get_axis("ui_up", "ui_down")

	global_position += direction.normalized() * move_speed * delta

func _input(event: InputEvent) -> void:
	# Zoom in and out with mouse wheel
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_WHEEL_UP:
			zoom += Vector2.ONE * zoom_speed
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			zoom -= Vector2.ONE * zoom_speed

		zoom.x = clamp(zoom.x, min_zoom, max_zoom)
		zoom.y = clamp(zoom.y, min_zoom, max_zoom)
