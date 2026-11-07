# Quiver changes, night of 2026-11-06

Status words: **tested** = I ran it and checked the result. **Untested** = not run. Everything game-related ran in a hidden virtual display (gamescope headless), not on your monitors.

## 1. Your second monitor
I don't think my work caused it, but I can't prove that. I assumed "second monitor" means the LG on DP-2.
- My last command that touched anything ran at 22:19. The blank screen appeared around 23:45, 86 minutes later.
- None of my commands changed a display setting.
- Your screens turn off after 30 minutes idle. At 23:45:20 the logs show the desktop panels restarting and the screens reconfiguring, then your login at 23:45:32.
- The kernel logged no display errors. A reboot resets the PC side and didn't help; replugging resets the monitor side and did. That points at the monitor or its link failing to wake.

**Separate problem:** SATA port ata7 failed 91,592 times in the last long uptime and is still failing. No mounted drive sits on it, so a dead drive or loose cable is likely.

## 2. Why upstream rewrote the launcher
Nobody says why they left C#, in anything I could find. What's on record:
- [PR #82](https://github.com/tgeorgiadis/quiver-launcher/pull/82): "Before: a C# Avalonia app that keeps its own catalog by merging GitHub lists into apps.json. After: a Tauri 2 app (React UI, small Rust core) that uses quiverlauncher.com as the only catalog."
- [PR #229](https://github.com/tgeorgiadis/quiver-launcher/pull/229) replaced `main` on 2026-10-31. v3 stays MIT on its own branch; v4 is source-available under the Business Source License 1.1, with a CLA.
- The beta 1 notes say it's "faster, it works with a controller everywhere".

My inference, not their statement: a web UI can share card components with their website (`packages/ui`), v3's history shows repeated Android and Steam Deck fixes, and a single catalog plus accounts suits a hosted service. v3 has had one commit since.

## 3. Games
| Game | Change | Status |
|---|---|---|
| **FF9** | Rebuilt on framework 09ba00ed. 12x (was 4x), US SCPH1001 BIOS so the full real intro plays, PGXP, enhanced audio, CD-speed mods off | **Tested:** New Game, opening, first field scene, candle, naming screen, steady 60 fps. Audio measured only. Battle run was still going when I stopped |
| **FFT** | Rebuilt on the same framework. 12x, widescreen, PGXP, enhanced audio; CD-speed mods off | **Tested:** title, opening, church, first battle, 60 fps |
| **OoT** | No change this round | |

Both wrappers run the rebuild only while `version.txt` matches the version it was made from, so an official update takes over by itself. Saves stay in the game's own `saves` folder.

Known blemishes:
- **FF9:** faint tile seams on pre-rendered backgrounds with bilinear filtering. I compared nearest, xBR and 6x: nearest removes them but looks blocky, xBR adds crosshatching, 6x has the same seams. Bilinear 12x looked best.
- **FFT:** the new framework dropped the call that filled widescreen margins, so the battle view has dark bands and a jagged right edge. To go back to 4:3, set `enabled = false` under `fft.presentation.widescreen` in `~/QuiverLauncher/src/ff-newfw/fft/build-release/mods/state.toml`.
- **Both:** run through XWayland, which is what I tested, not native Wayland. FF9 loads run at original speed.

## 4. Game auto-updates: three real causes
1. **Updates only ran after the first hourly check.** A short session never installed anything. They now start as soon as the library's statuses are fresh.
2. **The second menu you described.** Updating a Windows build opened the Proton dialog every time, and one open dialog held back every later update. My earlier fix missed this. Windows-to-Windows updates now keep their setup; a first install or a switch from Linux still asks. Automatic updates never open a dialog.
3. **Nothing protected a running game.** Automatic updates now wait for it to close, however it was started, and retry every 2 minutes.

Real library, read-only audit: 61 up to date, 0 behind, 6 pinned, 3 rolling, 9 not in the catalog. Star Fox [Enhanced] updated itself at 23:16.

## 5. Automated testing
- **Suite:** 1,828 passed, 0 failed, 8 skipped. It previously had 15 failures and a hang, all from assuming no Wine and no real controllers, plus build servers holding a pipe open.
- **New end-to-end update tests:** first start, Proton, running games.
- **GitHub CI:** `.github/workflows/personal-ci.yml` runs every test on each push to PersonalUpdates.
- **`quiver build`:** a new build only goes live if every test passes.
- **`quiver test`, `quiver audit`:** on demand. `tools/gamesmoke/smoke.py` runs a game hidden with a virtual pad, screenshots and audio levels.

**Not on: the nightly run.** The system blocked me from installing a scheduled job without your approval. To turn it on: `~/QuiverLauncher/quiver-launcher/tools/install-automation`

## 6. Launcher speed
Medians on your 79-game library, in a hidden display.

| | Before | After |
|---|---:|---:|
| First picture | 1.75 s | 0.58 s |
| Library on screen | 3.93 s | 1.06 s |
| CPU used starting | 6.6 s | 2.56 s |
| Idle CPU | 0.5% | 0.3% |
| Memory | 427 MB | 468 MB (worse) |

Measured just before the last small commit. Build size on disk went from 767 MB to 173 MB.

| Change | Why | Guideline |
|---|---|---|
| Stop at the first program found instead of listing every file in every game (1,054 ms to 29 ms) | Biggest gain. Checked against the full scan on all 79 real folders | Avoid unneeded work |
| Run status checks in parallel | They read the disk before their first await, so they ran in sequence | Task-based async |
| Start SDL on a worker thread (346 ms off the UI thread) | **Tested** with a virtual pad | Keep the UI thread free |
| Self-contained composite ReadyToRun build | Almost no JIT at startup | [ReadyToRun](https://learn.microsoft.com/dotnet/core/deploying/ready-to-run) |
| `TieredPGO` off, in this build only | Startup CPU about 20% lower; a launcher doesn't run long hot loops | [Runtime config](https://learn.microsoft.com/dotnet/core/runtime-config/compilation) |
| `[GeneratedRegex]` partial properties for release-file checks | Compiled at build time | [Source generators](https://learn.microsoft.com/dotnet/standard/base-types/regular-expression-source-generators) |
| `params ReadOnlySpan<string>` (C# 13) | No array per call | [Method parameters](https://learn.microsoft.com/dotnet/csharp/language-reference/keywords/method-parameters) |
| Reuse `JsonSerializerOptions` | A new one rebuilds its cache each time | [CA1869](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/ca1869) |
| Fix `HoverScrollText` layout cycle | Measuring during arrange re-ran layout on every hover | Avalonia layout rules |
| Pad polling: 4 times a second with no pad, connection checks twice a second, no per-tick allocation | Less idle work | Avoid hot-path allocation |
| Trace and Avalonia warnings off unless `QUIVER_TRACE=1` | Each line was a syslog call | Diagnostics on demand |
| 256 MB GPU artwork cache; shared immutable brushes; no X11 session management | Fewer re-uploads and allocations | Avalonia options |
| `SHA256.HashData`, char overloads, `Count` checks, no default initializers | Analyzer fixes | CA1850, CA1866/7, CA1860, CA1805, CA1826 |
| `quiver-settings` watcher: 217 ms to 5 ms per pass, mirror once a minute | It ran every 5 s, even during games. Also no longer copies half-unpacked files into the mirror | |

Also fixes the icon margin setting, whose binding always failed. **No features were removed.**

**Guideline check:** C# 14.0 and .NET 10, confirmed from the build (`LangVersion` 14.0, SDK 10.0.113). I ran Microsoft's [CA18xx performance rules](https://learn.microsoft.com/dotnet/fundamentals/code-analysis/quality-rules/performance-warnings): 135 findings, now 0 warnings on every build. Six rules (CA1822, CA1849, CA1861, CA1859, CA1819, CA1815) are lowered to suggestions in `.editorconfig`, with the reason beside each. That covers 87 of the 135 findings, so they were reviewed rather than rewritten.

## 7. Moonlight and Sunshine
- Launching never waits for a rebuild: the working build starts and the new one builds in the background.
- `quiver-tv` waits for a game update to finish unpacking before closing Quiver, then restarts as soon as it has exited instead of sleeping 2 s. New window in 0.27 s (**tested**, hidden display).
- Games and downloads no longer compete: automatic updates wait while you play.
- From the Moonlight tile, your desk pad (045e:0b12) is hidden so it can't take player 1 from Moonlight's pad. **Untested** with a real stream. To undo: `QUIVER_TV_KEEP_LOCAL_PADS=1`.

## 8. Not done or not checked
- **Not tested through a real Moonlight stream or on your real monitors:** the new launcher build or the rebuilt games.
- **Audio by ear:** FF9 and FFT were measured only. FF9 peaks reached 1.0 in the opening movie, so listen for clipping.
- **Battle Arena Toshinden:** still launches v0.1.3.
- **Legend of Dragoon:** the audit should now report it as behind (devbuild vs release-3.0.0); it needs Change Version by hand.
- **FF8 and other PS1 games:** CD-speed problem unchecked.
- **AeroGauge:** run.log shows `aerogauge_modern` needs GLIBC_2.43, which this system lacks. My test pad pressed Play by accident during testing, which may have updated its last-played time.
- **Disc changes** in FF9: untested.

## 9. Going back
- Launcher build: `~/.local/state/quiver/build-before-optimization`
- Scripts: `~/.local/state/quiver/{quiver,quiver-tv,quiver-settings}.before-optimization`
- Games: `play-wayland.bak-2026-11-07` in each game's folder
- Source: `git revert` on PersonalUpdates
