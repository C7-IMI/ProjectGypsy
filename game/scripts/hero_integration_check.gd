extends Node
## Headless integration check for the Wayfarer visual under Player.
##
## Exercises the real main scene: idle at rest, run while the autopilot moves the
## CharacterBody3D, reach when a crystal collection calls play_collect(), and a
## return to idle after the one-shot finishes. No rendering, no network, no Blender.
## Run: godot --headless --path game res://scenes/hero_integration_check.tscn

var _failures: Array[String] = []

func _check(label: String, actual: String, expected: String) -> void:
    print("HERO_CHECK " + label + " clip=" + actual + " expected=" + expected)
    if actual != expected:
        _failures.append(label + ": expected " + expected + ", got " + actual)

func _ready() -> void:
    var main: Node = load("res://scenes/main.tscn").instantiate()
    add_child(main)
    await get_tree().process_frame
    await get_tree().physics_frame
    var player: Node = main.get_node("Player")
    var hero: Node = player.get_node("Hero")
    var animation := hero.find_child("AnimationPlayer", true, false) as AnimationPlayer
    if animation == null:
        print("HERO_CHECK_FAIL no AnimationPlayer")
        get_tree().quit(1)
        return
    print("HERO_CHECK anims=" + str(animation.get_animation_list()))
    _check("idle", String(animation.current_animation), "idle")

    var lod_count := int(hero.call("get_lod_level"))
    print("HERO_CHECK lod_initial=" + str(lod_count))
    hero.call("force_lod", 2)
    await get_tree().process_frame
    if int(hero.call("get_lod_level")) != 2:
        _failures.append("runtime LOD force failed")
    print("HERO_CHECK lod_forced=" + str(hero.call("get_lod_level")))
    hero.call("force_lod", -1)

    var camera := get_viewport().get_camera_3d()
    if camera != null:
        var saved := camera.global_position
        camera.global_position = (hero as Node3D).global_position + Vector3(0, 0, 20)
        hero.call("_update_lod")
        if int(hero.call("get_lod_level")) != 2:
            _failures.append("distance LOD switch failed")
        print("HERO_CHECK lod_distance=" + str(hero.call("get_lod_level")))
        camera.global_position = saved
        hero.call("_update_lod")

    player.set("autopilot_enabled", true)
    player.set("autopilot_direction", Vector3(0, 0, 1))
    for _i in range(10):
        await get_tree().physics_frame
    _check("run", String(animation.current_animation), "run")

    player.set("autopilot_direction", Vector3.ZERO)
    player.set("autopilot_enabled", false)
    for _i in range(6):
        await get_tree().physics_frame
    player.call("play_collect")
    for _face_frame in range(4):
        await get_tree().process_frame
    _check("reach", String(animation.current_animation), "reach")
    if float(hero.call("get_face_value")) <= 0.0:
        _failures.append("Smile morph was not driven")
    if int(hero.call("get_cape_bones")) < 1:
        _failures.append("cape bones not found")
    print("HERO_CHECK face=" + str(hero.call("get_face_value")) + " cape=" + str(hero.call("get_cape_bones")))

    for _i in range(160):
        await get_tree().physics_frame
    _check("idle_return", String(animation.current_animation), "idle")

    if _failures.is_empty():
        print("HERO_SYSTEMS_OK lods=3 face=driven cape=driven")
        print("HERO_CHECK_OK idle->run->reach->idle")
        get_tree().quit(0)
    else:
        print("HERO_CHECK_FAIL " + " | ".join(_failures))
        get_tree().quit(1)
