import pygame
import random
import numpy as np
import copy
import torch
import torch.nn as nn

# Configuration
WIDTH = 150
HEIGHT = 185
MAX_EXTENSION = 5
MAX_AGE = 75
FPS = 120
DEFAULT_SUNLIGHT = 0.50
PHOTOSYNTHETIC_RATE = 0.05
CHEMO_DEAD_GAIN = 0.9
CHEMO_EMPTY_GAIN = 0
CHEMO_HARD_COST = 1
ATTACK_DAMAGE = 1
MUTATION_RATE_CELL_ADD = 0.1
MUTATION_RATE_CELL_REMOVE = 0.05
MUTATION_RATE_BRAIN_FLIP = 0.05
MUTATION_RATE_INT = 0.05
MUTATION_RATE_WEIGHT = 0.1
MUTATION_MAX_ATTEMPTS = 100
MOVE_REPRO_COST = 1
ROTATE_REPRO_COST = 1
REPRO_MUTATION_PROB = 0.3
INITIAL_MOVEMENT = True
INITIAL_ROTATION = True
HIDDEN_SIZE = 30
MAX_PHOTO = 10
INPUT_SIZE = 3 + MAX_PHOTO * 4 * 2

class Tile:
    def __init__(self, particle, species_id, lifeform_id, cell_type, integer):
        self.particle = particle
        self.species_id = species_id
        self.lifeform_id = lifeform_id
        self.cell_type = cell_type
        self.integer = integer

class Species:
    def __init__(self, species_id, cells, integer, rotation, brain):
        self.species_id = species_id
        self.cells = cells
        self.integer = integer
        self.rotation = rotation
        self.brain = brain

class Lifeform:
    def __init__(self, id, species_id, rotation, brain, x, y):
        self.lifeform_id = id
        self.species_id = species_id
        self.child_id = species_id
        self.rotation = rotation
        self.brain = brain
        self.fat = 0.0
        self.x = x
        self.y = y
        self.damage = 0
        self.age = 0
        self.was_attacked_this_turn = False
        self.hidden = None
        self.cell = None

class Brain:
    def __init__(self, movement, rotation):
        self.movement = movement
        self.rotation = rotation
        self.lstm = nn.LSTM(INPUT_SIZE, HIDDEN_SIZE, num_layers=1, batch_first=True)
        self.update_outputs()
        self.action_to_idx = {act: i for i, act in enumerate(self.outputs)}

    def make_outputs(self):
        outputs = []
        if self.movement:
            outputs.extend(["move_forward", "move_backward", "move_right", "move_left", "move_none"])
        if self.rotation:
            outputs.extend(["rotate_right", "rotate_left", "rotate_180", "rotate_none"])
        return outputs

    def update_outputs(self):
        self.outputs = self.make_outputs()
        self.fc = nn.Linear(HIDDEN_SIZE, len(self.outputs))

    def decide(self, lifeform, sensor_inputs):
        if not self.outputs:
            return "move_none"
        x = torch.tensor(sensor_inputs).unsqueeze(0).unsqueeze(0).float()
        h0 = torch.zeros(1, 1, HIDDEN_SIZE).float()
        c0 = torch.zeros(1, 1, HIDDEN_SIZE).float()
        if lifeform.hidden is not None:
            h0 = lifeform.hidden
            c0 = lifeform.cell
        with torch.no_grad():
            out, (hn, cn) = self.lstm(x, (h0, c0))
            logits = self.fc(out[0, 0])
            probs = torch.softmax(logits, dim=0)
            action_idx = torch.multinomial(probs, num_samples=1).item()
        lifeform.hidden = hn
        lifeform.cell = cn
        return self.outputs[action_idx]

def get_sensor_inputs(lifeform):
    species = species_id_to_object[lifeform.species_id]
    pr_positions = [pos for pos, ctype in species.cells.items() if ctype == "photoreceptor"]
    num_pr = len(pr_positions)
    inputs = []
    inputs.append(DEFAULT_SUNLIGHT)
    inputs.append(lifeform.fat / 50.0)
    inputs.append(1.0 if lifeform.was_attacked_this_turn else 0.0)
    directions = [(0,1), (1,0), (0,-1), (-1,0)]
    particle_map_id = {"none":0, "dead":1, "dead_empty":2, "dead_hard_empty":3}
    cell_types_list = ["none", "photosynthetic", "chemosynthetic", "empty", "hard_empty", "attack", "gene_replacement", "photoreceptor"]
    scalar = get_scalar(lifeform.rotation)
    for i in range(min(num_pr, MAX_PHOTO)):
        lx, ly = pr_positions[i]
        rx = lx * scalar[0]
        ry = ly * scalar[1]
        pr_gx = int(lifeform.x + rx)
        pr_gy = int(lifeform.y + ry)
        if not (0 <= pr_gx < WIDTH and 0 <= pr_gy < HEIGHT):
            for _ in range(4 * 2):
                inputs.append(0.0)
            continue
        for dx, dy in directions:
            seen_particle_id = 0
            seen_cell_id = 0
            for dist in range(1, 11):
                nx = pr_gx + dx * dist
                ny = pr_gy + dy * dist
                if not (0 <= nx < WIDTH and 0 <= ny < HEIGHT):
                    break
                tile = grid[nx][ny]
                hit = False
                if tile.lifeform_id is not None:
                    seen_cell_id = cell_types_list.index(tile.cell_type)
                    hit = True
                elif tile.particle != "none":
                    seen_particle_id = particle_map_id[tile.particle]
                    hit = True
                if hit:
                    break
            inputs.append(seen_particle_id / 3.0)
            inputs.append(seen_cell_id / 7.0)
    while len(inputs) < INPUT_SIZE:
        inputs.append(0.0)
    return np.array(inputs[:INPUT_SIZE])

def get_scalar(quad):
    if quad == 1:
        return (1, 1)
    elif quad == 2:
        return (1, -1)
    elif quad == 3:
        return (-1, -1)
    elif quad == 4:
        return (-1, 1)

def get_new_rotation(current, action):
    idx = current - 1
    if action == "rotate_right":
        delta = 1
    elif action == "rotate_left":
        delta = -1
    elif action == "rotate_180":
        delta = 2
    else:
        delta = 0
    new_idx = (idx + delta) % 4
    return new_idx + 1

def check_valid_configuration(lifeform, species, test_x=None, test_y=None, test_rot=None, skip_positions=None):
    if test_x is None:
        test_x = lifeform.x
    if test_y is None:
        test_y = lifeform.y
    if test_rot is None:
        test_rot = lifeform.rotation

    scalar = get_scalar(test_rot)
    proposed_pos = set()
    cell_count = len(species.cells)
    for lx, ly in species.cells.keys():
        rx = lx * scalar[0]
        ry = ly * scalar[1]
        gx = test_x + rx
        gy = test_y + ry
        gpos = (int(gx), int(gy))
        if not (0 <= gx < WIDTH and 0 <= gy < HEIGHT):
            return False
        proposed_pos.add(gpos)

    if len(proposed_pos) < cell_count:
        return False

    if skip_positions is None:
        current_scalar = get_scalar(lifeform.rotation)
        current_pos = set()
        for lx, ly in species.cells.keys():
            rx = lx * current_scalar[0]
            ry = ly * current_scalar[1]
            gx = lifeform.x + rx
            gy = lifeform.y + ry
            gpos = (int(gx), int(gy))
            current_pos.add(gpos)
        skip_positions = current_pos

    blocked = False
    for gpos in proposed_pos:
        if gpos not in skip_positions:
            x, y = gpos
            occupied = grid[x][y].lifeform_id is not None
            has_particle = grid[x][y].particle != "none"
            if occupied or has_particle:
                blocked = True
    if blocked:
        return False
    return True

def clear_occupation(lifeform, species):
    scalar = get_scalar(lifeform.rotation)
    for local_pos in species.cells:
        lx, ly = local_pos
        rx = lx * scalar[0]
        ry = ly * scalar[1]
        gx = lifeform.x + rx
        gy = lifeform.y + ry
        gpos = (int(gx), int(gy))
        if 0 <= gpos[0] < WIDTH and 0 <= gpos[1] < HEIGHT:
            x, y = gpos
            grid[x][y].lifeform_id = None
            grid[x][y].species_id = None
            grid[x][y].cell_type = None
            grid[x][y].integer = None

def occupy(lifeform, species):
    scalar = get_scalar(lifeform.rotation)
    for local_pos, cell_type in species.cells.items():
        lx, ly = local_pos
        rx = lx * scalar[0]
        ry = ly * scalar[1]
        gx = lifeform.x + rx
        gy = lifeform.y + ry
        gpos = (int(gx), int(gy))
        if 0 <= gpos[0] < WIDTH and 0 <= gpos[1] < HEIGHT:
            x, y = gpos
            grid[x][y].lifeform_id = lifeform.lifeform_id
            grid[x][y].species_id = lifeform.species_id
            grid[x][y].cell_type = cell_type
            grid[x][y].integer = species.integer

def die(lifeform, species):
    clear_occupation(lifeform, species)
    scalar = get_scalar(lifeform.rotation)
    for local_pos, cell_type in species.cells.items():
        lx, ly = local_pos
        rx = lx * scalar[0]
        ry = ly * scalar[1]
        gx = lifeform.x + rx
        gy = lifeform.y + ry
        gpos = (int(gx), int(gy))
        if 0 <= gpos[0] < WIDTH and 0 <= gpos[1] < HEIGHT:
            x, y = gpos
            if cell_type in ["photosynthetic", "chemosynthetic", "attack", "gene_replacement", "photoreceptor"]:
                grid[x][y].particle = "dead"
            elif cell_type == "empty":
                grid[x][y].particle = "dead_empty"
            elif cell_type == "hard_empty":
                grid[x][y].particle = "dead_hard_empty"

def mutate(lifeform):
    species = species_id_to_object[lifeform.child_id]
    new_cells = species.cells.copy()
    new_brain = copy.deepcopy(species.brain)
    if random.random() < MUTATION_RATE_BRAIN_FLIP:
        new_brain.movement = not new_brain.movement
        new_brain.update_outputs()
    if random.random() < MUTATION_RATE_BRAIN_FLIP:
        new_brain.rotation = not new_brain.rotation
        new_brain.update_outputs()
    if random.random() < MUTATION_RATE_WEIGHT:
        mutation_strength = 0.05
        for param in new_brain.lstm.parameters():
            param.data += torch.randn_like(param.data) * mutation_strength
        for param in new_brain.fc.parameters():
            param.data += torch.randn_like(param.data) * mutation_strength
    new_species = Species(len(species_id_to_object), new_cells, species.integer, species.rotation, new_brain)
    species_id_to_object[new_species.species_id] = new_species
    if random.random() < MUTATION_RATE_CELL_ADD:
        attempts = 0
        while attempts < MUTATION_MAX_ATTEMPTS:
            pos = (random.randint(-MAX_EXTENSION, MAX_EXTENSION), random.randint(-MAX_EXTENSION, MAX_EXTENSION))
            if pos not in new_cells:
                cell_type = random.choice(["photosynthetic", "chemosynthetic", "empty", "hard_empty", "attack", "gene_replacement", "photoreceptor"])
                new_cells[pos] = cell_type
                break
            attempts += 1
    if random.random() < MUTATION_RATE_CELL_REMOVE and len(new_cells) > 1:
        pos_to_remove = random.choice(list(new_cells.keys()))
        del new_cells[pos_to_remove]
    if random.random() < MUTATION_RATE_INT:
        new_species.integer = random.randint(0, 9)
    for cell_type in list(new_species.cells.values()):
        if cell_type == "photosynthetic":
            new_species.brain.movement = False
            new_species.brain.rotation = False
            new_brain.update_outputs()
    return new_species.species_id

def cell_functionality(cell, lifeform, gpos):
    x, y = gpos
    if cell == "photosynthetic":
        lifeform.fat += DEFAULT_SUNLIGHT * PHOTOSYNTHETIC_RATE
    elif cell == "chemosynthetic":
        directions = [(0,1),(1,0),(0,-1),(-1,0)]
        for dx, dy in directions:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                n_particle = grid[nx][ny].particle
                if n_particle == "dead":
                    lifeform.fat += CHEMO_DEAD_GAIN
                    grid[nx][ny].particle = "none"
                elif n_particle == "dead_empty":
                    lifeform.fat += CHEMO_EMPTY_GAIN
                    grid[nx][ny].particle = "none"
                elif n_particle == "dead_hard_empty":
                    lifeform.fat -= CHEMO_HARD_COST
                    grid[nx][ny].particle = "none"
    elif cell == "gene_replacement":
        directions = [(0,1),(1,0),(0,-1),(-1,0)]
        for dx, dy in directions:
            nx = x + dx
            ny = y + dy
            if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
                n_tile = grid[nx][ny]
                if n_tile.lifeform_id is not None and n_tile.lifeform_id != lifeform.lifeform_id and n_tile.cell_type != "attack" and n_tile.cell_type != "empty" and n_tile.cell_type != "hard_empty":
                    other_lf = lifeform_id_to_object[n_tile.lifeform_id]
                    if other_lf.species_id % 10 == species_id_to_object[lifeform.species_id].integer:
                        other_lf.child_id = lifeform.child_id

def attack_functionality(cell, lifeform, gpos):
    if cell != "attack":
        return
    x, y = gpos
    directions = [(0,1),(1,0),(0,-1),(-1,0)]
    for dx, dy in directions:
        nx = x + dx
        ny = y + dy
        if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
            n_tile = grid[nx][ny]
            if n_tile.lifeform_id is not None and n_tile.lifeform_id != lifeform.lifeform_id and n_tile.cell_type != "empty" and n_tile.cell_type != "hard_empty":
                other_lf = lifeform_id_to_object[n_tile.lifeform_id]
                other_lf.damage += ATTACK_DAMAGE
                other_lf.was_attacked_this_turn = True

def act_lifeform(lifeform, decision, species):
    if decision in ["move_none", "rotate_none"]:
        return

    if decision.startswith("move_"):
        dx, dy = 0, 0
        if decision == "move_forward":
            dx, dy = 0, -1
        elif decision == "move_backward":
            dx, dy = 0, 1
        elif decision == "move_right":
            dx, dy = 1, 0
        elif decision == "move_left":
            dx, dy = -1, 0
        rot = get_scalar(lifeform.rotation)
        new_x = lifeform.x + dx * rot[0]
        new_y = lifeform.y + dy * rot[1]
        if check_valid_configuration(lifeform, species, test_x=new_x, test_y=new_y):
            clear_occupation(lifeform, species)
            lifeform.x = int(new_x)
            lifeform.y = int(new_y)
            occupy(lifeform, species)
    elif decision.startswith("rotate_"):
        new_rot = get_new_rotation(lifeform.rotation, decision)
        if new_rot != lifeform.rotation and check_valid_configuration(lifeform, species, test_rot=new_rot):
            clear_occupation(lifeform, species)
            lifeform.rotation = new_rot
            occupy(lifeform, species)

species_id_to_object = {}
lifeform_id_to_object = {}

luca_cells = {(0, 0): "photosynthetic", (1, 0): "photosynthetic", (-1, 0): "photosynthetic", (0, 1): "photosynthetic", (0, -1): "photosynthetic", (1, 1): "photosynthetic", (-1, -1): "photosynthetic"}
luca_species = Species(0, luca_cells, random.randint(0,9), None, Brain(False, False))
species_id_to_object[0] = luca_species

luca_cells_2 = {(0, 0): "chemosynthetic"}
luca_species_2 = Species(1, luca_cells_2, random.randint(0,9), None, Brain(True, True))
species_id_to_object[1] = luca_species_2

grid = [[Tile("none", None, None, None, None) for _ in range(HEIGHT)] for _ in range(WIDTH)]

next_id = 0

def place_random_lifeform(species_id, num):
    global next_id
    species = species_id_to_object[species_id]
    placed = 0
    while placed < num:
        attempts = 0
        while attempts < 200:
            x = random.uniform(0, WIDTH)
            y = random.uniform(0, HEIGHT)
            rot = random.randint(1, 4)
            temp_lf = Lifeform(next_id, species_id, rot, species.brain, x, y)
            if check_valid_configuration(temp_lf, species, test_x=x, test_y=y, test_rot=rot, skip_positions=set()):
                lifeform = Lifeform(next_id, species_id, rot, species.brain, x, y)
                lifeform_id_to_object[next_id] = lifeform
                occupy(lifeform, species)
                next_id += 1
                placed += 1
                break
            attempts += 1
        if attempts >= 200:
            print(f"Failed to place {num - placed} more of species {species_id}")
            break

def reset():
    global grid, next_id
    luca_cells = {(0, 0): "photosynthetic", (1, 0): "photosynthetic", (-1, 0): "photosynthetic", (0, 1): "photosynthetic", (0, -1): "photosynthetic", (1, 1): "photosynthetic", (-1, -1): "photosynthetic"}
    luca_species = Species(0, luca_cells, random.randint(0,9), None, Brain(False, False))
    species_id_to_object[0] = luca_species

    luca_cells_2 = {(0, 0): "chemosynthetic"}
    luca_species_2 = Species(1, luca_cells_2, random.randint(0,9), None, Brain(True, True))
    species_id_to_object[1] = luca_species_2

    next_id = 0
    lifeform_id_to_object.clear()

    grid = [[Tile("none", None, None, None, None) for _ in range(HEIGHT)] for _ in range(WIDTH)]

    place_random_lifeform(0, 200)
    place_random_lifeform(1, 200)
    
    num_patches = 5
    for _ in range(num_patches):
        w_patch = random.randint(10, 30)
        h_patch = random.randint(10, 30)
        x_start = random.randint(0, WIDTH - w_patch)
        y_start = random.randint(0, HEIGHT - h_patch)
        for x in range(x_start, x_start + w_patch):
            for y in range(y_start, y_start + h_patch):
                if grid[x][y].lifeform_id is None:
                    grid[x][y].particle = "dead"

reset()

num_patches = 5
for _ in range(num_patches):
    w_patch = random.randint(10, 30)
    h_patch = random.randint(10, 30)
    x_start = random.randint(0, WIDTH - w_patch)
    y_start = random.randint(0, HEIGHT - h_patch)
    for x in range(x_start, x_start + w_patch):
        for y in range(y_start, y_start + h_patch):
            if grid[x][y].lifeform_id is None:
                grid[x][y].particle = "dead"

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("pitri.py")
clock = pygame.time.Clock()
running = True

# Precompute color maps
particle_map = {
    "none": np.array([76, 76, 76], dtype=np.uint8),
    "dead": np.array([100, 100, 100], dtype=np.uint8),
    "dead_empty": np.array([50, 50, 50], dtype=np.uint8),
    "dead_hard_empty": np.array([66, 62, 57], dtype=np.uint8)
}
cell_map = {
    "photosynthetic": np.array([149, 217, 148], dtype=np.uint8),
    "chemosynthetic": np.array([201, 152, 149], dtype=np.uint8),
    "empty": np.array([150, 140, 100], dtype=np.uint8),
    "hard_empty": np.array([180, 170, 130], dtype=np.uint8),
    "attack": np.array([217, 217, 130], dtype=np.uint8),
    "gene_replacement": np.array([212, 108, 137], dtype=np.uint8),
    "photoreceptor": np.array([100, 150, 200], dtype=np.uint8)
}

# Particle grid for fast drawing
particle_grid = np.zeros((WIDTH, HEIGHT), dtype=int)
particle_id_map = {"none": 0, "dead": 1, "dead_empty": 2, "dead_hard_empty": 3}
color_particle_map = np.array([particle_map[k] for k in particle_id_map])

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    if (len(lifeform_id_to_object) == 0):
        reset()

    # Update particle_grid
    for x in range(WIDTH):
        for y in range(HEIGHT):
            particle_grid[x, y] = particle_id_map.get(grid[x][y].particle, 0)

    # Update each lifeform
    to_remove = []
    for lf_id, lifeform in list(lifeform_id_to_object.items()):
        lifeform.was_attacked_this_turn = False
        species = species_id_to_object[lifeform.species_id]

        lifeform.age += 1

        # Update cells
        scalar = get_scalar(lifeform.rotation)
        for local_pos, cell in species.cells.items():
            lx, ly = local_pos
            rx = lx * scalar[0]
            ry = ly * scalar[1]
            gx = lifeform.x + rx
            gy = lifeform.y + ry
            gpos = (int(gx), int(gy))
            if 0 <= gpos[0] < WIDTH and 0 <= gpos[1] < HEIGHT:
                cell_functionality(cell, lifeform, gpos)
                attack_functionality(cell, lifeform, gpos)

        # Death check
        num_cells = len(species.cells)
        if lifeform.fat < 0 or lifeform.damage >= num_cells or lifeform.age >= MAX_AGE:
            to_remove.append(lf_id)
            die(lifeform, species)
            continue

        # Reproduce if fat enough
        if lifeform.fat >= num_cells:
            child_species_id = mutate(lifeform) if random.random() < REPRO_MUTATION_PROB else lifeform.species_id
            dx, dy = (random.randint(-10, 10), random.randint(-10, 10))
            child_x, child_y = lifeform.x + dx, lifeform.y + dy
            child_species = species_id_to_object[child_species_id]
            temp_child = Lifeform(next_id, child_species_id, lifeform.rotation, child_species.brain, child_x, child_y)
            if check_valid_configuration(temp_child, child_species, skip_positions=set()):
                child = Lifeform(next_id, child_species_id, lifeform.rotation, child_species.brain, child_x, child_y)
                child.hidden = None
                child.cell = None
                lifeform_id_to_object[next_id] = child
                occupy(child, child_species)
                next_id += 1
                repro_cost = num_cells + (MOVE_REPRO_COST if child_species.brain.movement else 0) + (ROTATE_REPRO_COST if child_species.brain.rotation else 0)
                lifeform.fat -= repro_cost

        # Brain decision
        ix = int(lifeform.x)
        iy = int(lifeform.y)
        if 0 <= ix < WIDTH and 0 <= iy < HEIGHT:
            sensor_inputs = get_sensor_inputs(lifeform)
            decision = lifeform.brain.decide(lifeform, sensor_inputs)
        else:
            decision = "move_none"
        act_lifeform(lifeform, decision, species)

    for lf_id in to_remove:
        del lifeform_id_to_object[lf_id]

    # Drawing with numpy
    color_grid = color_particle_map[particle_grid]

    for lifeform in lifeform_id_to_object.values():
        species = species_id_to_object[lifeform.species_id]
        scalar = get_scalar(lifeform.rotation)
        for local_pos, cell_type in species.cells.items():
            lx, ly = local_pos
            rx = lx * scalar[0]
            ry = ly * scalar[1]
            ax = int(lifeform.x + rx)
            ay = int(lifeform.y + ry)
            if 0 <= ax < WIDTH and 0 <= ay < HEIGHT:
                color_grid[ax, ay] = cell_map.get(cell_type, np.array([100, 100, 100], dtype=np.uint8))

    pygame.surfarray.blit_array(screen, color_grid)
    pygame.display.flip()

    print(len(lifeform_id_to_object))

    clock.tick(FPS)

pygame.quit()

"""
photosynthetic done
chemosynthetic done
dead done
hard_dead done
attack done
gene_replacement done
gene_combination 
photorecepter 

Possible:
photosynthecizer: makes photons
chemosynthecizer: makes chemicals
chemorecepter: detects chemicals
builder: makes blocks of stuff (for dens and making new organisms, like it will add to the nearest organism or make a new one)
breaker: breaks blocks of stuff
mover: moves the organism
"""