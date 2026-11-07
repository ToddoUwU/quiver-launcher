#!/usr/bin/env python3
"""Reads or changes Severed Chains' binary settings file (config.dcnf). Close the game first.
  lod-config.py FILE                   list every setting
  lod-config.py FILE key=value ...     set enum/text or true/false settings, keeping a .bak of the file
"""
import shutil, struct, sys


def load(path):
    b = open(path, "rb").read()
    count = struct.unpack_from("<I", b)[0]
    i, rows = 4, []
    for _ in range(count):
        n = int.from_bytes(b[i:i + 3], "little")
        i += 3
        key = b[i:i + n].decode()
        i += n
        size = struct.unpack_from("<I", b, i)[0]
        i += 4
        rows.append([key, b[i:i + size]])
        i += size
    if i != len(b):
        raise SystemExit(f"{path}: expected {len(b)} bytes, read {i}: unknown format, nothing changed")
    return rows


def dump(rows):
    out = struct.pack("<I", len(rows))
    for key, value in rows:
        k = key.encode()
        out += len(k).to_bytes(3, "little") + k + struct.pack("<I", len(value)) + value
    return out


def show(v):
    if len(v) == 1:
        return str(bool(v[0])).lower()
    if v and v[0] == len(v) - 1:
        return v[1:].decode(errors="replace")
    return v.hex()


def main():
    path = sys.argv[1]
    rows = load(path)
    if len(sys.argv) == 2:
        for key, value in rows:
            print(key, "=", show(value))
        return
    table = {key: row for row in rows for key in [row[0]]}
    for arg in sys.argv[2:]:
        key, _, value = arg.partition("=")
        key = key if ":" in key else "lod_core:" + key
        if key not in table:
            raise SystemExit(f"no setting called {key}")
        old = table[key][1]
        if value in ("true", "false"):
            table[key][1] = bytes([value == "true"])
        elif old and old[0] == len(old) - 1:
            table[key][1] = bytes([len(value)]) + value.encode()
        else:
            raise SystemExit(f"{key} isn't a text or true/false setting")
    shutil.copy2(path, path + ".bak")
    open(path, "wb").write(dump(rows))


if __name__ == "__main__":
    main()
