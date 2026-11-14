#!/usr/bin/env python3
"""Drive a game inside headless gamescope only: start | shot OUT.jpg | click X Y | key NAME | stop.

Coordinates for click are relative to the game's window. The real desktop displays (:0, :1) are refused.
State: $HL_STATE (default /tmp/headless-drive.state), game log: $HL_LOG. Used 2026-11-14 to click G-Diffuser's
first-time setup button: start in the background, shot, click, stop. Screenshots are saved at half size, so
double a point read off a screenshot before passing it to click.
"""
import ctypes, os, re, signal, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.environ.get("HL_STATE", "/tmp/headless-drive.state")
LOG = os.environ.get("HL_LOG", "/tmp/headless-drive-game.log")


def state():
    pid, disp = open(STATE).read().split()
    if disp in (":0", ":1"):
        raise SystemExit("refusing real desktop display " + disp)
    return int(pid), disp


def game_window(disp):
    tree = subprocess.run(["xwininfo", "-display", disp, "-root", "-tree"], capture_output=True, text=True).stdout
    found = re.findall(r"^\s+(0x[0-9a-f]+) \"(?!steamcompmgr)[^\"]+\":.*?(\d+)x(\d+)\+-?\d+\+-?\d+\s+\+(-?\d+)\+(-?\d+)", tree, re.M)
    found = [f for f in found if int(f[1]) > 200]
    if not found:
        raise SystemExit("no game window yet")
    wid, w, h, x, y = found[0]
    return wid, int(w), int(h), int(x), int(y)


def start(cwd, cmd):
    env = dict(os.environ, SDL_VIDEODRIVER="x11", SDL_VIDEO_DRIVER="x11", SDL_AUDIODRIVER="dummy",
               SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT="0x0000/0x0000", SDL_JOYSTICK_HIDAPI="0",
               HL_DISPLAY_FILE=STATE + ".display")
    env.pop("WAYLAND_DISPLAY", None)
    inner = 'echo "$DISPLAY" > "$HL_DISPLAY_FILE"; exec "$@"'
    log = open(LOG, "w")
    proc = subprocess.Popen(["gamescope", "--backend", "headless", "-W", "2560", "-H", "1440", "-w", "2560", "-h", "1440",
                             "-r", "60", "--", "bash", "-c", inner, "hl"] + cmd,
                            cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(100):
        time.sleep(0.2)
        try:
            disp = open(env["HL_DISPLAY_FILE"]).read().strip()
        except OSError:
            disp = ""
        if disp:
            break
    if disp in ("", ":0", ":1"):
        os.killpg(proc.pid, signal.SIGTERM)
        raise SystemExit("bad display " + repr(disp))
    open(STATE, "w").write(f"{proc.pid} {disp}")
    print("started", proc.pid, disp)
    proc.wait()
    print("gamescope exited", proc.returncode)


def shot(out):
    _, disp = state()
    wid, w, h, x, y = game_window(disp)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "x11grab", "-window_id", wid, "-i", disp,
                    "-frames:v", "1", "-q:v", "2", "-vf", "scale=iw/2:ih/2", out], timeout=30, check=True)
    print(f"window {wid} {w}x{h}+{x}+{y}; saved {out} at half size")


def xopen(disp):
    X = ctypes.cdll.LoadLibrary("libX11.so.6")
    XT = ctypes.cdll.LoadLibrary("libXtst.so.6")
    X.XOpenDisplay.restype = ctypes.c_void_p
    X.XOpenDisplay.argtypes = [ctypes.c_char_p]
    X.XFlush.argtypes = [ctypes.c_void_p]
    X.XCloseDisplay.argtypes = [ctypes.c_void_p]
    X.XStringToKeysym.restype = ctypes.c_ulong
    X.XStringToKeysym.argtypes = [ctypes.c_char_p]
    X.XKeysymToKeycode.restype = ctypes.c_ubyte
    X.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    XT.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
    XT.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    XT.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
    d = X.XOpenDisplay(disp.encode())
    if not d:
        raise SystemExit("cannot open " + disp)
    return X, XT, d


def click(cx, cy):
    _, disp = state()
    _, w, h, x, y = game_window(disp)
    X, XT, d = xopen(disp)
    XT.XTestFakeMotionEvent(d, -1, x + cx, y + cy, 0); X.XFlush(d); time.sleep(0.3)
    XT.XTestFakeMotionEvent(d, -1, x + cx + 1, y + cy, 0); X.XFlush(d); time.sleep(0.3)
    XT.XTestFakeButtonEvent(d, 1, 1, 0); X.XFlush(d); time.sleep(0.12)
    XT.XTestFakeButtonEvent(d, 1, 0, 0); X.XFlush(d)
    X.XCloseDisplay(d)
    print("clicked", cx, cy, "in window at", x, y)


def key(name):
    _, disp = state()
    X, XT, d = xopen(disp)
    code = X.XKeysymToKeycode(d, X.XStringToKeysym(name.encode()))
    XT.XTestFakeKeyEvent(d, code, 1, 0); X.XFlush(d); time.sleep(0.1)
    XT.XTestFakeKeyEvent(d, code, 0, 0); X.XFlush(d)
    X.XCloseDisplay(d)
    print("key", name)


def stop():
    pid, _ = state()
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    print("stopped", pid)


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "start":
        start(sys.argv[2], sys.argv[3:])
    elif c == "shot":
        shot(sys.argv[2])
    elif c == "click":
        click(int(sys.argv[2]), int(sys.argv[3]))
    elif c == "key":
        key(sys.argv[2])
    elif c == "stop":
        stop()
