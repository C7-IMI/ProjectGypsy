# SculptForge in the design process

SculptForge 0.9.6 is installed on this PC with the **SculptForge Bridge** Blender extension and a file-exchange
folder at %APPDATA%\SculptForge\SculptForge\blender.

## Design workflow

1. **Blockout in Blender.** Use the golden asset/import workflow and keep transforms, materials and modifiers.
2. **Send to SculptForge.** In Blender use the SculptForge Bridge add-on, or from Gypsy:
       python workstream/gypsy.py toolkit sculptforge bridge-send --project . --input assets/hero/wayfarer.glb
   The exchange writes to_blender/manifest.json and GoZ payloads.
3. **Sculpt detail in SculptForge.** Use SubTools, layers, masks, polygroups and face shapes. SculptForge is the
   authoring surface; Gypsy is not automating the GUI.
4. **Send back to Blender.** Use the add-on's Send to Blender; transforms, materials and modifiers update in place.
   Gypsy can receive the result headlessly:
       python workstream/gypsy.py toolkit sculptforge bridge-receive --project . --output artifacts/sculptforge/received.glb
5. **Return to the Gypsy pipeline.** Retopo/UV/export in Blender, then validate/import with the existing toolpacks,
   asset graph and hero checks.

## Headless LODs and conversion

    python workstream/gypsy.py toolkit sculptforge status --json
    python workstream/gypsy.py toolkit sculptforge lods --project . --input assets/hero/wayfarer.glb --output artifacts/sculptforge/wayfarer.glb --levels 3 --ratio 0.5 --force
    python workstream/gypsy.py toolkit sculptforge convert --project . --input assets/hero/wayfarer.glb --output artifacts/sculptforge/wayfarer.fbx --format fbx --force

All paths must resolve inside the project; script metacharacters are refused. Outputs are hashed and reported.

## What is and is not claimed

- Status is a real install/bridge probe.
- Headless LOD/convert commands are real CLI runs.
- Bridge send/receive are real file handshakes, but live GUI automation is not.
- No sculpt quality, retopo quality, licence clearance or engine-import pass is claimed from this toolkit alone.
