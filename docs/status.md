# Current status

The Linux Release build passes all 501 explicit-function registration and
linked-symbol checks. A playable Naruto-versus-Sasuke battle was verified in
run 010 after fixing missing battle callbacks and expanding the battle arena
from 62 to 128 MiB (136 MiB parent including bookkeeping).

The user navigated with a controller and confirmed the later run 010 error
happened after closing/exiting the game. That exit-time background-thread fault
is separate from the battle-entry failure. A run 009 null resource read remains
unclassified and was not reproduced in run 010; all roster combinations are not
verified. The native Vulkan renderer is now ported and verified separately in run 013:
Naruto-versus-Yamato gameplay rendered with SDK GPU drawing disabled, about
30 game frames/second after warm-up, and all 116 encountered shader objects
matched. See `docs/d3d-functions.md`. Rendering parity across all content remains
unverified.

See `docs/battle-memory.md` for exact failure evidence, verified Revolution
addresses and the capacity setting. Local evidence: run 007's fault/backtrace,
run 010's log, and `out/battle-running.png` showing the live fight.

No game assets or shared SDK files were changed. No commits were made.

## Earlier first-boot milestone

The Linux Release executable `naruto_revolution` builds and links using the
installed ReXGlue SDK. Codegen finishes without unresolved-branch warnings.
At that milestone, all 461 explicit manifest entries pass generated-registration and linked-symbol
checks.

Runtime verification used the SDK Xenos Vulkan plugin on the NVIDIA RTX 2050.
Screenshots confirmed startup logos, the autosave notice, intro video, title
screen and the new-save-data prompt after pressing Start. K acts as A and Enter
as Start. Gameplay has not been tested. The native renderer has not been ported.

Run 006 has no fatal, unregistered-function or access-violation messages through
the save prompt. It still logs unimplemented
`NtQueryInformationFile(XFileXctdCompressionInformation)` calls and an async
placeholder presentation warning. The intro video showed visible color/artifact
issues; rendering correctness beyond the title UI needs investigation.

The supplied assets display “Storm 4 Revolution Road to Boruto” title artwork;
this is not a verified vanilla asset set. The test used the existing Xbox asset
root without mounting the separate PC patchdata package. No game files or shared
SDK files were changed.

Local evidence (excluded from Git):
- `out/build.log`: successful build and 461-entry verification.
- `out/codegen.log`: clean final codegen.
- `out/build/linux-amd64-release/logs/naruto_revolution_006.log`: runtime log.
- `out/menu-check.png`: title screen.
- `out/start-menu.png`: new-save prompt.
- `out/movie-start.png`: intro video with rendering artifacts.

The test game was left running at the new-save prompt. No save creation was
confirmed. No commits were made.
