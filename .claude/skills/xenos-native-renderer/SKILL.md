---
name: xenos-native-renderer
description: How to give any Xbox 360 game recompiled with ReXGlue its own native Vulkan renderer, built from the one in ~/Desktop/NarutoNinjaStormRevolution (and Storm 3 before it). Covers the design (D3D hooks, frame capture, replay in a Vulkan view), which files can be reused as they are and which must be redone for each game, finding the game's D3D functions and device layout, the shader cache (XenosRecomp, DXC, exact matching), textures, EDRAM passes and resolves, post effects, settings and debugging. Use when starting or porting a native renderer for another 360 recompilation project, or when changing the renderer's shared parts.
---

# A native Vulkan renderer for ReXGlue Xbox 360 ports

ReXGlue recompiles a 360 game's PowerPC code to C++ and runs it on a
Xenia-derived runtime, whose `xenos` GPU plugin emulates the 360's GPU from
its command stream. A **native renderer** skips that emulation: it hooks
the game's Direct3D 9 (XDK) calls, copies each draw's data out of guest
memory, and draws it again with Vulkan and shaders compiled ahead of time.
This gives higher resolutions, FSR/CAS/FXAA, a smaller GPU cost, and a path
to Android.

The reference implementation is in **`~/Desktop/NarutoNinjaStormRevolution`**
(called "the reference" below), itself ported from
`~/Desktop/naruto-storm3-recomp`. Both are CyberConnect2 games, but most of
the code is about the **XDK's D3D and the Xenos GPU**, not the game, so it
works for other XDK games.

**Rule zero: addresses never transfer.** Every `sub_XXXXXXXX`, global,
device offset and shader-object offset must be found again, with evidence,
in the new game's own `Default.xex`. Copy the reference's *method* and
*code structure*. Never copy its numbers until the new xex confirms them.

## How it works

```
game thread                                  view thread (own window)
-----------                                  ------------------------
D3DDevice_Draw*   --hook--> RecordDraw ----> frame_capture::Capture
D3DDevice_ClearF  --hook--> CaptureClear       (vertices, indices, constants,
D3DDevice_Resolve --hook--> CaptureResolve      render state -> FrameInfo)
D3DDevice_Swap    --hook--> FinishFrame ---> native_view::SubmitFrame ----> replay, pass by pass:
                            (then call the original)                       EDRAM targets as VkImages,
                                                                           resolves as copies,
                                                                           textures decoded from guest
                                                                           memory, precompiled SPIR-V,
                                                                           upscale + present
```

- Every hook calls the original (`__imp__sub_...`), so the SDK's command
  processor still runs. Native-only mode passes
  `--vulkan_skip_rendering=true`, so the SDK builds the command stream but
  draws nothing, and the native view is the only picture.
- Draws are recorded **after** the original draw function runs, because that
  function commits the device's dirty state (shaders, constants, the
  register shadows) the capture reads.
- A **pass** is everything drawn between two Resolves. A Resolve copies an
  EDRAM render target, or the depth buffer, into a texture. It ends a pass,
  and its clear flags (`0x100` color, `0x200` depth/stencil) set how the next
  pass starts.
- `SubmitFrame` never blocks the game. The view takes frames as they come
  and gives their memory back (`RecycledData`).
- Shaders are **matched exactly**: the bound microcode is compared with
  every shader in the game's shader libraries, and each match has one
  precompiled SPIR-V. A shader with no match is saved from memory
  (`out/shaders/runtime/`) to be converted on the next cache build. It is
  never drawn with a "similar" shader.

## The files and what each one depends on

Paths are in the reference. "Generic" means XDK/Xenos-level code, which
needs only the setting prefix renamed and its device offsets checked.

| File | What it does | Depends on the game? |
| --- | --- | --- |
| `src/render_probe.cpp` | The D3D hooks, per-frame stats (`*_RENDER_PROBE=1`), pass counting, finding the bound vertex shader variant, shader matching per object | **Yes, completely**: hook addresses, argument registers, device offsets `+0x330C/+0x3310`, shader object layout (`+872`, `+896`, `+32`; PS `+40`, `+64`, `+24`), command-buffer write pointer `+48`, depth-only variant flag `0x20` |
| `src/frame_capture.cpp/.h` | Turns one draw into `native_view::Draw`: reads vertex layouts from the patched vertex fetch instructions, indices (16/32-bit, restart), VS/PS/boolean constants, texture fetch constants, register shadows (blend, depth, viewport...) | Generic, **but** the device offsets at the top (`kDeviceFetchConstants 0x480`, `kDeviceVertexConstants 0x780`, `kDevicePixelConstants 0x1780`, `kDeviceBooleans 0x2780`, index buffer `0x320C`, render targets `0x3210`, depth `0x3220`, register shadows `0x2880/0x28CC/0x2934`) come from the XDK device layout and must be checked for each game |
| `src/native_view.cpp/.h` | The Vulkan window and replay: EDRAM targets, resolves, clears, bindless textures, pipelines and pipeline cache, FSR 1 / CAS / FXAA, snapshots, dumps, F11/F12 keys | Generic. Rename the env prefix. Remove the `hud_layout` include and its use (a Naruto-only feature) |
| `src/texture_decode.cpp/.h` | Xenos texture fetch constant to Vulkan: untiling, endian swap, formats, cube/3D, BC1-5 to RGBA on the CPU for phones, fingerprints | Generic |
| `src/shader_library.cpp/.h` | Loads the game's shader libraries and the SPIR-V cache, matches microcode (ignoring vertex fetch instructions), saves runtime containers | Library names (`kLibraries`: `nuccMaterial`, `nuccPostEffect`, `runtime`), their file paths, and the env prefix |
| `src/shaders/*.hlsl`, `tools/build-postfx.py`, `src/postfx_spirv.h` | FSR 1, CAS, FXAA, depth24 conversion, compiled to a committed header | Generic (not game-derived, so it can be committed) |
| `tools/build-shaders.py`, `tools/shaders/xenosrecomp-naruto.patch` | Finds 360 shader containers in the library files and runtime captures, XenosRecomp (pinned revision) to HLSL, DXC to SPIR-V, one cache file | `LIBRARIES`, the default paths, the cache name. Check that the patch's fixes still apply to the new game's shaders |
| `src/hud_layout.cpp/.h` | Moves the fight HUD | **Naruto only**: leave it out |
| `tools/run.sh` | Driver choice, SDK library path, `--native` / `--native-only` | Binary name, env prefix |
| `docs/d3d-functions.md`, `config/*_d3d_funcs.toml` | The evidence for each address | Rewrite for each game. The TOML is documentation, not read at run time |

## Porting to a new game

Before this, the game must already boot and run on the SDK's `xenos`
renderer (manifest, function boundaries, kernel fixes). See the project's
own ReXGlue skill. Work in this order, and check each step in the running
game before starting the next.

### 1. Pick a prefix and copy the generic files

Choose an env prefix for the project (the reference uses `REVOLUTION_`,
Storm 3 uses its own). Copy `frame_capture`, `native_view`, `texture_decode`,
`shader_library`, `src/shaders/`, `tools/build-postfx.py`,
`tools/build-shaders.py` and its patch. Then:

```bash
grep -rl REVOLUTION_ src tools | xargs sed -i 's/REVOLUTION_/MYGAME_/g'
```

Remove `hud_layout` from `native_view.cpp`. Add the `.cpp` files to the
sources list in `CMakeLists.txt`. Write a `render_probe.cpp` with **no
addresses yet**: keep the structure, and leave the hooks out until step 2
has found and checked each one.

### 2. Find the game's D3D functions

The XDK's D3D is linked statically into each game, so its functions have no
names. Find them by what they do. For each one, write the address, role,
arguments and evidence in `docs/d3d-functions.md` and the TOML.

| Function | How to recognise it |
| --- | --- |
| `D3DDevice_Swap` (present) | Calls the imports `VdGetSystemCommandBuffer` and `VdSwap`; runs once per frame. Its r3 is the device and r4 the front-buffer texture |
| `DrawIndexedVertices` | `(device, primitive, base vertex, start index, index count)`; reads the index buffer field of the device |
| `DrawVertices` | `(device, primitive, start vertex, vertex count)`; same register-flush structure without indices |
| `ClearF` | flags r4, rects r5, color pointer r6, Z in f1, stencil r8; `Clear` ends up calling it |
| `Resolve` | a small wrapper: flags, source rect, destination texture, point, level, slice, clear color (r10), clear Z (f1) |
| `SetVertexShader` / `SetPixelShader` | store the shader object to the device and set a dirty bit; that store gives the device's shader offsets |
| Shader commit | reads both shader fields and the vertex declaration, emits the shader-load packets |
| Vertex shader patch (in place) and copy+patch (into the command buffer) | walk the shader object's variant table and rewrite vertex fetch instructions for the declaration. **Both are needed**: the patched fetches are the only reliable vertex layout |
| Shader constant, fetch constant, index setters | their stores give the constant, fetch and index buffer offsets |
| The device pointer global | read r3 in the Swap hook (GDB, or a log), then search the image for that value |
| Render/sampler state table | a table of setters then getters at a device offset (the reference: `+0x40`, 121 + 121) |

Methods that worked:

- **Instruction-sequence comparison with a known game.** Disassemble a
  reference function and search the new xex for the same instruction
  sequence, ignoring branch targets and global addresses. A match with the
  same struct offsets and registers is strong evidence. In Revolution the
  whole D3D block had moved by `0x3D400` from Storm 3, but each entry was
  still checked one by one.
- **Count per frame.** Hook a candidate with a one-time log and a counter.
  The draw functions together must account for every draw, and Swap must run
  once per frame.
- **Prove each hook fires.** A hook can be skipped when its caller is in the
  same generated `.cpp` (a direct call). Keep the `static const bool observed`
  one-time log of the reference in each hook until it has been seen.

### 3. Check the device and shader object layout

The offsets come from the XDK version the game was built with, so games
built with the same XDK usually share them. **Check every one** in the new
xex: the setters' store offsets, the commit function's loads, and a live
memory read (`/dev/shm/xenia_memory_*`: virtual address = file offset below
`0xA0000000`; physical at `0x100000000 + (addr & 0x1FFFFFFF)`). Then fix
the `constexpr` lists at the top of `frame_capture.cpp` and
`render_probe.cpp`, with a comment saying where each value was found.

Shader objects: a vertex shader object holds variants (a table of offsets,
8 bytes apart). Its microcode is at physical base + variant offset, with a
size. A pixel shader has one copy. Find these from the commit and patch
functions, not from the reference's numbers.

### 4. Capture, without drawing yet

Turn on `*_RENDER_PROBE=1`. Every 10 seconds the log shows fps, draws per
frame (indexed and non-indexed), primitive types, clears, resolves and their
flags, shader counts, library matches and captured draws per frame.
Captured draws should be close to all draws. If many are not captured, the
log of `Capture` returning false says why (an unknown format or primitive,
a missing shader).

### 5. The shader cache

1. Find the game's shader libraries. They are files of 360 shader
   containers: search the data for the container header
   (`(flags & 0xFFFFFF00) == 0x102A1100`, as `containers()` in
   `build-shaders.py` does). Some games keep them in archives or create them
   at run time. Then the runtime capture is the main source.
2. Set `LIBRARIES` in `build-shaders.py` and `kLibraries` in
   `shader_library.cpp` to them. Keep the cache format and the `runtime`
   library.
3. Build XenosRecomp at the pinned revision with the patch, using tools
   already on the machine. **Ask the user before downloading or building
   anything from outside the project.**
4. `python3 tools/build-shaders.py --game assets`, then run the game.
   Shaders it does not know are saved to `out/shaders/runtime/`. Build the
   cache again and restart, until the probe shows every shader matched.
5. If XenosRecomp mistranslates one of the game's shaders, fix it in the
   patch, not with a substitute shader.

The cache and runtime captures are **derived from the game: never commit
them**. Add `out/` to `.gitignore`.

### 6. The view

Run with `--native` (both windows) and compare the two pictures, then with
`--native-only`. Expect format, blend and resolve cases the reference never
needed. Add them to `frame_capture` / `texture_decode` / `native_view` as
general Xenos code, with comments, so they help the next game as well.

### 7. Settings

The same set as the reference (rename the prefix):

| Variable | Meaning |
| --- | --- |
| `_NATIVE_VIEW=1` | turn on the native view |
| `_NATIVE_VIEW_ONLY=1` | its window only (with `--vulkan_skip_rendering=true`) |
| `_NATIVE_VIEW_SCALE` | 1-4 times the game's resolution (1.5: 720p to 1080p) |
| `_NATIVE_VIEW_UPSCALER` | `fsr` (default), `cas`, `linear` |
| `_NATIVE_VIEW_SHARPNESS` | 0-1, default 0.9 |
| `_NATIVE_VIEW_FXAA=1` | FXAA before scaling |
| `_NATIVE_VIEW_ASPECT` | `16:9` (default), `21:9`..., `fill` |
| `_NATIVE_VIEW_FULLSCREEN=1` | open fullscreen (F11 toggles) |
| `_NATIVE_VIEW_DECOMPRESS=1` | BC textures decoded on the CPU, as on phones |
| `_OUT_DIR`, `_SHADER_CACHE` | where the pipeline cache, snapshots and shader cache are |

## Debugging a wrong picture

1. Screenshot both renderers on the same scene (`--native` shows both).
2. F12 (or Back+R3) saves every pass and the final frame as PPM files and
   logs all draws. `_NATIVE_VIEW_SNAPSHOTS=dir` with `_NATIVE_VIEW_DUMP=n`
   does it for frame n. In the view, Ctrl+Left/Right shows one pass's
   target, and Ctrl+Home goes back.
3. Find the first pass that differs. `_NATIVE_VIEW_DRAW_SNAPSHOTS=p` (and
   `_DRAW_SNAPSHOT_RANGE=a-b`) saves pass p after each draw, to find the
   draw.
4. Check that draw: shader match, vertex attributes (the dump shows the
   Xenos format and swizzles), textures (`_NATIVE_VIEW_TEXTURES=dir` dumps
   them decoded, `_LOG_TEXTURES=1`), state. `_NATIVE_VIEW_DEBUG` bits turn
   off depth testing (1) and culling (2) and flip the winding (4), to
   narrow down state bugs. `_DUMP_VS=offset` logs one vertex shader's
   constants. `_DEPTH_PROBE=x,y` logs depth at a pixel.
5. Fix it, then confirm with a screenshot of the same scene and a clean log.

## Things that went wrong before

- **Vertex layouts from the declaration are not enough.** D3D patches the
  vertex shader's fetch instructions for the declaration, sometimes in a
  copy in the command buffer. Hook both patch paths and read the layout
  from the patched code (`BoundVertexShader` in the reference).
- **Depth-only variants**: a vertex shader can have a second variant used
  when `RB_MODECONTROL`'s EDRAM mode is 5 (depth only). Pick the variant from
  that register, or the layout is wrong.
- **Resolve clear arguments hold leftovers** unless their flag
  (`0x100` / `0x200`) is set.
- **Vertex data reuse**: converted vertex buffers are cached while guest
  memory stays the same (`kVertexStableFrames`, `kVertexIdleFrames`), and
  textures are decoded again only when their fingerprint changes. If a
  picture is stale, suspect these first.
- **A black UI or logos at first start** is usually shaders not yet in the
  cache. Build the cache again after one run.
- Phone GPUs cannot sample BC formats. That is why the CPU decompress path
  exists.

## Rules

- Never trust an address or offset from another game until this game's xex
  confirms it. Write the evidence down.
- Never draw with a similar shader. Match exactly, or capture the shader
  and convert it.
- Never commit game data or anything derived from it (shader cache, runtime
  captures, snapshots, dumps). The post-effect header is fine.
- Never edit `generated/`. Change `src/`, the manifest, or an SDK patch.
- Keep shared fixes generic and commented, so they carry back to the other
  ports.
- Confirm each change in the running game (screenshot and log), and say
  plainly what was and wasn't verified.
