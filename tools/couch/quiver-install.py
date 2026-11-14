#!/usr/bin/env python3
"""Install catalog games into the Quiver library by hand, the way Quiver itself would.

Quiver's own --download refuses ("No eligible download"), and apps.json must not be edited while Quiver runs
(it rewrites the file from memory). So this script:

  1. reads the app and its release history from the public quiverlauncher.com API,
  2. picks the release Quiver has verified and the asset for this machine (a Linux build when there is one, else the
     Windows build, run through Proton),
  3. downloads it, checks the sha256 Quiver pinned, and unpacks it into Apps/<folder> (a lone wrapper folder is
     peeled off, like Quiver does), then writes version.txt, installed-build.txt and the catalog's filesToAdd,
  4. writes the library entry (same fields as QuiverCatalogMapping.ToListEntry) to the pending file.

apply-pending.sh merges the pending entries into apps.json once Quiver has closed.

Usage: quiver-install.py [--dry-run] [--asset SLUG=FILENAME ...] SLUG...
"""
import argparse, fnmatch, hashlib, json, os, re, shutil, subprocess, sys, tarfile, tempfile, urllib.request, zipfile
from pathlib import Path

API = "https://api.quiverlauncher.com/api/v1"
HOME = Path.home()
LIB = HOME / ".local/share/QuiverLauncher"
APPS = LIB / "Apps"
STAGE = HOME / ".local/state/quiver/staging/couch"
PENDING = STAGE / "pending-entries.json"
PROTON = HOME / ".steam/debian-installation/compatibilitytools.d/proton-cachyos-11.0-20261005-slr-x86_64_v3/proton"
UA = {"User-Agent": "QuiverLauncher"}

SKIP = re.compile(r"(?i)(arm64|aarch64|android|\.apk$|flatpak|steamdeck|switch|\.nro$|ps5|\.dmg$|macos|mac-|osx|"
                  r"\.txt$|\.sha256$|\.sig$|\.asc$|symbols|debug|pdb)")


def get(path):
    with urllib.request.urlopen(urllib.request.Request(API + path, headers=UA), timeout=60) as r:
        return json.load(r)


def pick_release(app, history):
    want = (app.get("verified") or {}).get("version")
    items = history.get("items", [])
    for r in items:
        if r.get("version") == want:
            return r
    verified = [r for r in items if r.get("state") == "verified"]
    return verified[0] if verified else None


def pick_asset(app, release, override=None):
    assets = release.get("assets", [])
    if override:
        return next(a for a in assets if a["filename"] == override), override.lower().endswith(".exe") or "win" in override.lower()
    launcher = app.get("launcher") or {}
    pref = (launcher.get("preferredExecutables") or {})
    usable = [a for a in assets if not SKIP.search(a["filename"])]
    linux = [a for a in usable if re.search(r"(?i)linux|appimage|\.elf$|x86_64\.tar|-x64\.tar", a["filename"])
             and not re.search(r"(?i)win", a["filename"])]
    for pat in pref.get("linux", []):
        for a in linux:
            if fnmatch.fnmatch(a["filename"], pat):
                return a, False
    if linux:
        linux.sort(key=lambda a: (not re.search(r"(?i)x86_64|x64|amd64", a["filename"]),
                                  not a["filename"].lower().endswith((".tar.gz", ".tgz", ".zip", ".tar.xz")),
                                  a["filename"]))
        return linux[0], False
    win = [a for a in usable if re.search(r"(?i)win|\.exe$|x64\.zip|pc", a["filename"])]
    if not win:
        win = [a for a in usable if a["filename"].lower().endswith(".zip")]
    if win:
        win.sort(key=lambda a: (not re.search(r"(?i)x64|win64|x86_64", a["filename"]), a["filename"]))
        return win[0], True
    return None, None


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def download(asset, dest):
    want = (asset.get("checksum") or "").removeprefix("sha256:")
    if dest.exists() and want and sha256(dest) == want:
        return want
    tmp = dest.with_suffix(dest.suffix + ".part")
    subprocess.run(["curl", "-fL", "--retry", "3", "-s", "-S", "-A", UA["User-Agent"], "-o", str(tmp), asset["url"]], check=True)
    got = sha256(tmp)
    if want and got != want:
        tmp.unlink()
        raise RuntimeError(f"sha256 mismatch for {asset['filename']}: got {got}, Quiver pinned {want}")
    tmp.rename(dest)
    return got


def unpack(archive, dest):
    name = archive.name.lower()
    t = Path(tempfile.mkdtemp(dir=STAGE))
    try:
        if name.endswith(".zip"):
            with zipfile.ZipFile(archive) as z:
                z.extractall(t)
                for info in z.infolist():  # zipfile drops the exec bit
                    mode = info.external_attr >> 16
                    if mode & 0o111:
                        p = t / info.filename
                        if p.is_file():
                            p.chmod(p.stat().st_mode | 0o111)
        elif name.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar.bz2", ".tar")):
            with tarfile.open(archive) as tf:
                tf.extractall(t, filter="tar")
        elif name.endswith((".7z", ".rar")):
            subprocess.run(["7z", "x", "-y", f"-o{t}", str(archive)], check=True, stdout=subprocess.DEVNULL)
        else:  # a single program file: AppImage, ELF, setup or game exe
            dest.mkdir(parents=True, exist_ok=True)
            out = dest / archive.name
            shutil.copy2(archive, out)
            out.chmod(0o755)
            return
        src = t
        while True:
            kids = list(src.iterdir())
            if len(kids) == 1 and kids[0].is_dir():
                src = kids[0]
            else:
                break
        dest.mkdir(parents=True, exist_ok=True)
        for k in src.iterdir():
            target = dest / k.name
            if target.exists():
                if target.is_dir() and not target.is_symlink():
                    shutil.copytree(k, target, dirs_exist_ok=True, symlinks=True)
                    continue
                target.unlink()
            shutil.move(str(k), str(target))
    finally:
        shutil.rmtree(t, ignore_errors=True)


def entry_for(app, project, windows):
    folder = (app.get("launcher") or {}).get("folderName") or app["slug"]
    icon = None if app.get("artworkFromGame") else app.get("artwork")
    e = {
        "name": app["name"], "folderName": folder, "installPath": None, "appIconUrl": icon,
        "preferredVersion": None, "skippedUpdateVersion": None, "project": app.get("projectName"),
        "autoUpdate": True, "tags": app.get("tags", []), "catalogEntryId": app.get("id"),
        "filesToAdd": (app.get("launcher") or {}).get("filesToAdd", []),
    }
    if project.get("provider") in ("github", "gitlab") and project.get("repository"):
        e["repository"] = project["repository"].strip()
        if project["provider"] == "gitlab":
            e["repositorySource"] = "gitlab"
        f = (app.get("launcher") or {}).get("releaseAssetFilter")
        if f:
            e["releaseAssetFilter"] = f
    mods = (app.get("launcher") or {}).get("mods")
    if mods and mods.get("path"):
        e["mods"] = {"path": mods["path"], "layout": mods.get("layout"),
                     "sources": [{"provider": s.get("provider"), "sourceUrl": s.get("sourceUrl")} for s in mods.get("sources", [])]}
    if windows:
        e["linuxRunner"] = "proton"
        e["linuxPrefixPath"] = str(APPS / folder / ".steam-compat-data")
        e["linuxProtonPath"] = str(PROTON)
    e["catalog"] = {"name": e["name"], "project": e["project"], "appIconUrl": icon, "tags": e["tags"]}
    return e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--asset", action="append", default=[], help="SLUG=FILENAME to force an asset")
    ap.add_argument("--keep-download", action="store_true")
    ap.add_argument("slugs", nargs="+")
    a = ap.parse_args()
    overrides = dict(x.split("=", 1) for x in a.asset)
    STAGE.mkdir(parents=True, exist_ok=True)
    (STAGE / "dl").mkdir(exist_ok=True)
    pending = json.loads(PENDING.read_text()) if PENDING.exists() else []
    library = json.loads((LIB / "apps.json").read_text(encoding="utf-8-sig"))["apps"]
    in_library = {x["folderName"] for x in library}
    failed = []
    for slug in a.slugs:
        try:
            detail = get(f"/apps/{slug}")
            app, project = detail["entry"], detail["project"]
            rel = pick_release(app, get(f"/apps/{slug}/release-history?limit=20"))
            if not rel:
                raise RuntimeError("no verified release")
            asset, windows = pick_asset(app, rel, overrides.get(slug))
            if not asset:
                raise RuntimeError("no Linux or Windows asset in " + ", ".join(x["filename"] for x in rel.get("assets", [])))
            folder = (app.get("launcher") or {}).get("folderName") or slug
            dest = APPS / folder
            print(f"{slug}: {rel['version']} {asset['filename']} ({'windows/proton' if windows else 'linux'}) -> {folder}"
                  f"{' [already in library]' if folder in in_library else ''}", flush=True)
            if a.dry_run:
                continue
            if (dest / "version.txt").exists():
                print(f"  {folder} already installed ({(dest / 'version.txt').read_text().strip()}): skipped")
                continue
            arc = STAGE / "dl" / asset["filename"]
            digest = download(asset, arc)
            unpack(arc, dest)
            (dest / "version.txt").write_text(rel["version"])
            (dest / "installed-build.txt").write_text(f"{asset['filename']}\n{digest}\n")
            for f in (app.get("launcher") or {}).get("filesToAdd", []):
                (dest / f).touch()
            if not a.keep_download:
                arc.unlink()
            e = entry_for(app, project, windows)
            pending = [p for p in pending if p["folderName"] != e["folderName"]] + [e]
            PENDING.write_text(json.dumps(pending, indent=2, ensure_ascii=False))
            print(f"  installed; entry queued ({len(pending)} pending)", flush=True)
        except Exception as ex:  # keep going: one bad release should not stop the batch
            failed.append(slug)
            print(f"  FAILED {slug}: {ex}", flush=True)
    if failed:
        print("failed:", " ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
