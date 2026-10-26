extends Node3D
## Render-only showroom for the Wayfarer hero. Cycles idle -> run -> reach while
## orbiting the camera, so the windowed movie capture can prove scale, orientation
## and that the imported animations actually deform the mesh.
##
## Run interactively:  godot --path game res://scenes/hero_preview.tscn
## Capture:            godot --path game --write-movie out.avi --fixed-fps 30 res://scenes/hero_preview.tscn -- --capture

@export var capture_seconds := 8.0
@export var swing_speed := 0.7
@export var swing_amount := 0.32

var _elapsed := 0.0
var _clip := ""
var _capture := false

@onready var hero: Node3D = $Hero
@onready var camera: Camera3D = $Camera3D

func _ready() -> void:
    _capture = "--capture" in OS.get_cmdline_user_args()
    var animation := hero.find_child("AnimationPlayer", true, false) as AnimationPlayer
    if animation == null:
        push_warning("HeroPreview: no AnimationPlayer found in the hero GLB")
        return
    for name in animation.get_animation_list():
        var lower := String(name).to_lower()
        if lower == "idle" or lower == "run":
            animation.get_animation(name).loop_mode = Animation.LOOP_LINEAR
    print("HERO_PREVIEW anims=" + str(animation.get_animation_list()) + " capture=" + str(_capture))
    _play("idle")

func _process(delta: float) -> void:
    _elapsed += delta
    var angle := PI + 0.42 + sin(_elapsed * swing_speed) * swing_amount
    camera.position = Vector3(sin(angle) * 3.15, 1.55, cos(angle) * 3.15)
    camera.look_at(Vector3(0.0, 1.0, 0.0), Vector3.UP)
    if _elapsed < 2.5:
        _play("idle")
    elif _elapsed < 5.2:
        _play("run")
    elif _elapsed < 7.4:
        _play("reach")
    else:
        _play("idle")
    if _capture and _elapsed >= capture_seconds:
        get_tree().quit(0)

func _play(wanted: String) -> void:
    if _clip == wanted:
        return
    var animation := hero.find_child("AnimationPlayer", true, false) as AnimationPlayer
    if animation == null:
        return
    for name in animation.get_animation_list():
        var lower := String(name).to_lower()
        if lower == wanted or lower.ends_with("|" + wanted):
            _clip = wanted
            animation.play(String(name), 0.2)
            print("HERO_PREVIEW clip=" + wanted)
            return
