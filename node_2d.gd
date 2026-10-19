extends Node2D

# ==================== CONFIG ====================
const WIDTH := 500
const HEIGHT := 250
const MAX_EXTENSION := 5
const MAX_AGE := 75
const FPS := 120
const DEFAULT_SUNLIGHT := 0.50
const PHOTOSYNTHETIC_RATE := 0.05
const CHEMO_DEAD_GAIN := 0.9
const CHEMO_EMPTY_GAIN := 0.0
const CHEMO_HARD_COST := 1.0
const ATTACK_DAMAGE := 1
const MUTATION_RATE_CELL_ADD := 0.1
const MUTATION_RATE_CELL_REMOVE := 0.05
const MUTATION_RATE_BRAIN_FLIP := 0.05
const MUTATION_RATE_INT := 0.05
const MUTATION_MAX_ATTEMPTS := 100
const MOVE_REPRO_COST := 1
const ROTATE_REPRO_COST := 1
const REPRO_MUTATION_PROB := 5

# ==================== DATA ====================
class Tile:
	var particle: String = "none"          # none, dead, dead_empty, dead_hard_empty
	var species_id = null
	var lifeform_id = null
	var cell_type = null
	var integer = null

class Species:
	var species_id: int
	var cells: Dictionary = {}             # Vector2i → String
	var integer: int
	var can_move: bool
	var can_rotate: bool

	func _init(id: int, c: Dictionary, i: int, move: bool, rot: bool):
		species_id = id
		cells = c.duplicate()
		integer = i
		can_move = move
		can_rotate = rot

class Lifeform:
	var lifeform_id: int
	var species_id: int
	var child_id: int
	var rotation: int                      # 1-4
	var fat: float = 0.0
	var x: float
	var y: float
	var damage: int = 0
	var age: int = 0
	var was_attacked_this_turn: bool = false

	func _init(id: int, sid: int, rot: int, px: float, py: float):
		lifeform_id = id
		species_id = sid
		child_id = sid
		rotation = rot
		x = px
		y = py

# ==================== STATE ====================
var species_id_to_object: Dictionary = {}
var lifeform_id_to_object: Dictionary = {}
var grid: Array = []                       # Array of Array of Tile
var next_id: int = 0

# Rendering
var image: Image
var texture: ImageTexture
var sprite: Sprite2D

# Colors
var particle_colors := {
	"none": Color(0.3, 0.3, 0.3),
	"dead": Color(0.39, 0.39, 0.39),
	"dead_empty": Color(0.2, 0.2, 0.2),
	"dead_hard_empty": Color(0.26, 0.24, 0.22)
}
var cell_colors := {
	"photosynthetic": Color(0.58, 0.85, 0.58),
	"chemosynthetic": Color(0.79, 0.60, 0.58),
	"empty": Color(0.59, 0.55, 0.39),
	"hard_empty": Color(0.71, 0.67, 0.51),
	"attack": Color(0.85, 0.85, 0.51),
	"gene_replacement": Color(0.83, 0.42, 0.54),
	"photoreceptor": Color(0.39, 0.59, 0.78)
}

func _ready():
	randomize()
	_init_grid()
	_create_initial_species()
	reset()

	# Setup rendering
	image = Image.create(WIDTH, HEIGHT, false, Image.FORMAT_RGB8)
	texture = ImageTexture.create_from_image(image)
	sprite = Sprite2D.new()
	sprite.texture = texture
	sprite.centered = false
	sprite.scale = Vector2(2.0, 2.0)           # make it larger on screen
	add_child(sprite)

	# Center the view a bit
	position = Vector2(50, 50)

func _process(_delta):
	if lifeform_id_to_object.is_empty():
		reset()

	_simulation_step()
	_draw_frame()

# ==================== INITIALIZATION ====================
func _init_grid():
	grid.clear()
	for x in range(WIDTH):
		var col: Array = []
		for y in range(HEIGHT):
			col.append(Tile.new())
		grid.append(col)

func _create_initial_species():
	# Species 0 – photosynthetic blob
	var luca_cells := {
		Vector2i(0, 0): "photosynthetic",
		Vector2i(1, 0): "photosynthetic",
		Vector2i(-1, 0): "photosynthetic",
		Vector2i(0, 1): "photosynthetic",
		Vector2i(0, -1): "photosynthetic",
		Vector2i(1, 1): "photosynthetic",
		Vector2i(-1, -1): "photosynthetic"
	}
	species_id_to_object[0] = Species.new(0, luca_cells, randi() % 10, false, false)

	# Species 1 – single chemosynthetic cell (can move + rotate)
	var luca_cells_2 := {Vector2i(0, 0): "chemosynthetic"}
	species_id_to_object[1] = Species.new(1, luca_cells_2, randi() % 10, true, true)

func reset():
	species_id_to_object.clear()
	lifeform_id_to_object.clear()
	next_id = 0
	_init_grid()
	_create_initial_species()

	place_random_lifeform(0, 600)
	place_random_lifeform(1, 600)

	# Dead matter patches
	for _i in range(5):
		var w_patch = randi_range(10, 30)
		var h_patch = randi_range(10, 30)
		var x_start = randi_range(0, WIDTH - w_patch)
		var y_start = randi_range(0, HEIGHT - h_patch)
		for x in range(x_start, x_start + w_patch):
			for y in range(y_start, y_start + h_patch):
				if grid[x][y].lifeform_id == null:
					grid[x][y].particle = "dead"

# ==================== HELPERS ====================
func get_scalar(quad: int) -> Vector2:
	match quad:
		1: return Vector2(1, 1)
		2: return Vector2(1, -1)
		3: return Vector2(-1, -1)
		4: return Vector2(-1, 1)
	return Vector2(1, 1)

func get_new_rotation(current: int, action: String) -> int:
	var idx = current - 1
	var delta := 0
	match action:
		"rotate_right": delta = 1
		"rotate_left":  delta = -1
		"rotate_180":   delta = 2
	return ((idx + delta) % 4) + 1

func check_valid_configuration(lifeform: Lifeform, species: Species,
		test_x = null, test_y = null, test_rot = null,
		skip_positions: Dictionary = {}) -> bool:

	var tx = lifeform.x if test_x == null else test_x
	var ty = lifeform.y if test_y == null else test_y
	var tr = lifeform.rotation if test_rot == null else test_rot

	var scalar = get_scalar(tr)
	var proposed: Dictionary = {}
	var cell_count = species.cells.size()

	for local_pos in species.cells:
		var lx = local_pos.x
		var ly = local_pos.y
		var gx = tx + lx * scalar.x
		var gy = ty + ly * scalar.y
		var gpos = Vector2i(int(gx), int(gy))
		if gx < 0 or gx >= WIDTH or gy < 0 or gy >= HEIGHT:
			return false
		proposed[gpos] = true

	if proposed.size() < cell_count:
		return false

	# Build current positions if needed
	if skip_positions.is_empty():
		var current_scalar = get_scalar(lifeform.rotation)
		for local_pos in species.cells:
			var lx = local_pos.x
			var ly = local_pos.y
			var gx = lifeform.x + lx * current_scalar.x
			var gy = lifeform.y + ly * current_scalar.y
			skip_positions[Vector2i(int(gx), int(gy))] = true

	for gpos in proposed:
		if not skip_positions.has(gpos):
			var tile: Tile = grid[gpos.x][gpos.y]
			if tile.lifeform_id != null or tile.particle != "none":
				return false
	return true

func clear_occupation(lifeform: Lifeform, species: Species):
	var scalar = get_scalar(lifeform.rotation)
	for local_pos in species.cells:
		var gx = lifeform.x + local_pos.x * scalar.x
		var gy = lifeform.y + local_pos.y * scalar.y
		var gpos = Vector2i(int(gx), int(gy))
		if gpos.x >= 0 and gpos.x < WIDTH and gpos.y >= 0 and gpos.y < HEIGHT:
			var t: Tile = grid[gpos.x][gpos.y]
			t.lifeform_id = null
			t.species_id = null
			t.cell_type = null
			t.integer = null

func occupy(lifeform: Lifeform, species: Species):
	var scalar = get_scalar(lifeform.rotation)
	for local_pos in species.cells:
		var cell_type = species.cells[local_pos]
		var gx = lifeform.x + local_pos.x * scalar.x
		var gy = lifeform.y + local_pos.y * scalar.y
		var gpos = Vector2i(int(gx), int(gy))
		if gpos.x >= 0 and gpos.x < WIDTH and gpos.y >= 0 and gpos.y < HEIGHT:
			var t: Tile = grid[gpos.x][gpos.y]
			t.lifeform_id = lifeform.lifeform_id
			t.species_id = lifeform.species_id
			t.cell_type = cell_type
			t.integer = species.integer

func die(lifeform: Lifeform, species: Species):
	clear_occupation(lifeform, species)
	var scalar = get_scalar(lifeform.rotation)
	for local_pos in species.cells:
		var cell_type = species.cells[local_pos]
		var gx = lifeform.x + local_pos.x * scalar.x
		var gy = lifeform.y + local_pos.y * scalar.y
		var gpos = Vector2i(int(gx), int(gy))
		if gpos.x >= 0 and gpos.x < WIDTH and gpos.y >= 0 and gpos.y < HEIGHT:
			var t: Tile = grid[gpos.x][gpos.y]
			match cell_type:
				"photosynthetic", "chemosynthetic", "attack", "gene_replacement", "photoreceptor":
					t.particle = "dead"
				"empty":
					t.particle = "dead_empty"
				"hard_empty":
					t.particle = "dead_hard_empty"

# ==================== MUTATION ====================
func mutate(lifeform: Lifeform) -> int:
	var species: Species = species_id_to_object[lifeform.child_id]
	var new_cells = species.cells.duplicate()
	var can_move = species.can_move
	var can_rotate = species.can_rotate

	# Flip movement / rotation ability
	if randf() < MUTATION_RATE_BRAIN_FLIP:
		can_move = not can_move
	if randf() < MUTATION_RATE_BRAIN_FLIP:
		can_rotate = not can_rotate

	# Add cell
	if randf() < MUTATION_RATE_CELL_ADD:
		for _a in range(MUTATION_MAX_ATTEMPTS):
			var pos = Vector2i(randi_range(-MAX_EXTENSION, MAX_EXTENSION),
							   randi_range(-MAX_EXTENSION, MAX_EXTENSION))
			if not new_cells.has(pos):
				var types = ["photosynthetic", "chemosynthetic", "empty", "hard_empty",
							 "attack", "gene_replacement", "photoreceptor"]
				new_cells[pos] = types[randi() % types.size()]
				break

	# Remove cell
	if randf() < MUTATION_RATE_CELL_REMOVE and new_cells.size() > 1:
		var keys = new_cells.keys()
		new_cells.erase(keys[randi() % keys.size()])

	# Integer mutation
	var new_int = species.integer
	if randf() < MUTATION_RATE_INT:
		new_int = randi() % 10

	# Photosynthetic organisms lose movement/rotation
	for ct in new_cells.values():
		if ct == "photosynthetic":
			can_move = false
			can_rotate = false
			break

	var new_id = species_id_to_object.size()
	var new_species = Species.new(new_id, new_cells, new_int, can_move, can_rotate)
	species_id_to_object[new_id] = new_species
	return new_id

# ==================== CELL FUNCTIONS ====================
func cell_functionality(cell: String, lifeform: Lifeform, gpos: Vector2i):
	match cell:
		"photosynthetic":
			lifeform.fat += DEFAULT_SUNLIGHT * PHOTOSYNTHETIC_RATE
		"chemosynthetic":
			var dirs = [Vector2i(0,1), Vector2i(1,0), Vector2i(0,-1), Vector2i(-1,0)]
			for d in dirs:
				var nx = gpos.x + d.x
				var ny = gpos.y + d.y
				if nx >= 0 and nx < WIDTH and ny >= 0 and ny < HEIGHT:
					var n_particle = grid[nx][ny].particle
					match n_particle:
						"dead":
							lifeform.fat += CHEMO_DEAD_GAIN
							grid[nx][ny].particle = "none"
						"dead_empty":
							lifeform.fat += CHEMO_EMPTY_GAIN
							grid[nx][ny].particle = "none"
						"dead_hard_empty":
							lifeform.fat -= CHEMO_HARD_COST
							grid[nx][ny].particle = "none"
		"gene_replacement":
			var dirs = [Vector2i(0,1), Vector2i(1,0), Vector2i(0,-1), Vector2i(-1,0)]
			for d in dirs:
				var nx = gpos.x + d.x
				var ny = gpos.y + d.y
				if nx >= 0 and nx < WIDTH and ny >= 0 and ny < HEIGHT:
					var n_tile: Tile = grid[nx][ny]
					if n_tile.lifeform_id != null and n_tile.lifeform_id != lifeform.lifeform_id \
							and n_tile.cell_type != "attack" and n_tile.cell_type != "empty" \
							and n_tile.cell_type != "hard_empty":
						var other: Lifeform = lifeform_id_to_object[n_tile.lifeform_id]
						var my_int = species_id_to_object[lifeform.species_id].integer
						if other.species_id % 10 == my_int:
							other.child_id = lifeform.child_id

func attack_functionality(cell: String, lifeform: Lifeform, gpos: Vector2i):
	if cell != "attack":
		return
	var dirs = [Vector2i(0,1), Vector2i(1,0), Vector2i(0,-1), Vector2i(-1,0)]
	for d in dirs:
		var nx = gpos.x + d.x
		var ny = gpos.y + d.y
		if nx >= 0 and nx < WIDTH and ny >= 0 and ny < HEIGHT:
			var n_tile: Tile = grid[nx][ny]
			if n_tile.lifeform_id != null and n_tile.lifeform_id != lifeform.lifeform_id \
					and n_tile.cell_type != "empty" and n_tile.cell_type != "hard_empty":
				var other: Lifeform = lifeform_id_to_object[n_tile.lifeform_id]
				other.damage += ATTACK_DAMAGE
				other.was_attacked_this_turn = true

# ==================== ACTIONS (RANDOM) ====================
func random_decision(species: Species) -> String:
	var options: Array[String] = []
	if species.can_move:
		options.append_array(["move_forward", "move_backward", "move_right", "move_left", "move_none"])
	if species.can_rotate:
		options.append_array(["rotate_right", "rotate_left", "rotate_180", "rotate_none"])
	if options.is_empty():
		return "move_none"
	return options[randi() % options.size()]

func act_lifeform(lifeform: Lifeform, decision: String, species: Species):
	if decision in ["move_none", "rotate_none"]:
		return

	if decision.begins_with("move_"):
		var dx := 0
		var dy := 0
		match decision:
			"move_forward":  dy = -1
			"move_backward": dy = 1
			"move_right":    dx = 1
			"move_left":     dx = -1
		var rot = get_scalar(lifeform.rotation)
		var new_x = lifeform.x + dx * rot.x
		var new_y = lifeform.y + dy * rot.y
		if check_valid_configuration(lifeform, species, new_x, new_y):
			clear_occupation(lifeform, species)
			lifeform.x = int(new_x)
			lifeform.y = int(new_y)
			occupy(lifeform, species)

	elif decision.begins_with("rotate_"):
		var new_rot = get_new_rotation(lifeform.rotation, decision)
		if new_rot != lifeform.rotation and check_valid_configuration(lifeform, species, null, null, new_rot):
			clear_occupation(lifeform, species)
			lifeform.rotation = new_rot
			occupy(lifeform, species)

# ==================== PLACEMENT ====================
func place_random_lifeform(species_id: int, num: int):
	var species: Species = species_id_to_object[species_id]
	var placed := 0
	while placed < num:
		var attempts := 0
		while attempts < 200:
			var x = randf() * WIDTH
			var y = randf() * HEIGHT
			var rot = randi_range(1, 4)
			var temp = Lifeform.new(next_id, species_id, rot, x, y)
			if check_valid_configuration(temp, species, x, y, rot, {}):
				var lf = Lifeform.new(next_id, species_id, rot, x, y)
				lifeform_id_to_object[next_id] = lf
				occupy(lf, species)
				next_id += 1
				placed += 1
				break
			attempts += 1
		if attempts >= 200:
			print("Failed to place remaining of species ", species_id)
			break

# ==================== MAIN LOOP ====================
func _simulation_step():
	var to_remove: Array = []

	for lf_id in lifeform_id_to_object.keys():
		var lifeform: Lifeform = lifeform_id_to_object[lf_id]
		lifeform.was_attacked_this_turn = false
		var species: Species = species_id_to_object[lifeform.species_id]

		lifeform.age += 1

		# Cell functionality
		var scalar = get_scalar(lifeform.rotation)
		for local_pos in species.cells:
			var cell = species.cells[local_pos]
			var gx = lifeform.x + local_pos.x * scalar.x
			var gy = lifeform.y + local_pos.y * scalar.y
			var gpos = Vector2i(int(gx), int(gy))
			if gpos.x >= 0 and gpos.x < WIDTH and gpos.y >= 0 and gpos.y < HEIGHT:
				cell_functionality(cell, lifeform, gpos)
				attack_functionality(cell, lifeform, gpos)

		# Death
		var num_cells = species.cells.size()
		if lifeform.fat < 0 or lifeform.damage >= num_cells or lifeform.age >= MAX_AGE:
			to_remove.append(lf_id)
			die(lifeform, species)
			continue

		# Reproduce
		if lifeform.fat >= num_cells:
			var child_species_id = mutate(lifeform) if randf() < REPRO_MUTATION_PROB else lifeform.species_id
			var dx = randi_range(-10, 10)
			var dy = randi_range(-10, 10)
			var child_x = lifeform.x + dx
			var child_y = lifeform.y + dy
			var child_species: Species = species_id_to_object[child_species_id]
			var temp_child = Lifeform.new(next_id, child_species_id, lifeform.rotation, child_x, child_y)
			if check_valid_configuration(temp_child, child_species, null, null, null, {}):
				var child = Lifeform.new(next_id, child_species_id, lifeform.rotation, child_x, child_y)
				lifeform_id_to_object[next_id] = child
				occupy(child, child_species)
				next_id += 1
				var repro_cost = num_cells
				if child_species.can_move:
					repro_cost += MOVE_REPRO_COST
				if child_species.can_rotate:
					repro_cost += ROTATE_REPRO_COST
				lifeform.fat -= repro_cost

		# Random decision + act
		var decision = random_decision(species)
		act_lifeform(lifeform, decision, species)

	for id in to_remove:
		lifeform_id_to_object.erase(id)

# ==================== DRAWING ====================
func _draw_frame():
	# Background particles
	for x in range(WIDTH):
		for y in range(HEIGHT):
			var p = grid[x][y].particle
			image.set_pixel(x, y, particle_colors.get(p, Color.GRAY))

	# Lifeforms on top
	for lifeform in lifeform_id_to_object.values():
		var species: Species = species_id_to_object[lifeform.species_id]
		var scalar = get_scalar(lifeform.rotation)
		for local_pos in species.cells:
			var cell_type = species.cells[local_pos]
			var ax = int(lifeform.x + local_pos.x * scalar.x)
			var ay = int(lifeform.y + local_pos.y * scalar.y)
			if ax >= 0 and ax < WIDTH and ay >= 0 and ay < HEIGHT:
				image.set_pixel(ax, ay, cell_colors.get(cell_type, Color.WHITE))

	texture.update(image)
