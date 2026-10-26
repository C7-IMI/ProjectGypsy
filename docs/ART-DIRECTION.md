# Art direction — Wayfarer hero

**Status:** working art direction for the first hero character (PG-D17/PG-D18). This is a production brief, not a claim
that the final hero is finished. The verified asset evidence is recorded after the Blender/Godot run.

## World and camera

The slice is a twilight alien moor: near-black ground, desaturated teal rock, a cold sky, and cyan “wayfinder” energy
that marks collectibles. The camera is a third-person follow camera looking slightly down; the hero must read at about
12–20 m and at 720p capture size. Silhouette first, detail second.

## Hero: the Wayfarer

A lone traveller who navigates by a brass wayfinder and a small lantern. The design should feel hand-built and
weathered, not military or glossy.

| Element | Direction |
| --- | --- |
| Silhouette | Tall hooded traveller; broad asymmetrical cloak; scarf tail; one visible lantern/wayfinder prop |
| Proportions | ~1.8 m; stylised 6.5–7 heads; oversized hands and boots for readability |
| Palette | cloak/teal #17464d, underlayer #0d252b, leather #4a3324, brass #c08a46, skin #b98262, wayfinder glow #63f5d8 |
| Materials | flat/painted PBR, roughness 0.5–0.8; metal brass; emissive wayfinder only |
| Detail budget | 1k–8k triangles; 512² base/normal/roughmetal maps; 4 material slots |
| Rig | humanoid root/hips/spine/chest/neck/head, clavicle/arms/hands, thighs/shins/feet; cloak chain 3 bones; scarf 2 bones |
| Animation set | **idle** (breathing, lantern sway), **run** (contact/passing/contact), **reach** (collect gesture) |
| Readability | cyan glow visible from behind/side; boots and hood distinct in silhouette; no thin danglers that vanish at 720p |

## Pipeline

1. **Brief and palette** — this document plus assets/hero/ART-BRIEF.md.
2. **Blockout** — primitive-based body and cloak at correct scale, origin at feet, forward −Y in Blender (Godot −Z).
3. **Rig and skin** — armature with explicit bone names; automatic weights followed by cleanup; test poses.
4. **Animation** — three actions on the same armature: idle, run, reach. Loop idle/run; reach is one-shot.
5. **Texture/material** — hand-authored palette texture or procedural cloth/leather detail; PBR values; emissive map for
   the wayfinder. No megascans, no unlicensed source art.
6. **Export** — GLB with mesh, armature, animations, materials and texture embedded/referenced; optional FBX for
   compatibility. Validate by re-importing.
7. **Godot integration** — visual under Player, collision unchanged; animation state from player velocity/autopilot.
8. **Capture and review** — headless demo must still print GYPSY_DEMO_OK; windowed capture must show the hero at a
   readable size. Reject the asset if it is invisible, mis-scaled, untextured or breaks the demo.

## Non-goals

No sculpted hair/fur, facial rig, cloth simulation, mocap, photoreal skin or hero LOD chain in this first pass. Those
are later if the art direction is accepted. No third-party asset may be shipped without provenance and licence.

## Validation contract

- Asset files exist and are non-empty.
- Armature has a humanoid root/spine/limb hierarchy.
- At least three named actions exist and are non-empty.
- LOD1/LOD2 preserve the rig/actions; normal/roughness maps and the Smile morph are present.
- Runtime systems: distance LOD switching, driven Smile, spring-driven cape motion, and the demo marker remain functional.
- Bounds are approximately human scale; origin at feet.
- Materials/textures are present and the glTF/FBX re-imports without errors.
- The Godot slice still passes the headless marker and produces a rendered frame.

If any of these fail, the correct status is “not built”, not “hero complete”.
