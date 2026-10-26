# Poly Haven (CC0)

`polyhaven.py` searches and downloads CC0 assets from Poly Haven's public API (no key) and writes a JSON sidecar
with the licence, source URL, SHA-256 and retrieval time.

~~~powershell
python tools/polyhaven/polyhaven.py list --type textures --search brick
python tools/polyhaven/polyhaven.py download brick_wall_02 --resolution 1k --slot Diffuse --dest artifacts/polyhaven
~~~

Downloaded assets are authored/curated inputs, not generated; review them before use. Poly Haven licence: CC0.
