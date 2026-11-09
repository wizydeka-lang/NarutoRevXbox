// Revolution battle-arena capacity, verified from this game's XEX and a live
// battle-loading failure. sub_826F89F0 allocates (size, arena, tag),
// sub_826F8830 creates (arena, memory, size, alignment), and sub_826F8B18
// creates a top-level arena (arena, size, alignment). Arena 1's 62 MiB pool
// had only two 128-byte units free; the xfbin loader then copied to null+60.
// Grow both its backing allocation and parent pool, including the allocator's
// 1/16 bookkeeping overhead. Never skip the failed copy or write to assets.
#include <rex/hook.h>
#include <rex/logging.h>
#include <rex/memory/utils.h>

#include <cstdint>
#include <cstdlib>

namespace {
constexpr uint32_t kOriginalBattleBytes = 0x03E00000;
constexpr uint32_t kOriginalParentBytes = 0x041E0000;
constexpr uint32_t kArenaTable = 0x82AB3B60;
constexpr uint32_t kArenaStride = 76;
constexpr uint32_t kInitialBattleAllocation = 0x826BDE2C;
constexpr uint32_t kRemadeBattleAllocation = 0x826BDF60;

uint32_t BattleBytes() {
  static const uint32_t bytes = [] {
    const char* value = std::getenv("REVOLUTION_BATTLE_ARENA_MB");
    if (!value) return 128u << 20;
    char* end = nullptr;
    long mb = std::strtol(value, &end, 10);
    return end != value && *end == '\0' && mb >= 62 && mb <= 192
        ? static_cast<uint32_t>(mb) << 20 : 128u << 20;
  }();
  return bytes;
}

uint32_t Load32(const uint8_t* base, uint32_t address) {
  return rex::memory::load_and_swap<uint32_t>(base + address);
}
}

extern "C" {
REX_FUNC(__imp__sub_826F8B18);
REX_FUNC(__imp__sub_826F8830);
REX_FUNC(__imp__sub_826F89F0);
}

REX_HOOK_RAW(sub_826F8B18) {
  if (ctx.r3.u32 == 0 && ctx.r4.u32 == kOriginalParentBytes) {
    ctx.r4.u64 = kOriginalParentBytes +
        (BattleBytes() - kOriginalBattleBytes) / 16 * 17;
    REXLOG_INFO("Battle parent arena: {:.2f} MiB (original {:.2f})",
        ctx.r4.u32 / 1048576.0, kOriginalParentBytes / 1048576.0);
  }
  __imp__sub_826F8B18(ctx, base);
}

REX_HOOK_RAW(sub_826F8830) {
  const bool battle = ctx.r3.u32 == 1 && ctx.r5.u32 == kOriginalBattleBytes;
  if (battle) ctx.r5.u64 = BattleBytes();
  const uint32_t memory = ctx.r4.u32;
  __imp__sub_826F8830(ctx, base);
  if (battle) {
    REXLOG_INFO("Battle arena: {:.2f} MiB at {:08X} (original 62 MiB)",
        BattleBytes() / 1048576.0, memory);
  }
}

REX_HOOK_RAW(sub_826F89F0) {
  const uint32_t caller = static_cast<uint32_t>(ctx.lr);
  if ((caller == kInitialBattleAllocation || caller == kRemadeBattleAllocation) &&
      ctx.r3.u32 == kOriginalBattleBytes) {
    ctx.r3.u64 = BattleBytes();
  }
  const uint32_t size = ctx.r3.u32;
  const int32_t arena = ctx.r4.s32;
  __imp__sub_826F89F0(ctx, base);
  if (!ctx.r3.u32 && size && arena == 1) {
    const uint32_t descriptor = kArenaTable + kArenaStride;
    REXLOG_ERROR("Battle arena allocation failed: {} bytes from {:08X}; "
        "{} bytes free of {}",
        size, caller, Load32(base, descriptor + 20) * Load32(base, descriptor + 8),
        Load32(base, descriptor + 64));
  }
}
