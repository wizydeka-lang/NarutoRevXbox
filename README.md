# Naruto Revolution recompilation

ReXGlue recompilation of the Xbox 360 version of Naruto Shippuden: Ultimate
Ninja Storm Revolution. Uses the installed ReXGlue SDK and its Xenos GPU plugin.
Includes a native Vulkan renderer adapted from the Storm 3 reference, using
Revolution-specific D3D hooks and locally compiled shaders.

Supply your own extracted Xbox 360 game in `assets/`, including `Default.xex`.
Game assets, generated code and build outputs are excluded from Git. The PC mod
in `assets/patchdata/` is not used for the baseline game.

## Build on Linux

Requires CMake 3.25+, Ninja, Clang 20, Python 3.11+, and the installed SDK at
`~/rexglue-sdk/out/install/linux-amd64` (override `CMAKE_PREFIX_PATH` if needed).

```sh
cmake --preset linux-amd64-release
cmake --build --preset linux-amd64-release --target naruto_revolution_codegen
cmake --preset linux-amd64-release
cmake --build --preset linux-amd64-release
```

Repeat all four commands after manifest changes. Source-only changes need the
last command. Builds use four compiler jobs. Explicit manifest entries are
checked against generated registrations and symbols in the linked executable.

## Run

```sh
tools/run.sh --check
tools/run.sh                 # NVIDIA
tools/run.sh --radeon        # integrated Radeon
```

For keyboard input (K = A, Enter = Start):

```sh
tools/run.sh -- --mnk_mode=true --keybind_a=K --keybind_start=Return
```

Pass game options after `--`. Logs are under
`out/build/linux-amd64-release/logs/`. Do not remove `/dev/shm/xenia_memory_*`
files while a game is running.

See `.claude/skills/rexglue-native-render/SKILL.md` for project rules and the
Storm 3 reference. Revolution function addresses must be verified independently.

The battle arena defaults to 128 MiB to accommodate the supplied character
assets. Override with `REVOLUTION_BATTLE_ARENA_MB` (62–192); 62 restores the
original capacity. The parent arena and battle-reset allocation grow together.
See `docs/battle-memory.md` for the verified addresses and failure evidence.

## Native Vulkan renderer

```sh
tools/run.sh --native-only       # native window, SDK GPU drawing disabled
tools/run.sh --native            # native and SDK windows for comparison
```

The native view defaults to 1080p rendering (scale 1.5), FSR 1 presentation and
16:9. Settings use the `REVOLUTION_NATIVE_VIEW_` prefix:

| Suffix | Values |
| --- | --- |
| `SCALE` | 1–4; 1.5 is 1080p from the original 720p |
| `UPSCALER` | `fsr`, `cas`, `linear` |
| `SHARPNESS` | 0–1; default 0.9 |
| `FXAA` | 1 to enable |
| `ASPECT` | `16:9`, another `W:H`, or `fill` |
| `FULLSCREEN` | 1 to enable |
| `SNAPSHOTS` | directory for F12 snapshots |
| `DRAW_SNAPSHOTS` | directory/prefix for per-draw snapshots |
| `DRAW_SNAPSHOT_RANGE` | draw range such as `0-20` |
| `TEXTURES` | directory for decoded texture dumps |
| `DECOMPRESS` | 1 to force CPU texture decompression |
| `DEBUG` | diagnostic bit mask described in `src/native_view.cpp` |

Set `REVOLUTION_RENDER_PROBE=1` to log draw/shader counts. F12 requests a native
snapshot; a controller remains usable while the native window has focus.
Shader and pipeline caches, runtime captures and screenshots stay under `out/`.

### Rebuild the shader cache

Use an existing XenosRecomp checkout at revision
`990d03b28a27b50277ee5d8d942e1c5f873869d1`, with
`tools/shaders/xenosrecomp-naruto.patch` applied and its DXC binaries present.
The script validates that revision and patch and never downloads/builds tools.

```sh
python3 tools/build-shaders.py --compiler-root /path/to/XenosRecomp
```

The executable is found in the sibling `XenosRecomp-build/XenosRecomp/` folder;
use `--compiler /path/to/XenosRecomp` to override it. The cache is generated
from this project's own `.nsh` files and `out/shaders/runtime/` captures. If a
new scene captures missing shaders, rebuild the cache and restart. The renderer
never substitutes a similar shader. Game-derived shader caches are not shared.

Post-processing SPIR-V is supplied in `src/postfx_spirv.h`. To rebuild it from
the included shader sources:

```sh
python3 tools/build-postfx.py --dxc-dir /path/to/XenosRecomp/thirdparty/dxc-bin
```

See `docs/d3d-functions.md` for mapping evidence and runtime verification.
