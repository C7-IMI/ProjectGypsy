extends Node3D
## Wayfarer hero visual: maps locomotion speed to the imported idle/run clips and
## plays the one-shot reach clip for crystal collection.
##
## The imported GLB root is instanced under Player at local y = -0.9. The
## CharacterBody3D collision, movement, autopilot and demo contract stay in
## player.gd/main.gd; this node is presentation only and never gates gameplay.
## Missing clips warn once at startup instead of breaking the demo.

@export var idle_clip := "idle"
@export var run_clip := "run"
@export var reach_clip := "reach"
@export var run_speed_threshold := 0.8

var _animation: AnimationPlayer
var _current := ""
var _reach_active := false
var _last_speed := 0.0
var _last_on_floor := true

func _ready() -> void:
    _animation = find_child("AnimationPlayer", true, false) as AnimationPlayer
    if _animation == null:
        push_warning("HeroVisual: no AnimationPlayer found in the Wayfarer GLB; hero stays in bind pose")
        return
    var clips := _animation.get_animation_list()
    var missing: Array[String] = []
    for wanted in [idle_clip, run_clip, reach_clip]:
        if _resolve(wanted) == "":
            missing.append(wanted)
    for loop_name in [idle_clip, run_clip]:
        var resolved := _resolve(loop_name)
        if resolved != "":
            _animation.get_animation(resolved).loop_mode = Animation.LOOP_LINEAR
    var reach_name := _resolve(reach_clip)
    if reach_name != "":
        _animation.get_animation(reach_name).loop_mode = Animation.LOOP_NONE
    _animation.animation_finished.connect(_on_animation_finished)
    print("HERO_VISUAL ready clips=" + str(clips) + " missing=" + str(missing))
    _play(idle_clip, 0.0)

func _resolve(wanted: String) -> String:
    if _animation == null:
        return ""
    for name in _animation.get_animation_list():
        var lower := String(name).to_lower()
        if lower == wanted or lower.ends_with("|" + wanted):
            return String(name)
    return ""

func _play(wanted: String, blend := 0.2) -> void:
    if _animation == null:
        return
    var resolved := _resolve(wanted)
    if resolved == "" or _current == resolved:
        return
    _current = resolved
    _animation.play(resolved, blend)

func play_motion(speed: float, on_floor: bool) -> void:
    _last_speed = speed
    _last_on_floor = on_floor
    if _animation == null or _reach_active:
        return
    if speed > run_speed_threshold and on_floor:
        _play(run_clip, 0.15)
    else:
        _play(idle_clip, 0.25)

func play_collect() -> void:
    if _animation == null:
        return
    var resolved := _resolve(reach_clip)
    if resolved == "":
        return
    _reach_active = true
    _animation.play(resolved, 0.12)
    _current = resolved

func _on_animation_finished(finished: StringName) -> void:
    if _animation == null or not _reach_active:
        return
    if String(finished) != _resolve(reach_clip):
        return
    _reach_active = false
    if _last_speed > run_speed_threshold and _last_on_floor:
        _play(run_clip, 0.2)
    else:
        _play(idle_clip, 0.2)
