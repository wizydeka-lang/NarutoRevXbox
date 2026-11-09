# Initial function boundaries

The first analysis reported 13 unresolved direct tail-branch targets. Each was
inspected in the decrypted, basic-compression-expanded image of this project's
`assets/Default.xex`, using LLVM PowerPC disassembly. Explicit sizes stop at the
next verified function boundary. Comments in the manifest describe each entry.

The missing targets included six-instruction interface thunks and a two-instruction
`this` adjustment thunk. The entire executable section was scanned for these
exact instruction patterns, as well as the standard four-instruction vtable thunk.
Matches were checked against generated control flow and added with exact instruction lengths to avoid repeated runtime
failures from the same patterns. No Storm 3 addresses were used.

`0x8281E008` is a wrapper that loads TLS slot 84 into r7 and tail branches to
`0x8281DEA8`; it does not share the destination's prologue or stack frame.

Generated registration and linked symbols are checked during builds. Runtime
coverage remains separate from those static checks.

Code emission exposed a byte-string parser split at `0x82816F44` whose decimal
loop branches backward to the shared error return at `0x82816F3C`. Its actual
entry is `0x82816E80`, ending before the next parser at `0x82816F98`; that whole
280-byte range is declared explicitly. The pair at `0x828F8564` matched the
adjustment thunk pattern but belongs to the strlen loop at `0x828F8500` and
was excluded.

Runtime startup uncovered a callback at `0x826C6228` (28 bytes) and a nullable
member dispatch wrapper at `0x8268B590` (36 bytes). Both were disassembled before
being declared. Scanning the executable for the nullable member wrapper and the
four-instruction r11-based vtable thunk initially found 135 candidates. Control-flow review excluded 98 interior dispatch
sequences; 37 standalone entries were retained. These patterns end
in an indirect tail branch and have no stack frame.

The third run rendered Bandai Namco and CyberConnect2 logos, then reached the
embedded-interface thunk at `0x827AD088`. The matching pair at `0x827AD070` and
`0x827AD088` loads object +72, adjusts to its +64 interface and dispatches through
the vtable. Both are declared as 24-byte functions.

The fourth run reached the autosave notice, then the movie callback
`0x828B74E0`, which returns `0x8000` in three instructions. It is declared with
12 bytes, ending at padding. Its adjacent 8-byte member forwarding function
`0x828B74F0` is also declared.

The fifth run reached the one-instruction thunk `0x82931D78`, a tail branch to
`0x82931A30`. Scanning for a single unlinked relative branch followed by zero
padding, with an aligned pointer in read-only data and an executable target,
added 131 entries. Codegen reported no unresolved branches afterward.

## Battle setup callback

The first battle attempt in run 006 stopped at `0x8231AB70`, called from
`0x825ABB7C` with r3=`0x45D20310`. Disassembly verifies `lis r11`; `lfs f1` from
read-only data; `blr`, ending before zero padding at `0x8231AB7C`. It returns a
constant float and has no stack frame.

A scan found 49 instances of this instruction pattern with constants in .rdata.
Control-flow review excluded 10 embedded return blocks whose preceding code
falls through. The 39 standalone leaves were added with exact 12-byte sizes.
