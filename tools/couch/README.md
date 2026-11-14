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

## lus-seating/: one controller per player in SpaghettiKart and Starship

Stock libultraship puts every gamepad on port 1 (ports 2-4 ignore them all at each refresh). BattleShip's libultraship
fork and G-Diffuser already seat pads by plug order; SpaghettiKart and Starship are rebuilt with the same logic.

- `apply-seating.py <libultraship checkout>`: the patch (idempotent). Pad N -> port N up to 4, seats kept across
  hot-plug, `LUS_AUTO_SEAT=0` = stock behaviour. Committed on ToddoUwU/libultraship branches PersonalUpdates-SpaghettiKart
  (base f40cfd33) and PersonalUpdates-Starship (base 45c4f8d6).
- `lus-seated GAME [--background] [--force]` (linked in ~/.local/bin): merges the tag in the game's version.txt into
  ~/QuiverLauncher/src/GAME PersonalUpdates (and upstream's libultraship commit into PersonalUpdates-GAME), pushes,
  builds (always inside the 20 GB-capped user unit `lus-seated-GAME`), installs `seated/` in the game folder.
  Conflicts abort and notify. Log: ~/.local/state/quiver/lus-seated-GAME.log.
- `play-seated`: copied (not linked: it finds the game from its own folder) into the game folder and named in its
  selected_executable.txt. Runs seated/ when it matches version.txt, else the release
  AppImage for that session plus a background `lus-seated`.
- `seat-test GAME-FOLDER`: end-to-end check in a headless gamescope. `seat-test-pads.py` plugs virtual pads
  (045e:028e, the only pads the game is allowed to see) 2 -> 4 -> unplugs #2 -> plugs a 5th; passes when the game's
  log reads ports 1 2 3 4 2. Restores the game's cfg. Refuses while a Moonlight stream is live.
- Build packages (apt): libsdl2-net-dev libzip-dev zipcmp zipmerge ziptool nlohmann-json3-dev libtinyxml2-dev
  libspdlog-dev libboost-dev libogg-dev libvorbis-dev (plus libsdl2-dev libpng-dev libopengl-dev, already installed).
