extends Area3D
## A collectible crystal. Touching it with the player body marks it collected,
## hides it, stops monitoring and emits `collected` exactly once.

signal collected(crystal)

var is_collected := false

func _ready() -> void:
    add_to_group("crystal")
    body_entered.connect(_on_body_entered)

func _process(delta: float) -> void:
    if not is_collected:
        $Mesh.rotate_y(delta * 1.4)

func _on_body_entered(body: Node3D) -> void:
    if is_collected:
        return
    if not body.is_in_group("player"):
        return
    is_collected = true
    set_deferred("monitoring", false)
    visible = false
    collected.emit(self)
