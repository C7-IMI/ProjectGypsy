# LeftBehind — Unity 6 slice

The second-engine proof for ProjectGypsy, named **LeftBehind**. Unity licence is proven; this project contains the
same mechanic as the Godot slice: a player capsule, three collectible crystals, a follow camera and a deterministic
headless demo.

## Open/build

Open `unity/LeftBehind` in Unity 6000.6.7f1, or build headless from the repository root:

    Unity.exe -batchmode -quit -nographics -projectPath unity/LeftBehind -executeMethod BuildLeftBehind.Build -logFile artifacts/leftbehind/build.log

Output: `unity/LeftBehind/Build/LeftBehind.exe`.

## Run

Interactive:

    .\unity\LeftBehind\Build\LeftBehind.exe

Headless acceptance demo:

    .\unity\LeftBehind\Build\LeftBehind.exe -batchmode -nographics --demo -logFile artifacts/leftbehind/player.log

Expected marker:

    GYPSY_DEMO_OK collected=3 frames=<n>

Capture (windowed):

    .\unity\LeftBehind\Build\LeftBehind.exe --demo --capture=artifacts/leftbehind/frame.png -screen-fullscreen 0 -screen-width 1280 -screen-height 720 -logFile artifacts/leftbehind/capture.log

## Controls

WASD / arrow keys move the capsule. Touching a crystal collects it. The camera follows.

## Evidence

- `artifacts/leftbehind/build.log` — Unity build report
- `artifacts/leftbehind/player.log` — demo marker
- `artifacts/leftbehind/frame.png` — rendered capture when requested
- `docs/UNITY-SLICE.md` — acceptance record (written after verification)

The project is not the Phase-1 engine choice; it is the second-engine adapter proof. See ADR-001/ADR-009.
