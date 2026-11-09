# Battle loading memory

Run 006 stopped at an unregistered float-return callback, `0x8231AB70`.
The manifest now declares it and 38 matching standalone float-return leaves.

Run 007 passed that failure but stalled in `sub_828F26F0` (memcpy), writing to
`0x0000003C`, called from `0x827374BC`. GDB caught the fault and showed the
xfbin reader stack:

```
828F26F0 <- 82737380 <- 8273B528 <- 826FFBB8 <- 82700A60
```

At `0x8273BA7C`, the reader calls `sub_826F89F0` to allocate its chunk buffer.
The result was zero; it added a 60-byte header and copied to that address.
Live arena 1 at `0x82AB3BAC` had 2 free units of 128 bytes, with one free-list
node totaling 256 bytes. Its total size was `0x03E00000` (62 MiB).

The following addresses were verified in Revolution's own translated
instructions and memory, independently of the Storm 3 reference:

- `sub_826F89F0(size, arena, tag)` allocates through a table of 76-byte arena
  descriptors at `0x82AB3B60`; `sub_826F8540` handles the free list.
- `sub_826F8830(id, memory, size, alignment)` initializes the arena and stores
  its backing address at +60, size at +64, unit size at +8, free units at +20.
- `sub_826F8B18(id, size, alignment)` takes the backing memory from the main heap
  and calls the initializer. The parent size is `0x041E0000` (62 MiB * 17/16).
- Config table `0x820BC4E8` sets arena 1 to 62 MiB. Its initial backing allocation
  returns at `0x826BDE2C` and initialization returns at `0x826BDE54`.
- Battle reset allocates the same hardcoded 62 MiB, returning at `0x826BDF60`,
  then initializes arena 1, returning at `0x826BDF7C`.

`src/battle_memory.cpp` grows the battle pool to 128 MiB at both creation paths,
and grows the parent by the difference plus 1/16 for bookkeeping (136 MiB).
It changes arguments to original functions, leaving allocator and loader logic
intact. `REVOLUTION_BATTLE_ARENA_MB=62` restores the original capacity;
valid values are 62 through 192, with 128 as the default. Allocation failures
in arena 1 are logged with their size, caller and remaining free bytes.

Run 008 confirms that hooks execute: startup logs report a 136 MiB parent and
128 MiB battle arena. The next attempt passed the previous null-copy failure but stopped at a separate
unregistered nullable forwarding callback, `0x825DA738`, called from
`0x82604C1C`. Its 32-byte body was verified and declared in the manifest.
Run 010 reached a playable Naruto-versus-Sasuke battle on a grassy stage;
screenshots show both HUDs, character movement/attacks and the timer at 85.
No battle allocation or missing-model diagnostics fired. The later fault with
LR `0x82828470` occurred when the user closed/exited the game (confirmed by the
user), rather than during play. It dereferences the heap's null +3596 lookup
table from a background thread and is tracked separately as an exit-time issue.
The temporary character-model diagnostic was removed after this verification.

A run 009 null model-resource read during battle setup was not reproduced in
run 010 and remains unclassified; shutdown timing may be relevant. Testing one
match does not establish coverage of every character/costume/support combination.
Rendering artifacts, including large colored polygons, remain visible and were
not addressed by the CPU dispatch and arena-capacity fixes.
