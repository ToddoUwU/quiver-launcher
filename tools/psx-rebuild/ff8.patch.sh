#!/usr/bin/env bash
# FF9's kit pinned its fork's European SCPH5552 BIOS. The new framework links SCPH1001 (the US BIOS, matching the US disc).
T=$1
sed -i '/PSXRECOMP_BIOS_STEMS\|PSXRECOMP_BIOS_STEM \|PSXRECOMP_BIOS_PROFILE/d' "$T/CMakeLists.txt"
sed -i 's|^bios_config = .*|bios_config = "psxrecomp/bios/SCPH1001.toml"|' "$T/game.toml"
