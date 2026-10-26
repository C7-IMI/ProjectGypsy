extends Camera3D
## Fixed-offset third-person camera that smoothly follows the player.

@export var target_path: NodePath
@export var follow_offset := Vector3(0.0, 4.2, 6.0)
@export var smoothing := 6.0

var target: Node3D

func _ready() -> void:
    target = get_node_or_null(target_path) as Node3D
    if target != null:
        global_position = target.global_position + follow_offset

func _physics_process(delta: float) -> void:
    if target == null:
        return
    var desired := target.global_position + follow_offset
    var weight := 1.0 - exp(-smoothing * delta)
    global_position = global_position.lerp(desired, weight)
    look_at(target.global_position + Vector3(0.0, 1.0, 0.0), Vector3.UP)
