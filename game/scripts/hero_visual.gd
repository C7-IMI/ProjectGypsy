extends Node3D
## Wayfarer hero presentation manager.
##
## Owns three authored LODs, chooses LOD0/LOD1/LOD2 from camera distance, drives
## the imported Smile morph on collection, and applies spring-driven cape/cloth
## secondary motion. Gameplay (CharacterBody3D, collision, autopilot, markers)
## remains in player.gd/main.gd; this node never gates gameplay.

@export var idle_clip := "idle"
@export var run_clip := "run"
@export var reach_clip := "reach"
@export var run_speed_threshold := 0.8
@export var lod1_distance := 9.0
@export var lod2_distance := 14.0
@export var cape_damping := 7.0
@export var cape_stiffness := 24.0

var _lods: Array[Node] = []
var _players: Array[AnimationPlayer] = []
var _meshes: Array[MeshInstance3D] = []
var _skeletons: Array[Skeleton3D] = []
var _active_player: AnimationPlayer = null
var _active_skeleton: Skeleton3D = null
var _current := ""
var _reach_active := false
var _last_speed := 0.0
var _last_on_floor := true
var _current_lod := 0
var _lod_override := -1
var _face_value := 0.0
var _face_target := 0.0
var _face_indices: Array[int] = []
var _face_meshes: Array[MeshInstance3D] = []
var _cape_indices: Array[int] = []
var _cape_rest: Array[Quaternion] = []
var _cape_angles: Array[float] = []
var _cape_vels: Array[float] = []
var _cloth_ticks := 0

func _ready() -> void:
    for name in ["LOD0", "LOD1", "LOD2"]:
        var node := get_node_or_null(name)
        if node != null:
            _lods.append(node)
    for node in _lods:
        var player := node.find_child("AnimationPlayer", true, false) as AnimationPlayer
        if player != null:
            _players.append(player)
        var skeleton := node.find_child("Skeleton3D", true, false) as Skeleton3D
        if skeleton != null:
            _skeletons.append(skeleton)
        for mesh in node.find_children("*", "MeshInstance3D", true, false):
            if mesh is MeshInstance3D:
                _meshes.append(mesh)
    for player in _players:
        for wanted in [idle_clip, run_clip, reach_clip]:
            var resolved := _resolve(player, wanted)
            if resolved != "":
                player.get_animation(resolved).loop_mode = Animation.LOOP_NONE if wanted == reach_clip else Animation.LOOP_LINEAR
        player.animation_finished.connect(_on_animation_finished.bind(player))
    _discover_face()
    _select_lod(0, true)
    print("HERO_VISUAL lods=" + str(_lods.size()) + " clips=" + str(_clip_list()) + " face=" + str(_face_indices.size()) + " cape=" + str(_cape_indices.size()))
    _play(idle_clip, 0.0)

func _clip_list() -> Array:
    if _players.is_empty():
        return []
    return _players[0].get_animation_list()

func _resolve(player: AnimationPlayer, wanted: String) -> String:
    if player == null:
        return ""
    for name in player.get_animation_list():
        var lower := String(name).to_lower()
        if lower == wanted or lower.ends_with("|" + wanted):
            return String(name)
    return ""

func _play(wanted: String, blend := 0.2) -> void:
    for player in _players:
        var resolved := _resolve(player, wanted)
        if resolved == "" or resolved == _current:
            continue
        player.play(resolved, blend)
    _current = _resolve(_players[0], wanted) if not _players.is_empty() else ""

func play_motion(speed: float, on_floor: bool) -> void:
    _last_speed = speed
    _last_on_floor = on_floor
    if _players.is_empty() or _reach_active:
        return
    if speed > run_speed_threshold and on_floor:
        _play(run_clip, 0.15)
    else:
        _play(idle_clip, 0.25)

func play_collect() -> void:
    if _players.is_empty():
        return
    _face_target = clampf(_face_target + 0.34, 0.0, 1.0)
    _face_value = maxf(_face_value, _face_target * 0.6)
    _apply_face()
    var resolved := _resolve(_players[0], reach_clip)
    if resolved == "":
        return
    _reach_active = true
    for player in _players:
        var clip := _resolve(player, reach_clip)
        if clip != "":
            player.play(clip, 0.12)
    _current = resolved

func _on_animation_finished(_name: StringName, source: AnimationPlayer) -> void:
    if source != _active_player or not _reach_active:
        return
    _reach_active = false
    if _last_speed > run_speed_threshold and _last_on_floor:
        _play(run_clip, 0.2)
    else:
        _play(idle_clip, 0.2)

func _process(delta: float) -> void:
    _update_lod()
    _update_face(delta)
    _update_cape(delta)

func _update_lod() -> void:
    var wanted := _current_lod
    if _lod_override >= 0:
        wanted = _lod_override
    else:
        var camera := get_viewport().get_camera_3d()
        if camera != null:
            var distance := camera.global_position.distance_to(global_position)
            if distance >= lod2_distance and _lods.size() > 2:
                wanted = 2
            elif distance >= lod1_distance and _lods.size() > 1:
                wanted = 1
            else:
                wanted = 0
    if wanted != _current_lod:
        _select_lod(wanted, false)

func _select_lod(index: int, force: bool) -> void:
    if _lods.is_empty():
        return
    index = clampi(index, 0, _lods.size() - 1)
    if not force and index == _current_lod:
        return
    _current_lod = index
    var time := 0.0
    if _active_player != null:
        time = _active_player.current_animation_position
    for i in _lods.size():
        _lods[i].visible = i == index
    _active_player = _players[index] if index < _players.size() else null
    _active_skeleton = _skeletons[index] if index < _skeletons.size() else null
    _discover_cape()
    if _active_player != null and _current != "":
        var resolved := _resolve(_active_player, _current)
        if resolved != "":
            _active_player.play(resolved, 0.0)
            _active_player.seek(time, true)
    print("HERO_LOD mode=" + str(index) + " lods=" + str(_lods.size()))

func force_lod(index: int) -> void:
    _lod_override = index
    _update_lod()

func get_lod_level() -> int:
    return _current_lod

func get_face_value() -> float:
    return _face_value

func get_cape_bones() -> int:
    return _cape_indices.size()

func _discover_face() -> void:
    _face_indices.clear()
    _face_meshes.clear()
    for mesh in _meshes:
        if mesh.mesh == null:
            continue
        for i in mesh.mesh.get_blend_shape_count():
            if String(mesh.mesh.get_blend_shape_name(i)).to_lower() == "smile":
                _face_indices.append(i)
                if not _face_meshes.has(mesh):
                    _face_meshes.append(mesh)
    if not _face_indices.is_empty():
        print("HERO_FACE morphs=Smile meshes=" + str(_face_meshes.size()))

func _update_face(delta: float) -> void:
    _face_value = move_toward(_face_value, _face_target, delta * 2.0)
    _apply_face()

func _apply_face() -> void:
    for mesh in _face_meshes:
        for index in _face_indices:
            if index < mesh.mesh.get_blend_shape_count():
                mesh.set_blend_shape_value(index, _face_value)

func _discover_cape() -> void:
    _cape_indices.clear()
    _cape_rest.clear()
    _cape_angles.clear()
    _cape_vels.clear()
    if _active_skeleton == null:
        return
    for name in ["cape_a", "cape_b", "cape_c"]:
        var index := _active_skeleton.find_bone(StringName(name))
        if index >= 0:
            _cape_indices.append(index)
            _cape_rest.append(_active_skeleton.get_bone_pose_rotation(index))
            _cape_angles.append(0.0)
            _cape_vels.append(0.0)
    if not _cape_indices.is_empty():
        print("HERO_CLOTH bones=" + str(_cape_indices.size()))

func _update_cape(delta: float) -> void:
    if _active_skeleton == null or _cape_indices.is_empty():
        return
    var body := get_parent()
    var speed := 0.0
    if body is CharacterBody3D:
        speed = Vector2(body.velocity.x, body.velocity.z).length()
    var target := clampf(-speed * 0.06 + sin(Time.get_ticks_msec() * 0.004) * 0.08, -0.65, 0.35)
    for i in _cape_indices.size():
        var accel := (target - _cape_angles[i]) * cape_stiffness - _cape_vels[i] * cape_damping
        _cape_vels[i] += accel * delta
        _cape_angles[i] = clampf(_cape_angles[i] + _cape_vels[i] * delta, -0.8, 0.5)
        var index := _cape_indices[i]
        var pose := _cape_rest[i] * Quaternion(Vector3.RIGHT, _cape_angles[i])
        _active_skeleton.set_bone_pose_rotation(index, pose)
    _cloth_ticks += 1
    if _cloth_ticks == 20:
        print("HERO_CLOTH active bones=" + str(_cape_indices.size()) + " angle=" + str(snappedf(_cape_angles[0], 0.001)))
