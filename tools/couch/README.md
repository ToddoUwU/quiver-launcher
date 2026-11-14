# tools/couch: hand-installing catalog games and setting them up for couch play

Made 2026-11-13 for the local-multiplayer batch (see ~/CouchGames.md and ~/CouchGamesNeeds.md).

| Script | What it does |
|---|---|
| `quiver-install.py SLUG...` | Installs catalog games the way Quiver does (verified release, checksum, wrapper folder peeled, version.txt, installed-build.txt, filesToAdd) and queues their library entries. `--dry-run` shows the picks. Linux builds first, else the Windows build via Proton (cachyos 11.0). |
| `apply-pending.sh` | Merges the queued entries into apps.json once Quiver has closed (Quiver rewrites apps.json while it runs). Run detached: `systemd-run --user --unit=quiver-apply-couch --collect tools/couch/apply-pending.sh`. |
| `headless-setup.py` | Runs a game in a headless gamescope with every pad hidden, presses keys only inside gamescope's own X server, and stops when a file appears. Used to build libultraship .o2r assets (SpaghettiKart, Starship: ROM in the folder or a stand-in zenity; 2Ship: ROM path as argv). |
| `lus-config.py CFG` | Max graphics for libultraship ports and port 1's gamepad mappings copied to ports 2-4. LUS still makes ports 2-4 ignore every pad at each start, so player 2 picks their pad in the controller window. |
| `sm64coopdx-local` | Two Co-op DX windows side by side on the ASUS: P1 hosts on localhost with gamepad 0, P2 joins with gamepad 1 (muted). Moonlight tile "Mario 64 Co-op (2 players)". |

Never run a game binary outside headless-setup.py (even `--help` opens a window on the real desktop).
