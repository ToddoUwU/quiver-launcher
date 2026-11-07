# Rebuilding PS1 recomps on a newer framework

`build-title.sh <short> <Apps folder> <exe>` copies a kit's project files into `~/QuiverLauncher/src/ff-newfw/<short>`, swaps in
psxrecomp 09ba00ed and recomp-ui 3f1d6f12 (the pair Toshinden v0.1.4 shipped), applies `<short>.patch.sh`, then generates and compiles.
The installed game in `Apps/` is never written. Use `GEN_ARGS="--bios /path/SCPH1001.BIN"` for titles that need a retail BIOS.

Each folder here holds the settings and mod choices the rebuild runs with (`$HOME` stands for your home folder). The game's
`play-wayland` runs the rebuild only while `version.txt` matches the kit it was made from, so an official update takes over by itself.
