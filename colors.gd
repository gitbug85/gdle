var themes: Dictionary = {}

func _init() -> void:
	_init_themes()

func _init_themes() -> void:
	# Default theme
	themes["default"] = {
		"none": Color(0.3, 0.3, 0.3),
		"dead": Color(0.39, 0.39, 0.39),
		"dead_empty": Color(0.2, 0.2, 0.2),
		"dead_hard_empty": Color(0.26, 0.24, 0.22),

		"photosynthetic": Color(0.58, 0.85, 0.58),
		"chemosynthetic": Color(0.79, 0.60, 0.58),
		"empty": Color(0.59, 0.55, 0.39),
		"hard_empty": Color(0.71, 0.67, 0.51),
		"attack": Color(0.85, 0.85, 0.51),
		"gene_replacement": Color(0.83, 0.42, 0.54),
		"photoreceptor": Color(0.39, 0.59, 0.78),
	}

	themes["ocean"] = {
		"none": Color(0.15, 0.18, 0.24),
		"dead": Color(0.25, 0.29, 0.36),
		"dead_empty": Color(0.12, 0.16, 0.22),
		"dead_hard_empty": Color(0.20, 0.23, 0.29),

		"photosynthetic": Color(0.30, 0.80, 0.65),
		"chemosynthetic": Color(0.35, 0.65, 0.85),
		"empty": Color(0.30, 0.40, 0.55),
		"hard_empty": Color(0.40, 0.52, 0.67),
		"attack": Color(0.95, 0.75, 0.35),
		"gene_replacement": Color(0.80, 0.40, 0.70),
		"photoreceptor": Color(0.40, 0.75, 0.95),
	}

func get_color(tile: String, theme: String = "default") -> Color:
	if not themes.has(theme):
		push_warning("Unknown color theme: " + theme)
		theme = "default"

	var selected_theme: Dictionary = themes[theme]

	if not selected_theme.has(tile):
		push_warning("Unknown tile type: " + tile)
		return selected_theme["none"]

	return selected_theme[tile]
