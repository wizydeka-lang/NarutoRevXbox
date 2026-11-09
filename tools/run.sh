#!/usr/bin/env bash
set -euo pipefail
project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
sdk_prefix="${REVOLUTION_SDK_PREFIX:-$HOME/rexglue-sdk/out/install/linux-amd64}"
build_type=release
gpu=nvidia
check=false
native_only=false
native=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --debug) build_type=debug ;;
    --radeon) gpu=radeon ;;
    --nvidia) gpu=nvidia ;;
    --check) check=true ;;
    --native) native=true ;;
    --native-only) native=true; native_only=true ;;
    --) shift; break ;;
    --help|-h)
      printf '%s\n' 'Usage: tools/run.sh [--debug] [--nvidia|--radeon] [--check] [--native|--native-only] [-- game options]'
      exit 0 ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
  esac
  shift
done
build_dir="$project_root/out/build/linux-amd64-$build_type"
suffix=""
[[ "$build_type" == debug ]] && suffix=d
driver="/usr/share/vulkan/icd.d/${gpu}_icd.x86_64.json"
for required in "$build_dir/naruto_revolution" "$build_dir/librexgpu-xenos${suffix}.so"     "$sdk_prefix/lib64/librexruntime${suffix}.so" "$project_root/assets/Default.xex" "$driver"; do
  [[ -r "$required" ]] || { printf 'Missing: %s\n' "$required" >&2; exit 1; }
done
if [[ "$native_only" == true && ! -r "$project_root/out/shaders/revolution_shaders.bin" ]]; then
  printf '%s\n' 'Native shader cache missing. Build it with tools/build-shaders.py first (see README.md).' >&2
  exit 1
fi
if [[ "$check" == true ]]; then
  printf 'Ready: %s\nGPU: %s\n' "$build_dir/naruto_revolution" "$gpu"
  exit 0
fi
export VK_DRIVER_FILES="$driver"
export VK_ICD_FILENAMES="$driver"
export SDL_AUDIO_DRIVER="${SDL_AUDIO_DRIVER:-pipewire}"
export SDL_VIDEO_DRIVER=x11
export LD_LIBRARY_PATH="$sdk_prefix/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export REVOLUTION_OUT_DIR="$project_root/out"
native_args=()
if [[ "$native" == true ]]; then
  export REVOLUTION_NATIVE_VIEW=1
fi
if [[ "$native_only" == true ]]; then
  export REVOLUTION_NATIVE_VIEW_ONLY=1
  native_args=(--vulkan_skip_rendering=true)
fi
cd -- "$project_root"
exec "$build_dir/naruto_revolution" "--game_data_root=$project_root/assets"   --gpu_plugin=xenos --vulkan_device=0 --async_shader_compilation=true "${native_args[@]}" "$@"
