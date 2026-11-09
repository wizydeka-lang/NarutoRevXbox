#!/usr/bin/env python3
"""Export the reusable ReXGlue/Xenos Vulkan renderer without game data."""

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


HOOKS = {
    "present": "82783B48",
    "draw_indexed": "8278ECD8",
    "draw": "8278E8C0",
    "clear": "8279A2D8",
    "resolve": "82799148",
    "set_texture": "8278A6C8",
    "patch_vertex_shader": "827874F8",
    "copy_vertex_shader": "827872F0",
}
CORE = (
    "frame_capture.cpp", "frame_capture.h", "native_view.cpp", "native_view.h",
    "texture_decode.cpp", "texture_decode.h", "shader_library.cpp",
    "shader_library.h", "hud_layout.h", "postfx_spirv.h",
)

CONFIGURATOR = r'''#!/usr/bin/env python3
"""Configure a renderer adapter from independently verified target addresses."""
import argparse
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import tomllib

ROOT = Path(__file__).resolve().parent.parent
HOOKS = @HOOK_NAMES@

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    args = parser.parse_args()
    profile = tomllib.loads(args.profile.read_text())
    project = profile.get("project", {})
    name = project.get("name", "")
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", name):
        raise ValueError("project.name must be an identifier (hyphens are allowed)")
    if project.get("layout") != "xdk-330c":
        raise ValueError("Supported layout: xdk-330c; other XDK layouts require capture changes")
    hooks = profile.get("hooks", {})
    if set(hooks) != set(HOOKS):
        raise ValueError("hooks must contain exactly: " + ", ".join(HOOKS))
    for role, address in hooks.items():
        if type(address) is not int or not 0x10000 <= address < 0xA0000000 or address % 4:
            raise ValueError(f"{role}: supply a nonzero, aligned guest code address")
    if len(set(hooks.values())) != len(HOOKS):
        raise ValueError("Hook addresses must be distinct")
    libraries = profile.get("shader_libraries", [])
    if not isinstance(libraries, list) or len(libraries) > 254:
        raise ValueError("shader_libraries must be an array of at most 254 tables")
    names, paths = [], []
    for library in libraries:
        library_name, path = library.get("name"), library.get("path")
        if not isinstance(library_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", library_name):
            raise ValueError("Each shader library needs an identifier name")
        if library_name == "runtime" or library_name in names:
            raise ValueError("Shader library names must be unique; runtime is reserved")
        if not isinstance(path, str) or not path or "\\" in path:
            raise ValueError("Shader library paths must be relative paths using forward slashes")
        if PurePosixPath(path).is_absolute() or PureWindowsPath(path).drive or ".." in PurePosixPath(path).parts:
            raise ValueError("Shader library paths must stay inside the target game root")
        names.append(library_name)
        paths.append(path)
    template = (ROOT / "templates/render_hooks.cpp.in").read_text()
    for role, address in hooks.items():
        template = template.replace("@" + role + "@", f"{address:08X}")
    if re.search(r"@[a-z_]+@", template):
        raise ValueError("Unresolved adapter template token")
    def array(name, items):
        return (f"inline constexpr std::array<const char*, {len(items)}> {name} = {{" +
                ", ".join(json.dumps(item) for item in items) + "};\n")
    header = "// Generated from renderer.toml; configure again after changing the profile.\n"
    header += "#pragma once\n#include <array>\nnamespace rex_native_profile {\n"
    header += array("kLibraries", names + ["runtime"])
    header += array("kLibraryPaths", paths)
    header += "inline constexpr const char* kWindowTitle = " + json.dumps(name + " - native renderer") + ";\n}\n"
    # Validate everything before replacing the three configured outputs.
    (ROOT / "src/renderer_profile.h").write_text(header)
    (ROOT / "src/render_hooks.cpp").write_text(template)
    (ROOT / "renderer.toml").write_text(args.profile.read_text())
    print(f"Configured {name}: {len(hooks)} hooks, {len(libraries)} libraries plus runtime captures")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, TypeError, AttributeError, tomllib.TOMLDecodeError) as error:
        print(f"Renderer profile error: {error}", file=sys.stderr)
        sys.exit(1)
'''

CMAKE = '''# Call after rexglue_setup_target() on the host executable.
function(rex_native_attach target)
    if(NOT TARGET "${target}")
        message(FATAL_ERROR "rex_native_attach needs an existing ReXGlue host target")
    endif()
    set(renderer_root "${CMAKE_CURRENT_FUNCTION_LIST_DIR}")
    if(NOT EXISTS "${renderer_root}/src/render_hooks.cpp" OR
       NOT EXISTS "${renderer_root}/src/renderer_profile.h")
        message(FATAL_ERROR "Configure the renderer first: python3 tools/configure.py --profile target.toml")
    endif()
    target_sources(${target} PRIVATE
        "${renderer_root}/src/render_hooks.cpp"
        "${renderer_root}/src/frame_capture.cpp"
        "${renderer_root}/src/native_view.cpp"
        "${renderer_root}/src/texture_decode.cpp"
        "${renderer_root}/src/shader_library.cpp"
        "${renderer_root}/src/hud_layout.cpp")
    target_include_directories(${target} PRIVATE "${renderer_root}/src")
    target_compile_features(${target} PRIVATE cxx_std_23)
    target_link_libraries(${target} PRIVATE rex::runtime)
endfunction()
'''

README = '''# ReXNative renderer toolkit

Source toolkit for ReXGlue Xbox 360 recompilations with a compatible XDK D3D
device layout. Provides Vulkan presentation, EDRAM targets, resolves, texture
decoding, exact shader matching, FSR 1/CAS/FXAA and frame/pass/draw snapshots.
It is not a renderer for arbitrary PC, PlayStation or unrelated engine APIs.

This export contains no game files, translated CPU code, executable, shader
cache or runtime shader captures. Post-processing SPIR-V is built from the
included generic HLSL. Third-party notices remain in third_party/.

## Integrate

1. Independently map the new game's eight hook entry points and verify their
   argument registers and struct offsets. Start with target.example.toml.
   Zero addresses deliberately fail configuration. The tested xdk-330c layout
   uses fetch constants +0x480, VS/PS constants +0x780/+0x1780, booleans +0x2780,
   indices +0x320C, targets +0x3210, depth +0x3220 and PS/VS +0x330C/+0x3310.
   Shader objects, resource headers and register shadows also need checking
   against render_hooks.cpp.in and frame_capture.cpp before running a new game.
2. Set shader_libraries to that game's container library paths, relative to
   its asset root. Use an empty array for runtime-capture-only discovery.
   These must be Xenos shader containers; engine-specific archives need an
   extraction/scanning adapter first. Library order is part of the cache format.
3. Run `python3 tools/configure.py --profile /path/to/target.toml`.
4. In the host project's CMakeLists.txt, after its rexglue_setup_target call:

   ```cmake
   add_subdirectory(path/to/rex-native)
   rex_native_attach(your_game_target)
   ```

   C++23 and the host SDK's Vulkan, SDL3 and xxhash headers are required. Attach
   sources directly to the host so strong hooks cannot be discarded as unused
   members of a static archive. Remove any older hooks for these same entries.
5. Compile the target game's cache using an existing pinned, patched compiler:

   ```sh
   python3 tools/build-shaders.py --game /path/to/assets --out /path/to/out/shaders/native_shaders.bin --runtime /path/to/out/shaders/runtime --compiler-root /path/to/XenosRecomp
   ```

   The compiler revision and patch are checked; tools are never downloaded or
   built automatically. For post-processing rebuilds, run build-postfx.py with
   --dxc-dir pointing to an existing DXC distribution. See the included patch.
6. Run with X360NR_NATIVE_VIEW=1 and X360NR_OUT_DIR set to an absolute output
   directory. Pass the host's normal --game_data_root and --gpu_plugin=xenos.
   X360NR_NATIVE_VIEW_ONLY=1 plus --vulkan_skip_rendering=true selects native-only
   drawing. The SDK command processor still runs. Use an absolute
   X360NR_SHADER_CACHE override if the cache is elsewhere.

Warm up uncached scenes with both windows, compile captured runtime shaders and
restart before judging the image. Missing shaders are reported and captured;
similar shaders are never substituted. X360NR_RENDER_PROBE=1 reports counts.
Check every first-hook log, compare draw counts and the same scene against the
SDK renderer, then inspect F12 snapshots to narrow visual differences to a draw.
Registration/symbol checks alone do not prove capture hooks actually execute.

Settings use X360NR_NATIVE_VIEW_ followed by SCALE (1–4, default 1.5), UPSCALER
(fsr/cas/linear), SHARPNESS (0–1), FXAA, ASPECT, FULLSCREEN, SNAPSHOTS,
DRAW_SNAPSHOTS, DRAW_SNAPSHOT_RANGE, TEXTURES, DECOMPRESS, DUMP or DEBUG.
The capture structs currently assume the tested XDK resource/shader layout;
different layouts and hook ABIs require adapting the source, not just addresses.
HUD repositioning is disabled: the original game's HUD heuristics are not
portable. Game-specific fixes, save changes and roster unlocks are omitted.

Keep target assets, generated CPU code, game-derived shaders and output caches
out of version control. Porting this toolkit does not verify another game's
rendering; record which target scenes, effects and platforms were actually tested.
'''


def export(source, destination, profile):
    if destination.exists():
        raise ValueError("Output already exists; choose a new directory to preserve existing work")
    required = [source / "src" / name for name in CORE]
    required += [source / "src/render_probe.cpp", source / "src/shaders",
                 source / "third_party", source / "tools/build-shaders.py",
                 source / "tools/build-postfx.py", source / "tools/shaders/xenosrecomp-naruto.patch"]
    for path in required:
        if not path.exists():
            raise ValueError(f"Required renderer source missing: {path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Build in a sibling staging directory so a failed configuration leaves no partial kit.
    with tempfile.TemporaryDirectory(prefix=".rex-native-", dir=destination.parent) as staging:
        root = Path(staging) / "kit"
        for directory in ["src", "tools/shaders", "templates"]:
            (root / directory).mkdir(parents=True)
        for name in CORE:
            text = (source / "src" / name).read_text()
            text = text.replace("REVOLUTION_", "X360NR_").replace("naruto_revolution", "ReXNative")
            text = text.replace("revolution_shaders.bin", "native_shaders.bin")
            text = text.replace("Naruto - native renderer", "ReXNative")
            text = text.replace("Revolution native view", "ReXNative")
            if name == "native_view.cpp":
                text = text.replace('#include "native_view.h"', '#include "native_view.h"\n#include "renderer_profile.h"')
                text = text.replace('"ReXNative", width, height,', 'rex_native_profile::kWindowTitle, width, height,')
            if name == "shader_library.cpp":
                text = text.replace('#include "shader_library.h"', '#include "shader_library.h"\n#include "renderer_profile.h"')
                text = text.replace('const char* const kLibraries[] = {"nuccMaterial", "nuccPostEffect", "runtime"};',
                                    'const auto& kLibraries = rex_native_profile::kLibraries;')
                text = text.replace('for (const char* name : {kLibraries[0], kLibraries[1]}) {\n    ScanLibrary(game_data_root / "data" / "system" / (std::string(name) + "_xbox360.nsh"), name);',
                                    'for (size_t i = 0; i < rex_native_profile::kLibraryPaths.size(); ++i) {\n    ScanLibrary(game_data_root / rex_native_profile::kLibraryPaths[i], kLibraries[i]);')
                text = text.replace('kLibraries[2]', 'kLibraries.back()')
                if 'std::string(name) + "_xbox360.nsh"' in text or 'const char* const kLibraries[]' in text:
                    raise ValueError("Shader library source changed; update exporter transformations")
            (root / "src" / name).write_text(text)
        (root / "src/hud_layout.cpp").write_text(
            '#include "hud_layout.h"\nnamespace hud_layout {\n'
            'std::vector<Transform> Transforms(const native_view::FrameInfo&) { return {}; }\n}\n')
        hooks = (source / "src/render_probe.cpp").read_text()
        hooks = hooks[hooks.index("#include"):]
        hooks = "// Target D3D adapter; generated from verified hook addresses.\n" + hooks
        hooks = hooks.replace("REVOLUTION_", "X360NR_")
        for role, address in HOOKS.items():
            hooks = hooks.replace(address, "@" + role + "@")
        if re.search(r"sub_[0-9A-Fa-f]{8}", hooks):
            raise ValueError("Unmapped game function in adapter; update the exporter")
        (root / "templates/render_hooks.cpp.in").write_text(hooks)
        for name in ["build-shaders.py", "build-postfx.py"]:
            text = (source / "tools" / name).read_text().replace("revolution_shaders.bin", "native_shaders.bin")
            if name == "build-shaders.py":
                text = text.replace("import tempfile", "import tempfile\nimport tomllib")
                text = text.replace('LIBRARIES = ["nuccMaterial", "nuccPostEffect"]\n', '')
                text = text.replace('    args = parser.parse_args()',
                                    '    args = parser.parse_args()\n    libraries = tomllib.loads((ROOT / "renderer.toml").read_text()).get("shader_libraries", [])')
                text = text.replace('for library_index, library in enumerate(LIBRARIES):\n        path = args.game / "data" / "system" / f"{library}_xbox360.nsh"',
                                    'for library_index, entry in enumerate(libraries):\n        library = entry["name"]\n        path = args.game / entry["path"]')
                text = text.replace('len(LIBRARIES)', 'len(libraries)')
                if "enumerate(LIBRARIES)" in text:
                    raise ValueError("Shader compiler source changed; update exporter transformations")
            (root / "tools" / name).write_text(text)
        shutil.copyfile(source / "tools/shaders/xenosrecomp-naruto.patch",
                        root / "tools/shaders/xenosrecomp-naruto.patch")
        shutil.copytree(source / "src/shaders", root / "src/shaders")
        shutil.copytree(source / "third_party", root / "third_party")
        (root / "tools/configure.py").write_text(CONFIGURATOR.replace("@HOOK_NAMES@", repr(list(HOOKS))))
        (root / "CMakeLists.txt").write_text(CMAKE)
        (root / "README.md").write_text(README)
        (root / ".gitignore").write_text('/out/\n/assets/\n/generated/\n__pycache__/\n')
        example = ('# Replace zeroes only after verifying the target XEX and hook ABIs.\n'
                   '[project]\nname = "my_game"\nlayout = "xdk-330c"\n'
                   'shader_libraries = [] # Put [[shader_libraries]] at top level instead.\n\n[hooks]\n')
        example = example.replace('shader_libraries = [] # Put [[shader_libraries]] at top level instead.\n', '')
        example += ''.join(f'{role} = 0x00000000\n' for role in HOOKS)
        example += ('\n# Optional container libraries; omit for runtime-capture-only discovery.\n'
                    '# [[shader_libraries]]\n# name = "material"\n# path = "data/system/material_xbox360.nsh"\n')
        (root / "target.example.toml").write_text(example)
        if profile:
            subprocess.run([sys.executable, str(root / "tools/configure.py"), "--profile", str(profile)], check=True)
        root.rename(destination)
    print(f"Exported renderer toolkit to {destination}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[4],
                        help="renderer source project (defaults to this skill's project)")
    parser.add_argument("--output", type=Path, required=True, help="new toolkit directory")
    parser.add_argument("--profile", type=Path, help="optional verified target TOML; otherwise export an unconfigured kit")
    args = parser.parse_args()
    export(args.source.resolve(), args.output.resolve(), args.profile.resolve() if args.profile else None)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Renderer export failed: {error}", file=sys.stderr)
        sys.exit(1)
