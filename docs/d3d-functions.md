# Revolution D3D functions and native renderer

The runtime hooks in `src/render_probe.cpp` use Revolution addresses independently
verified in this project's translated XEX instructions. The sibling Storm 3
implementation supplied the renderer design, not assumed game addresses.

| Revolution function | Role | Evidence |
| --- | --- | --- |
| `0x82783B48` | Present/swap | Calls VdGetSystemCommandBuffer and VdSwap; submits one native frame per call. |
| `0x8278ECD8` | Indexed draw | Five arguments: device, primitive, base vertex, start index, index count; reads index buffer +0x320C. |
| `0x8278E8C0` | Non-indexed draw | Device, primitive, first vertex, vertex count; same register flush structure. |
| `0x8279A2D8` | ClearF | Flags and color pointer, f1 depth, r8 stencil; called before clear capture. |
| `0x82799148` | Resolve | 19-instruction wrapper, destination surface/texture and source rect arguments. |
| `0x8278A6C8` | SetTexture | Fetch-constant updates, sampler and texture arguments. |
| `0x827874F8` | Patch VS in place | Shader +896 variant table, 416-byte per-variant state, declaration fetch patches. |
| `0x827872F0` | Copy/patch VS | Copies shader into command buffer, leaves write pointer at device +48 on final word. |
| `0x82787638` | Commit shader state | Reads VS +0x3310, PS +0x330C, declaration +0x2FD0; shader IM_LOAD path. |
| `0x8278DC38` / `0x8278DA30` | Set VS / PS | Store at +0x3310 / +0x330C and update dirty flags. |
| `0x82782AD8` | CreateDevice | Called at `0x82831B68` with output pointer in r8. |
| `0x82786508` | Flush register shadows | Writes masked registers, one word per selected bit. |

Full instruction-sequence comparison preserved register operands and struct
immediates, normalizing only code destinations. The matching D3D region is
relocated by 0x3D400 relative to Storm 3, but each chosen entry was inspected.
Differences are image-global addresses, float constant addresses, and dispatch
jump-table offsets (2256 versus 2352); those were not copied into the renderer.

## Device layout

A GDB breakpoint at the actual present-hook entry in run 013 read r3 as
`0x40002E80`. Live memory puts that device pointer at image global `0x82B49904`.
The table at device +0x40 contains 121 setters then 121 getters. Its first ten
entries are engine stubs; remaining entries match the named D3D state functions
listed in `config/revolution_d3d_funcs.toml`.

The shader constant setters (`0x8278D688`, `0x8278D760`), vertex fetch setter
(`0x8277BB58`), index setter (`0x8277B848`), shader commit and draw/resolve paths
verify the offsets used by capture: fetch +0x480; VS/PS float constants
+0x780/+0x1780; booleans +0x2780; indices +0x320C; render targets +0x3210;
depth +0x3220; PS/VS objects +0x330C/+0x3310. Register-shadow groups remain
+0x2880 (0x2000), +0x28CC (0x2100), +0x2934 (0x2200).

Vertex shader containers embed the virtual header at +872, variants at +896,
physical backing pointer at +32, and variant code offset/size at +872/+876.
Pixel containers embed their header at +40, variant table at +64, physical
backing at +24 and offset/size at +40/+44. The verified commit and patch routines
use those exact layouts. Bound patched vertex microcode is captured after the
original draw commits device state.

## Runtime verification

All eight capture hooks logged their first execution in run 013. In a battle,
a measured window had 353.5 indexed plus 58.2 non-indexed draws/frame and 411.7
captured draws/frame. All 116 encountered shader objects matched exact library
or captured-runtime shaders; no similar-shader fallback is used. The native
view sustained about 30 game frames/second after pipeline warm-up. A snapshot
shows Naruto fighting Yamato with the arena, animated characters, effects and HUD.

The SDK command processor remains active, with `--vulkan_skip_rendering=true`
in native-only mode. Presentation, EDRAM targets, resolves, texture decoding and
SPIR-V draw submission are performed by this project's Vulkan renderer.

The first run intentionally captured three sprite shaders absent from the two
.nsh libraries. Rebuilding the cache and restarting resolved the initial black
logo/UI view. Only Revolution's own assets and runtime captures went into its
cache; Storm 3's game-derived cache was not reused.

Evidence stays under ignored `out/`: `native-build.log`, `shader-build.log`,
`native-device.txt`, `native-current.png`, and runtime log 013. An F12-equivalent
request saved the final image and 31 intermediate pass snapshots under
`out/native-snapshots/007545/`, confirming snapshot diagnostics also work. Kernel file-info
warnings remain; no fatal or unregistered-function errors were observed during
this rendering test. Visual parity for every stage, costume and effect is not
established by this initial port.
