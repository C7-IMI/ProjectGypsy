# ADR-007 — Language boundaries

- **Status:** accepted, 2026-10-25
- **Scope:** which language is used for gameplay, tooling, native plugins and the workstream.
- **Related:** [ADR-001](ADR-001-engines.md), [ADR-002](ADR-002-art-pipeline.md),
  [ADR-003](ADR-003-workstream-architecture.md), [ADR-005](ADR-005-character-animation-automation.md),
  [ADR-006](ADR-006-blender-import-matrix.md), [TOOLCHAIN.md](../TOOLCHAIN.md).

## Context

The engine is a per-project choice (ADR-001), and each engine has an idiomatic language: Godot GDScript/C#, Unity C#,
UE5 C++/Blueprints, Flax C#. The workstream is Python today. Rust was considered (and the operator does not require
it); it is a strong systems language but not an engine language on this stack.

The risk to avoid is a language boundary that fights the engine: editor integration, hot reload, import hooks, platform
export templates and debugging all assume the engine's own language.

## Decision

1. **Gameplay, editor integration, UI and scene logic use the engine's language.** No engine-language replacement.
2. **The workstream and asset tooling use Python** for orchestration, adapters, validators, reports and tests. It is
   already installed, has the image/mesh/glTF ecosystem and iterates fast.
3. **Rust is optional and is not installed.** If a native need is proven, Rust may be used only behind a **stable
   boundary**: a versioned CLI or a C ABI native library. It never becomes the gameplay language on these engines.
4. **No Rust types cross the boundary.** C ABI/JSON only; no unwinding across FFI; per-platform builds (Windows,
   Android, iOS); a load-and-call smoke test before the library is trusted.
5. **Performance hot paths are engine-native first.** A native plugin is justified only by profiling evidence and a
   measured delta; it is not a default architecture.
6. **C++ is allowed only where the engine requires it** (UE5 modules, native plugins); **C#** for Unity/Godot/Flax
   gameplay; **GDScript** for Godot gameplay and tools.
7. **Every language in the build is checked.** Python tests/checks today; engine build checks per adapter; if Rust is
   ever added, `cargo fmt --check`, `cargo clippy` and `cargo test` join the same check list, with a pinned toolchain.

## Consequences

**Positive:** the engine's editor, importers, debugging and platform export remain usable; the team can hire the
engine's normal skills; the workstream stays fast to change; Rust remains available later without a rewrite.

**Negative:** more than one language in the repository; the boundary must be documented and tested; a native library
needs per-platform builds; Python may need a native helper if a hot loop is ever measured as the bottleneck.

## Alternatives rejected

- **Rust-first game** (Bevy/Fyrox or Rust plugins for all gameplay): a different engine/pipeline project with weaker
  editor/AAA ecosystem, more platform work and a smaller hiring pool; not justified here.
- **Single language for engine + tooling**: would force the engine language onto tooling or the tooling language onto
  the engine; both lose.
- **C++ everywhere**: slower iteration and more risk for tooling; appropriate only inside UE5.
- **Install Rust now "just in case"**: unused toolchains drift; add it when a measured need exists.

## Open questions

- If a native helper is justified later, which boundary: CLI first (simpler) or C ABI plugin (used in-process)?
- Which hot path is measured first (procedural generation, mesh processing, compression, simulation)?
- For a second engine adapter, does the same language split hold? (Presumed yes.)
