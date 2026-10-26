extends Node3D
## ProjectGypsy Phase-1 vertical slice root.
##
## Interactive mode: a human walks the capsule with WASD (+ Space to jump) and
## collects the three crystals. No HUD by design (interface design is parked, PG-D4).
##
## Demo mode (`-- --demo` after the engine args): a deterministic autopilot drives
## the same CharacterBody3D movement path, collects all three crystals inside a
## bounded number of physics frames, prints exactly one marker line and quits:
##   success -> "GYPSY_DEMO_OK collected=3 frames=<n>" and exit code 0
##   failure -> "GYPSY_DEMO_FAIL <reason>" and exit code 1
##
## Script-to-script access is dynamic (Object.set/get/connect) on purpose: the demo
## must work on a cold checkout where Godot has not yet built its script-class cache.

const DEMO_FLAG := "--demo"
const COLLECT_TARGET := 3
const MAX_DEMO_FRAMES := 900

@onready var player: Node = $Player

var demo_mode := false
var demo_frames := 0
var collected := 0
var finished := false

func _ready() -> void:
    _register_input_actions()
    demo_mode = _has_demo_flag()
    for node in get_tree().get_nodes_in_group("crystal"):
        node.connect("collected", Callable(self, "_on_crystal_collected"))
    player.set("autopilot_enabled", demo_mode)
    if not demo_mode:
        print("ProjectGypsy Phase-1 slice — WASD to move, Space to jump. Headless demo: '-- --demo'.")

func _has_demo_flag() -> bool:
    return DEMO_FLAG in OS.get_cmdline_user_args() or DEMO_FLAG in OS.get_cmdline_args()

func _register_input_actions() -> void:
    _add_action("move_forward", [KEY_W, KEY_UP])
    _add_action("move_back", [KEY_S, KEY_DOWN])
    _add_action("move_left", [KEY_A, KEY_LEFT])
    _add_action("move_right", [KEY_D, KEY_RIGHT])
    _add_action("jump", [KEY_SPACE])

func _add_action(action: StringName, keys: Array) -> void:
    if not InputMap.has_action(action):
        InputMap.add_action(action, 0.2)
    for key in keys:
        var event := InputEventKey.new()
        event.physical_keycode = key
        InputMap.action_add_event(action, event)

func _physics_process(_delta: float) -> void:
    if not demo_mode or finished:
        return
    demo_frames += 1
    if collected >= COLLECT_TARGET:
        _finish_ok()
        return
    if demo_frames > MAX_DEMO_FRAMES:
        _finish_fail("timeout collected=%d" % collected)
        return
    var target := _nearest_crystal()
    if target == null:
        _finish_fail("no remaining crystal with collected=%d" % collected)
        return
    var offset: Vector3 = target.global_position - (player as Node3D).global_position
    offset.y = 0.0
    var direction := offset.normalized() if offset.length_squared() > 0.0001 else Vector3.ZERO
    player.set("autopilot_direction", direction)

func _nearest_crystal() -> Node3D:
    var best: Node3D = null
    var best_distance := INF
    var player_position: Vector3 = (player as Node3D).global_position
    for node in get_tree().get_nodes_in_group("crystal"):
        if bool(node.get("is_collected")):
            continue
        var crystal := node as Node3D
        var distance := player_position.distance_squared_to(crystal.global_position)
        if distance < best_distance:
            best_distance = distance
            best = crystal
    return best

func _on_crystal_collected(_crystal: Node) -> void:
    collected += 1

func _finish_ok() -> void:
    if finished:
        return
    finished = true
    print("GYPSY_DEMO_OK collected=%d frames=%d" % [collected, demo_frames])
    get_tree().quit(0)

func _finish_fail(reason: String) -> void:
    if finished:
        return
    finished = true
    print("GYPSY_DEMO_FAIL %s" % reason)
    get_tree().quit(1)
