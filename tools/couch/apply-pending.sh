#!/bin/bash
# Adds the games quiver-install.py queued (staging/couch/pending-entries.json) to Quiver's library.
#
# Quiver keeps apps.json in memory and writes it back, so the merge only happens while Quiver is closed:
#   apply-pending.sh          wait for Quiver to close (checks every 20 s), then merge
#   apply-pending.sh --now    merge only if Quiver is not running
# Run it detached so it survives this shell:
#   systemd-run --user --unit=quiver-apply-couch --collect tools/couch/apply-pending.sh
# Entries already in the library (same folderName) are updated in place, keeping your own fields; new ones are
# appended. apps.json is backed up first. Log: ~/.local/state/quiver/staging/couch/apply.log
set -u
Q=$HOME/.local/share/QuiverLauncher
P=$HOME/.local/state/quiver/staging/couch/pending-entries.json
LOG=$HOME/.local/state/quiver/staging/couch/apply.log
exec >>"$LOG" 2>&1
echo "== $(date '+%F %T') apply-pending ($*)"
[[ -s $P ]] || { echo "nothing pending"; exit 0; }
while pgrep -x QuiverLauncher. >/dev/null || pgrep -f 'QuiverLauncher\.Desktop$' >/dev/null; do
  [[ ${1:-} == --now ]] && { echo "Quiver is running: nothing done"; exit 1; }
  sleep 20
done
sleep 3
cp -p "$Q/apps.json" "$Q/apps.json.bak-$(date +%Y-%m-%d-%H%M)-couch" || { echo "backup failed: nothing done"; exit 1; }
python3 -I - "$Q/apps.json" "$P" <<'EOF'
import json, os, sys
lib_path, pending_path = sys.argv[1:]
raw = open(lib_path, encoding="utf-8-sig").read()
lib = json.loads(raw)
pending = json.load(open(pending_path, encoding="utf-8"))
by_folder = {a.get("folderName"): a for a in lib["apps"]}
added, updated = [], []
for e in pending:
    cur = by_folder.get(e["folderName"])
    if cur is None:
        lib["apps"].append(e); added.append(e["name"])
    else:
        for k, v in e.items():
            if cur.get(k) in (None, [], "") or k in ("linuxRunner", "linuxPrefixPath", "linuxProtonPath"):
                cur[k] = v
        updated.append(e["name"])
tmp = lib_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(lib, f, indent=2, ensure_ascii=False)
os.replace(tmp, lib_path)
done = pending_path.replace(".json", ".applied.json")
os.replace(pending_path, done)
print(f"added {len(added)}: {', '.join(added)}")
print(f"updated {len(updated)}: {', '.join(updated)}")
EOF
rc=$?
echo "== $(date '+%F %T') done (rc=$rc)"
[[ $rc == 0 ]] && notify-send -a Quiver "New couch games added" "Open Quiver: the new games are in the library. Details: $LOG" 2>/dev/null
exit $rc
