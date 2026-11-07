#!/usr/bin/env bash
# Rebuild one psxrecomp title on the newer framework, in its own folder. The installed game in Apps/ is never written.
# usage: build-title.sh <short-name> <Apps folder name> <exe basename>
set -uo pipefail
W=$HOME/QuiverLauncher/src/ff-newfw; SHORT=$1; KIT=$HOME/.local/share/QuiverLauncher/Apps/$2; EXE=$3; T=$W/$SHORT
log(){ printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }
mkdir -p "$T"
log "copy project files"
rsync -a --exclude /build-release --exclude /generated --exclude /psxrecomp --exclude /recomp-ui --exclude /saves \
  --exclude "/$EXE" --exclude 'settings.toml*' --exclude 'selected_executable*' --exclude 'play-wayland*' --exclude 'psx_last_run_report.json' \
  --exclude 'quiver-launch.log' --exclude 'LastPlayed.txt' --exclude 'installed-build.txt' --exclude "/mods/state.toml*" --exclude /mods/bundled "$KIT/" "$T/"
rsync -a --delete --exclude /generated --exclude /recompiler/build --exclude /bios/SCPH1001.BIN "$W/psxrecomp/" "$T/psxrecomp/"
rsync -a --delete "$W/recomp-ui/" "$T/recomp-ui/"
[ -e "$KIT/psxrecomp/bios/SCPH5552.BIN" ] && cp -n "$KIT/psxrecomp/bios/SCPH5552.BIN" "$T/psxrecomp/bios/"
[ -x "$W/$SHORT.patch.sh" ] && "$W/$SHORT.patch.sh" "$T"
{ echo "psxrecomp=$(git -C "$W/psxrecomp" rev-parse HEAD)"; echo "recomp-ui=$(git -C "$W/recomp-ui" rev-parse HEAD)"; } > "$T/framework_pins.txt"
. "$HOME/.local/share/retcomm/toolchains/cmake-clang-v1/latest/env.sh"
export CMAKE_BUILD_PARALLEL_LEVEL=10 NINJAFLAGS=-j10
cd "$T" || exit 1
log "generate"
python3 psxrecomp/psxrecomp_cli.py generate --config game.toml --project-root . --no-toolchain-download ${GEN_ARGS:-} || { log "GENERATE FAILED rc=$?"; exit 2; }
log "rebuild"
python3 psxrecomp/psxrecomp_cli.py rebuild --config game.toml --project-root . --build-dir build-release --target psx-runtime --exe-basename "$EXE" --no-pgo --no-toolchain-download --cmake-extra=-DCMAKE_DISABLE_FIND_PACKAGE_OpenSSL=ON || { log "REBUILD FAILED rc=$?"; exit 3; }
log "done: $(ls -la "$T/build-release/$EXE" 2>&1)"
