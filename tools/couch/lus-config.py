#!/usr/bin/env python3
"""Max graphics + multiplayer-ready controller ports for libultraship (Harbour Masters) ports.

  lus-config.py CONFIG.cfg.json [--ports 4] [--extra CVAR=VALUE ...]

Graphics (what the user wants everywhere): fullscreen 2560x1440 on the ASUS (X 2560), 8x MSAA (the most LUS offers),
internal resolution pinned to exactly 1440 lines at 16:9, vsync, interpolation matched to the refresh rate, linear
texture filtering, SDL audio (goes to PipeWire). Both CVar spellings are written: older LUS reads gMSAAValue etc.,
newer reads gSettings.MSAAValue etc.

Controllers: LUS gives port 1 every gamepad and makes ports 2-4 ignore them all, and ports 2-4 start with no mappings.
This copies port 1's gamepad (SDL) mappings to ports 2..N, so a second player only has to pick their pad for port 2
in the game's controller window (the ignore list itself is not saved by LUS; it is rebuilt at every start).
"""
import argparse, json, shutil, time
from pathlib import Path

GRAPHICS = {
    "MSAAValue": 8, "InternalResolution": 1.0, "VsyncEnabled": 1, "MatchRefreshRate": 1, "InterpolationFPS": 240,
    "SdlWindowedFullscreen": 1, "TextureFilter": 1,
}
ADVRES = {"Enabled": 1, "VerticalPixelCount": 1440, "AspectRatioX": 16.0, "AspectRatioY": 9.0,
          "UIComboItem": {"AspectRatio": 1, "PixelCount": 0}, "VerticalResolutionToggle": 1}


def put(d, path, value):
    *head, last = path.split(".")
    for k in head:
        d = d.setdefault(k, {})
    d[last] = value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--ports", type=int, default=4)
    ap.add_argument("--extra", action="append", default=[])
    a = ap.parse_args()
    p = Path(a.config)
    d = json.loads(p.read_text())
    shutil.copy2(p, p.with_name(p.name + time.strftime(".bak-%Y-%m-%d-couch")))
    c = d.setdefault("CVars", {})
    for k, v in GRAPHICS.items():
        c["g" + k] = v
        put(c, "gSettings." + k, v)
    for base in ("gAdvancedResolution", "gSettings.AdvancedResolution"):
        for k, v in ADVRES.items():
            put(c, f"{base}.{k}", v)
    w = d.setdefault("Window", {})
    w.update({"Width": 2560, "Height": 1440, "PositionX": 2560, "PositionY": 0, "AudioBackend": "sdl"})
    w.setdefault("Fullscreen", {}).update({"Enabled": True, "Width": 2560, "Height": 1440})
    for kv in a.extra:
        k, v = kv.split("=", 1)
        put(c, k, json.loads(v))

    # Controller ports: both layouts exist (gControllers.* in older LUS, gSettings.Controllers.* in newer).
    for root_path in ("gControllers", "gSettings.Controllers"):
        node = c
        for k in root_path.split("."):
            node = node.get(k) if isinstance(node, dict) else None
        if not isinstance(node, dict) or "Port1" not in node:
            continue
        port1 = node["Port1"]
        maps = {kind: node.get(kind, {}) for kind in ("ButtonMappings", "AxisDirectionMappings", "RumbleMappings")}

        def sdl_ids(ids):
            return [i for i in ids.split(",") if i and "SDL" in i or (i and i.startswith("P0") and "-" not in i[2:])]

        for n in range(2, a.ports + 1):
            pre = f"P{n - 1}"
            port = json.loads(json.dumps(port1))

            def remap(ids, kind):
                out = []
                for i in ids.split(","):
                    if not i or "KB" in i or "Mouse" in i:
                        continue  # the keyboard stays on player 1
                    new = pre + i[2:]
                    src = maps.get(kind, {}).get(i)
                    if src is not None:
                        maps[kind][new] = src
                    out.append(new)
                return ",".join(out) + ("," if out else "")

            for group, vals in port.items():
                if isinstance(vals, dict):
                    for k, ids in vals.items():
                        if isinstance(ids, str) and k.endswith("MappingIds"):
                            kind = "ButtonMappings" if group == "Buttons" else "AxisDirectionMappings"
                            vals[k] = remap(ids, kind)
                elif group == "RumbleMappingIds" and isinstance(vals, str):
                    port[group] = remap(vals, "RumbleMappings")
            port["HasConfig"] = 1
            node[f"Port{n}"] = port
        for kind, m in maps.items():
            if m:
                node[kind] = m
    p.write_text(json.dumps(d, indent=4))
    print("updated", p)


if __name__ == "__main__":
    main()
