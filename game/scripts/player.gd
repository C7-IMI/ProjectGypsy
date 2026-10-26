extends CharacterBody3D
## Player capsule: WASD movement, optional jump, simple gravity and floor reset.
## In demo mode the root scene sets `autopilot_enabled` and supplies a world-space
## direction each physics frame through `autopilot_direction`; the same
## CharacterBody3D movement code runs, so the demo exercises the real mechanic
## instead of teleporting the player.

@export var move_speed := 7.0
@export var acceleration := 35.0
@export var air_acceleration := 10.0
@export var jump_velocity := 7.0
@export var gravity := 20.0
@export var fall_reset_y := -10.0

var autopilot_enabled := false
var autopilot_direction := Vector3.ZERO
var spawn_position := Vector3.ZERO

func _ready() -> void:
    add_to_group("player")
    spawn_position = global_position

func _physics_process(delta: float) -> void:
    if not is_on_floor():
        velocity.y -= gravity * delta

    var direction := Vector3.ZERO
    if autopilot_enabled:
        direction = autopilot_direction
        velocity.x = direction.x * move_speed
        velocity.z = direction.z * move_speed
    else:
        var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
        direction = Vector3(input.x, 0.0, input.y).limit_length(1.0)
        var accel := acceleration if is_on_floor() else air_acceleration
        velocity.x = move_toward(velocity.x, direction.x * move_speed, accel * delta)
        velocity.z = move_toward(velocity.z, direction.z * move_speed, accel * delta)
        if is_on_floor() and Input.is_action_just_pressed("jump"):
            velocity.y = jump_velocity
        if direction.length_squared() > 0.0001:
            var target_yaw := atan2(-direction.x, -direction.z)
            rotation.y = lerp_angle(rotation.y, target_yaw, clampf(delta * 12.0, 0.0, 1.0))

    move_and_slide()

    if global_position.y < fall_reset_y:
        global_position = spawn_position
        velocity = Vector3.ZERO
