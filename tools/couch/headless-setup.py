#!/usr/bin/env python3
"""Run a game's first-time setup out of sight, in a headless gamescope, and stop when it is done.

Some ports ask yes/no or OK in a native message box before they extract their assets. This presses Return (or other
keys) inside gamescope's own nested X server only: its display number is read from gamescope's log, and the real
desktop displays (:0, :1) are refused. Every gamepad is hidden from the game, so the player's pads are never touched.

  headless-setup.py --cwd DIR --until FILE [--seconds 300] [--keys Return] [--every 3] [--env K=V] -- CMD...

Exit 0 once FILE exists (the game is then closed), 1 on timeout.
"""
import argparse, ctypes, os, re, signal, subprocess, sys, time

X = ctypes.cdll.LoadLibrary("libX11.so.6")
XT = ctypes.cdll.LoadLibrary("libXtst.so.6")
X.XOpenDisplay.restype = ctypes.c_void_p
X.XOpenDisplay.argtypes = [ctypes.c_char_p]
X.XStringToKeysym.restype = ctypes.c_ulong
X.XStringToKeysym.argtypes = [ctypes.c_char_p]
X.XKeysymToKeycode.restype = ctypes.c_ubyte
X.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
X.XFlush.argtypes = [ctypes.c_void_p]
X.XCloseDisplay.argtypes = [ctypes.c_void_p]
XT.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]


def tap(display, keys):
    if display in (":0", ":1"):
        raise SystemExit(f"refusing to send keys to the real desktop display {display}")
    d = X.XOpenDisplay(display.encode())
    if not d:
        return False
    for k in keys:
        code = X.XKeysymToKeycode(d, X.XStringToKeysym(k.encode()))
        XT.XTestFakeKeyEvent(d, code, 1, 0)
        X.XFlush(d)
        time.sleep(0.08)
        XT.XTestFakeKeyEvent(d, code, 0, 0)
        X.XFlush(d)
    X.XCloseDisplay(d)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--until", required=True, help="file whose appearance means setup is done")
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--keys", default="Return", help="comma-separated X keysyms pressed every --every seconds")
    ap.add_argument("--every", type=float, default=3)
    ap.add_argument("--first", type=float, default=8, help="seconds before the first key press")
    ap.add_argument("--settle", type=float, default=5, help="seconds to wait after FILE appears")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--log", default="/dev/null")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    env = dict(os.environ)
    env["SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT"] = "0x0000/0x0000"  # no pads for the game at all
    env["SDL_JOYSTICK_HIDAPI"] = "0"
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    log = open(a.log, "w")
    proc = subprocess.Popen(["gamescope", "--backend", "headless", "-W", "2560", "-H", "1440", "-w", "2560", "-h", "1440",
                             "-r", "60", "--"] + cmd, cwd=a.cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    start, display, next_tap, done_at = time.time(), None, time.time() + a.first, None
    keys = [k for k in a.keys.split(",") if k]
    try:
        while time.time() - start < a.seconds and proc.poll() is None:
            if display is None and a.log != "/dev/null":
                m = re.search(r"Starting Xwayland on (:\d+)", open(a.log, errors="ignore").read())
                display = m.group(1) if m else None
            if os.path.exists(a.until):
                done_at = done_at or time.time()
                if time.time() - done_at >= a.settle:
                    print("done:", a.until)
                    return 0
            elif display and keys and time.time() >= next_tap:
                tap(display, keys)
                next_tap = time.time() + a.every
            time.sleep(0.5)
        print("timed out" if proc.poll() is None else f"exited {proc.returncode}", "without", a.until)
        return 1
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)


if __name__ == "__main__":
    sys.exit(main())
