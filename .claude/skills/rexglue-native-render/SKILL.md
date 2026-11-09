---
name: rexglue-native-render
description: How to recompile this Xbox 360 game (Naruto Shippuden Ultimate Ninja Storm Revolution) with the ReXGlue SDK and give it a native Vulkan renderer, following the finished Storm 3 port in ~/Desktop/naruto-storm3-recomp. Covers project setup, codegen and the manifest, finding function boundaries, REX_HOOK and guest memory, SDK patches, running and debugging, and porting the native renderer (finding the game's D3D functions, shader cache, settings). Use before any build, hook, manifest, SDK or renderer work, or when the game must be run, tested or debugged.
---

# ReXGlue SDK and the native renderer (Storm Revolution)

This project recompiles the Xbox 360 game *Naruto Shippuden: Ultimate Ninja
Storm Revolution* with ReXGlue: the game's PowerPC code is translated to C++,
compiled, and run on ReXGlue's runtime (a Xenia-derived kernel, audio and
input). The goal is the same as the finished sister project
**`~/Desktop/naruto-storm3-recomp`** (Storm 3 Full Burst): a native PC (and
later Android) port with **our own Vulkan renderer** instead of the SDK's
emulated Xenos GPU.

Storm 3 and Revolution are both CyberConnect2's engine (xfbin/NUCC files,
`nuccMaterial_xbox360.nsh` shaders, the same D3D usage), so almost every
technique transfers. **Addresses don't**: every `sub_XXXXXXXX`, global and
struct offset from Storm 3 must be found again in Revolution's `Default.xex`
before it is used. Read the Storm 3 code for *how*, never copy its numbers.

Never commit unless the user asks. Never commit or share `assets/`,
`generated/`, built executables or anything derived from the game.

## The game files

`assets/` is the user's Xbox 360 game: `Default.xex` (capital D), `data/`
(`sim/data.cpk`, `sound.cpk`, `stage.cpk`, `dataRegion.cpk`, `disc/adx2.cpk`,
`movie.cpk`, `system/*.nsh`, `sound/XENON/`), `nxeart`, `AvatarAssetPack`.
Read-only: never write into it.

`assets/patchdata/adddata.cpk` is **not** part of the Xbox game: it is a PC
mod ("Storm Revolution 4", PC paths `sound/WIN32/...`, PC voices in Siren 14).
The Xbox game never reads `patchdata/`. Leave it out of every test of the
plain game; mods come later, converted with the Storm 3 project's tools
(`tools/mod-convert.py`, `mod-repack.py`, `nub_voice.py`, `docs/modding.md`).

## Reference: the Storm 3 project

| Need | Look at (in ~/Desktop/naruto-storm3-recomp) |
| --- | --- |
| Build setup, presets, CMake | `CMakeLists.txt`, `CMakePresets.json`, `README.md` |
| SDK setup and our SDK patches | `tools/setup-sdk.sh`, `patches/*.patch`, `patches/README.md` |
| Manifest and function boundaries | `naruto_manifest.toml`, `docs/function-dispatch.md`, `tools/verify_function_dispatch.py` |
| How the game's D3D calls were found | `docs/d3d-functions.md`, `config/naruto_d3d_funcs.toml` |
| Native renderer | `src/render_probe.cpp` (D3D hooks), `src/frame_capture.cpp`, `src/native_view.cpp`, `src/texture_decode.cpp`, `src/shader_library.cpp`, `tools/build-shaders.py`, `tools/build-postfx.py` |
| Run script, launcher | `tools/run-radeon.sh`, `tools/launcher/` |
| Runtime settings | `config/naruto-performance.toml` |
| Game fixes as hooks | `src/heap_limits.cpp`, `src/moveset_guard.cpp` |

Reuse its files by adapting them (names, paths, addresses), not by linking
to them.

## Starting the project

The SDK is already built and installed at `~/rexglue-sdk`
(`~/rexglue-sdk/out/install/linux-amd64`), at the revision and with the
patches the Storm 3 project uses. Don't rebuild or re-patch it without a
reason; if a fix is needed, see "SDK patches".

```bash
cd ~/Desktop/NarutoNinjaStormRevolution
git init                                   # if not yet
~/rexglue-sdk/out/install/linux-amd64/bin/rexglue init \
    --project-name <name> --xex-path assets/Default.xex --game-root assets
```

This writes the manifest (`<name>_manifest.toml`), `generated/rexglue.cmake`
and the project skeleton. Then adapt from Storm 3: `CMakePresets.json`
(linux-amd64-release/debug), the `CMakeLists.txt` structure (sources list,
GPU plugin `xenos`, verify check), `.gitignore` (assets/, generated/, out/),
and a `config/<name>-performance.toml`. Ask the user for the project name
before choosing one.

## Building

```bash
cmake --preset linux-amd64-release -DCMAKE_PREFIX_PATH=$HOME/rexglue-sdk/out/install/linux-amd64
cmake --build --preset linux-amd64-release --target <name>_codegen
cmake --preset linux-amd64-release        # again, so the new files are seen
cmake --build --preset linux-amd64-release [--parallel 4]
```

All four after the manifest changes; only the last after `src/` changes.
Codegen writes `generated/default/`: **never edit it**. Compiling it takes a
long time and a lot of memory; use `--parallel 4` if the compiler is killed.

## Function boundaries (the CPU side)

Codegen finds most functions, not all. The first runs will stop with
**"Call to invalid or unregistered function at guest address X"**, or crash
in a function cut in the wrong place. For each one:

1. Disassemble around X from `Default.xex` and look at the neighbours: a
   real entry (prologue `mflr r12`, a thunk `lwz r12,0(r3); lwz r11,N(r12);
   mtctr r11; bctr`, a small leaf ending in `blr`)?
2. If real, add it to `[entrypoint.functions]` in the manifest
   (`0xADDR = { size = N }`, `{}`, or `{ parent = ..., end = ... }` for a
   shared chunk), with a comment saying how it was verified, then rebuild
   with all four commands.
3. If X is garbage (`0x0`, `0x1`, a data address), the pointer is wrong;
   find the cause, never "fix" it in the manifest.
4. When one pattern (e.g. a vtable thunk) is missing once, scan the whole
   xex for it and add every match (the Storm 3 project found 164 at once).

In the Storm 3 project this part was done by the user by hand. Explain what
you add, and why, so they can check it.

## Hooking a game function

Every translated function `sub_XXXXXXXX` is defined **weak**, with the real
code under `__imp__sub_XXXXXXXX` (see `generated/default/*_pch.h`). A strong
`sub_XXXXXXXX` in `src/` replaces it; call `__imp__` for the original.

```cpp
#include <rex/hook.h>
#include <rex/logging.h>
#include <rex/memory/utils.h>

extern "C" {
REX_FUNC(__imp__sub_XXXXXXXX);    // the original
}

REX_HOOK_RAW(sub_XXXXXXXX) {       // ctx: PPCContext&, base: guest memory
  const uint32_t ptr = ctx.r4.u32;                         // args in r3..r10
  uint32_t v = rex::memory::load_and_swap<uint32_t>(base + ptr);  // big-endian guest
  rex::memory::store_and_swap<uint32_t>(base + ptr, v);
  __imp__sub_XXXXXXXX(ctx, base);                          // result in ctx.r3
}
```

- Arguments in `ctx.r3`–`ctx.r10` (`.u32`, `.u64`, `.s32`), floats in
  `ctx.f1`…; return in `ctx.r3` / `ctx.f1`; `ctx.lr` is the caller.
- Guest memory is `base + address`, always through `load_and_swap` /
  `store_and_swap`.
- `REX_HOOK(sub_X, fn)` marshals plain-typed arguments; `REX_STUB*` makes a
  logged no-op; `rex::CallFrame` / `rex::ppc::ImportFunction` call game
  functions from a hook without disturbing registers (`rex/hook.h`).
- Log with `REXLOG_INFO/WARN/ERROR` (fmt syntax); log rare events once.
- A hook may not fire when its caller is in the same generated `.cpp` file.
  Check the callers (`grep -n "sub_X(ctx" generated/default/*.cpp`) and prove
  the hook runs (a one-time log) before relying on it.
- Each new `src/*.cpp` goes into the sources list in `CMakeLists.txt`.
- Head every hook file with a comment: what the function does, how it was
  identified, and why it is hooked (as in Storm 3's `src/heap_limits.cpp`).

## SDK patches

The SDK at `~/rexglue-sdk` already carries Storm 3's patches (Vulkan texture
exponent, present semaphores, skip-rendering, crash diagnostics, Android,
netplay); see that project's `patches/README.md`. A new SDK fix: change it
in `~/rexglue-sdk`, rebuild with
`(cd ~/rexglue-sdk && cmake --build --preset linux-amd64-release --target install --parallel 4)`,
save it as a `.patch` in this project's `patches/` with a README entry, and
tell the user, since the Storm 3 build uses the same SDK and the change
reaches it on its next build.

## Running

Adapt Storm 3's `tools/run-radeon.sh`: it sets the SDK library path, Vulkan
driver (`--nvidia` / `--radeon`), SDL X11, `--game_data_root`, async shader
compilation, and `--native-only` (native view only, `--vulkan_skip_rendering=true`).
Before the native renderer exists, run with the SDK's own Xenos renderer:

```bash
LD_LIBRARY_PATH=$HOME/rexglue-sdk/out/install/linux-amd64/lib64 \
  ./out/build/linux-amd64-release/<name> --game_data_root="$PWD/assets" --gpu_plugin=xenos
```

- Logs: `out/build/linux-amd64-release/logs/<name>_<N>.log`, one per run.
  Search for `access violation`, `invalid or unregistered`, `[error]`.
- Keyboard: `--mnk_mode=true` with `--keybind_a=K` etc.
- Each run leaves `/dev/shm/xenia_memory_*` (about 5 GB): delete them after
  the game exits, never while it runs.
- Don't `pkill -f <name>` from the Bash tool (it kills the tool's own shell);
  find the pid with `ps -eo pid,args | grep '[o]ut/build/.*/<name>'`.
- Judge by screenshots: `xdotool search --name <window title>`,
  `xdotool windowactivate --sync`, `spectacle -b -n -a -o shot.png`, then
  Read the PNG. Keys: `xdotool keydown K; sleep 0.1; xdotool keyup K`, ~0.7 s
  apart, screenshot before the next key (menus drop keys during changes). If
  the user is using the desktop, keys and screenshots hit their window:
  check the screenshot shows the game.
- The dev laptop's RTX 2050 is power capped: compare GPU timings relatively.
- Guest memory while running: `/dev/shm/xenia_memory_*`; virtual address =
  file offset below `0xA0000000`, physical-backed addresses at
  `0x100000000 + (addr & 0x1FFFFFFF)`.

## Porting the native renderer

Order of work, as it went for Storm 3 (`docs/d3d-functions.md` there):

1. **Find the game's D3D functions** in Revolution's xex:
   - Present: the function that calls `VdGetSystemCommandBuffer` and
     `VdSwap`, once per frame.
   - Draws: trace calls per frame; `DrawIndexedVertices`-like
     `(device, primitive, 0, start, count)` and `DrawVertices`-like
     `(device, primitive, 0, count)` account for every draw.
   - Shader setters (store to device fields and set dirty bits), the
     per-draw commit, resolves, the render/sampler state setter table, and
     the device pointer global. Write down the evidence for each in a
     `docs/d3d-functions.md` and list them in a `config/*_d3d_funcs.toml`.
   - Storm 3's offsets (device `+0x480` fetch constants, `+0x780` VS
     constants, `+0x1780` PS constants, `+0x330C`/`+0x3310` shaders...) come
     from the XDK's D3D device layout and are likely the same if the XDK
     version matches. Verify each one in Revolution before use.
2. **Capture**: port `render_probe.cpp` + `frame_capture.cpp` with the new
   addresses; log draw counts per frame and compare with what you expect.
3. **Shaders**: port `tools/build-shaders.py` (XenosRecomp, pinned, with
   `tools/shaders/xenosrecomp-naruto.patch`, then DXC to SPIR-V) for
   `data/system/nuccMaterial_xbox360.nsh` and `nuccPostEffect_xbox360.nsh`,
   plus shaders captured at runtime. Match shaders exactly; never draw with
   a "similar" one. The cache is game-derived: never commit it.
4. **View**: port `native_view.cpp` (EDRAM targets as Vulkan images,
   resolves, bindless textures, `texture_decode.cpp`), then the post effects
   (FSR 1, CAS, FXAA via `tools/build-postfx.py`).
5. Settings, as in Storm 3 (rename the prefix for this project):
   `*_NATIVE_VIEW=1` on, `_ONLY` its window only, `_SCALE` 1–4 (1.5 =
   1080p), `_UPSCALER` fsr/cas/linear, `_SHARPNESS`, `_FXAA`, `_ASPECT`,
   `_FULLSCREEN`; for debugging `_SNAPSHOTS` + `_DUMP` (frame snapshots, F12
   any time), `_DRAW_SNAPSHOTS` + `_DRAW_SNAPSHOT_RANGE` (after each draw),
   `_TEXTURES` (dump decoded textures), `_DECOMPRESS`, `_DEBUG` flags.

Debugging a wrong picture: screenshot; F12 snapshot; compare with the SDK's
Xenos rendering (run without `--native-only`); narrow to one draw with the
draw snapshots; check its shader, textures and state; fix; confirm with a
screenshot of the same scene and a clean log.

## Rules

- Never edit `generated/`; change `src/`, the manifest, or an SDK patch.
- Never trust a Storm 3 address in Revolution until verified in this xex.
- Confirm every change in the running game (screenshot and log), and say
  plainly what was and wasn't verified.
- Keep comments and docs in plain words: what the code does and why.
- Ask before building or running code downloaded from outside the project,
  and before changing the shared SDK.
