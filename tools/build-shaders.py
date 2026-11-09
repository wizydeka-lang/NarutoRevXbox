#!/usr/bin/env python3
"""Build the native renderer's shader cache from the user's game files.

The game's shaders are Xbox 360 shader containers in
data/system/nuccMaterial_xbox360.nsh and nuccPostEffect_xbox360.nsh, plus the
ones the game captures from memory into out/shaders/runtime/ when it binds a
shader neither file has (vs_<id>.bin, ps_<id>.bin). This converts each one to
HLSL with XenosRecomp (pinned below, with tools/shaders/xenosrecomp-naruto.patch)
and compiles it to SPIR-V with DXC, then writes them all to one cache file. The
cache holds code derived from the game, so it is built locally and never
committed; run this again after playing to convert newly captured shaders.

Cache format (little-endian): b"NSHC", version, entry count; then per entry
the library (0 nuccMaterial, 1 nuccPostEffect, 2 runtime), stage (0 vertex,
1 pixel), two padding bytes, the container's offset in its library file (for
runtime, its id), and the SPIR-V blob's offset in the cache and size; then the
SPIR-V blobs.

Usage: python3 tools/build-shaders.py [--game assets] [--out out/shaders/revolution_shaders.bin]
Uses existing pinned, patched XenosRecomp and DXC tools; never downloads or builds tools.
"""

import argparse
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
XENOSRECOMP_REVISION = "990d03b28a27b50277ee5d8d942e1c5f873869d1"
PATCH = ROOT / "tools" / "shaders" / "xenosrecomp-naruto.patch"
LIBRARIES = ["nuccMaterial", "nuccPostEffect"]
CACHE_VERSION = 2


def run(*args, **kwargs):
    subprocess.run(args, check=True, **kwargs)


def containers(data):
    """Yields (offset, stage, bytes) for each shader container, like XenosRecomp."""
    i = 0
    while i + 36 <= len(data):
        flags, vsize, psize = struct.unpack_from(">III", data, i)
        f1c, f20 = struct.unpack_from(">II", data, i + 28)
        total = vsize + psize
        if (flags & 0xFFFFFF00) == 0x102A1100 and not f1c and not f20 and 0 < total <= len(data) - i:
            yield i, 0 if flags & 1 else 1, data[i:i + total]
            i += total
        else:
            i += 4


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--game", type=Path, default=ROOT / "assets",
                        help="folder holding Default.xex and data/ (default: assets)")
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "shaders" / "revolution_shaders.bin")
    parser.add_argument("--runtime", type=Path, default=ROOT / "out" / "shaders" / "runtime")
    parser.add_argument("--compiler-root", type=Path, required=True,
                        help="existing pinned, patched XenosRecomp source directory")
    parser.add_argument("--compiler", type=Path,
                        help="existing XenosRecomp executable (default: sibling build directory)")
    args = parser.parse_args()

    src = args.compiler_root.resolve()
    recomp = args.compiler or src.parent / "XenosRecomp-build" / "XenosRecomp" / "XenosRecomp"
    revision = subprocess.check_output(["git", "-C", str(src), "rev-parse", "HEAD"], text=True).strip()
    if revision != XENOSRECOMP_REVISION:
        sys.exit(f"Unexpected XenosRecomp revision: {revision}")
    run("git", "-C", str(src), "apply", "--reverse", "--check", str(PATCH))
    if not recomp.is_file():
        sys.exit(f"Shader compiler not found: {recomp}")
    dxc_dir = src / "thirdparty" / "dxc-bin"
    dxc = dxc_dir / "bin" / "x64" / "dxc-linux"
    env = dict(os.environ, LD_LIBRARY_PATH=str(dxc_dir / "lib" / "x64"))
    include = src / "XenosRecomp" / "shader_common.h"

    sources = []  # (library index, name, offset or id, stage, container)
    for library_index, library in enumerate(LIBRARIES):
        path = args.game / "data" / "system" / f"{library}_xbox360.nsh"
        if not path.exists():
            sys.exit(f"{path} not found; point --game at the game files.")
        for offset, stage, blob in containers(path.read_bytes()):
            sources.append((library_index, f"{library}_{offset:08x}", offset, stage, blob))
    for path in sorted(args.runtime.glob("[vp]s_????????.bin")):
        for _, stage, blob in containers(path.read_bytes()):
            sources.append((len(LIBRARIES), f"runtime_{path.stem}", int(path.stem[3:], 16), stage,
                            blob))
            break

    entries, blobs, failed = [], [], []
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for library_index, name, offset, stage, blob in sources:
            container, hlsl, spirv = tmp / f"{name}.bin", tmp / f"{name}.hlsl", tmp / f"{name}.spv"
            container.write_bytes(blob)
            if subprocess.run([str(recomp), str(container), str(hlsl), str(include)],
                              capture_output=True).returncode != 0:
                failed.append((name, ["XenosRecomp failed"]))
                continue
            command = [str(dxc), "-T", "vs_6_0" if stage == 0 else "ps_6_0", "-HV", "2021",
                       "-all-resources-bound", "-spirv", "-fvk-use-dx-layout", "-Qstrip_debug",
                       str(hlsl), "-Fo", str(spirv)]
            if stage == 0:
                command.insert(-3, "-fvk-invert-y")
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            if result.returncode != 0:
                errors = [l for l in result.stderr.splitlines() if "error" in l]
                failed.append((name, errors[:1]))
                continue
            entries.append((library_index, stage, offset))
            blobs.append(spirv.read_bytes())

    header = struct.pack("<4sII", b"NSHC", CACHE_VERSION, len(entries))
    position = len(header) + 16 * len(entries)
    table = b""
    for (library_index, stage, offset), blob in zip(entries, blobs):
        table += struct.pack("<BBxxIII", library_index, stage, offset, position, len(blob))
        position += len(blob)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(header + table + b"".join(blobs))
    print(f"{args.out}: {len(entries)} shaders, {position // 1024} KiB")
    for name, errors in failed:
        print(f"  failed: {name} {re.sub(r'^.*?error', 'error', errors[0]) if errors else ''}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
