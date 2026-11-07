#!/usr/bin/env python3
"""Run a game out of sight and report whether it works.

The game runs inside `gamescope --backend headless`, so no real monitor is ever touched and nothing changes a display
mode. A virtual Xbox pad presses the buttons in --keys, the game's audio goes to a private silent sink so it can be
measured, and screenshots are taken from gamescope's own X server.

  smoke.py --cwd DIR --out OUT -- ./Game --no-launcher
    --seconds N           how long to run (default 60)
    --keys "20:a,25:start,40-200/4:a,50:up~2.5"
                          t:button presses, from-to/every:button to repeat, button~seconds to hold
    --shots-every N       screenshot every N seconds (default 15)
    --env K=V             extra environment (repeatable)
    --size WxH            virtual screen (default 2560x1440)

Writes OUT/report.json: exit state, audio RMS/peak per 10 s, frame change between screenshots, peak GPU memory.
Exit code 0 when the game stayed alive, drew changing pictures, and (with --expect-audio) made sound.
"""
import argparse, json, os, re, shutil, signal, subprocess, sys, tempfile, threading, time


def run(*cmd, **kw):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, **kw).stdout


BUTTONS = {}


def make_pad(product=0x028e):
    """A virtual Xbox 360 pad. Every other pad is hidden from the game with SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT."""
    from evdev import AbsInfo, UInput, ecodes as e
    global BUTTONS
    BUTTONS = {
        "a": e.BTN_SOUTH, "b": e.BTN_EAST, "x": e.BTN_NORTH, "y": e.BTN_WEST,
        "lb": e.BTN_TL, "rb": e.BTN_TR, "back": e.BTN_SELECT, "start": e.BTN_START, "guide": e.BTN_MODE,
    }
    axis = AbsInfo(0, -32768, 32767, 16, 128, 0)
    trigger = AbsInfo(0, 0, 255, 0, 0, 0)
    hat = AbsInfo(0, -1, 1, 0, 0, 0)
    cap = {
        e.EV_KEY: list(BUTTONS.values()) + [e.BTN_THUMBL, e.BTN_THUMBR],
        e.EV_ABS: [(e.ABS_X, axis), (e.ABS_Y, axis), (e.ABS_RX, axis), (e.ABS_RY, axis), (e.ABS_Z, trigger),
                   (e.ABS_RZ, trigger), (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat)],
    }
    return UInput(cap, name="Microsoft X-Box 360 pad", vendor=0x045e, product=product, version=0x114, bustype=e.BUS_USB)


def press(pad, name, hold=0.12):
    from evdev import ecodes as e
    hats = {"up": (e.ABS_HAT0Y, -1), "down": (e.ABS_HAT0Y, 1), "left": (e.ABS_HAT0X, -1), "right": (e.ABS_HAT0X, 1)}
    if name in hats:
        code, value = hats[name]
        pad.write(e.EV_ABS, code, value); pad.syn(); time.sleep(hold)
        pad.write(e.EV_ABS, code, 0); pad.syn()
    elif name in BUTTONS:
        pad.write(e.EV_KEY, BUTTONS[name], 1); pad.syn(); time.sleep(hold)
        pad.write(e.EV_KEY, BUTTONS[name], 0); pad.syn()


def parse_keys(text):
    events = []
    for part in filter(None, (text or "").split(",")):
        when, button = part.split(":")
        m = re.fullmatch(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)", when)
        if m:
            t, end, every = map(float, m.groups())
            while t <= end:
                events.append((t, button)); t += every
        else:
            events.append((float(when), button))
    return sorted(events)


def child_pids(root):
    seen, todo = set(), [root]
    while todo:
        pid = todo.pop()
        if pid in seen:
            continue
        seen.add(pid)
        todo += [int(x) for x in run("pgrep", "-P", str(pid)).split()]
    return seen


def frame_signature(path):
    """A small grey thumbnail, to tell whether two screenshots differ. No third-party imaging needed."""
    raw = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", path, "-vf", "scale=64:36,format=gray",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL).stdout
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=60)
    ap.add_argument("--keys", default="")
    ap.add_argument("--shots-every", type=float, default=15)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--size", default="2560x1440")
    ap.add_argument("--expect-audio", action="store_true")
    ap.add_argument("--no-pad", action="store_true")
    ap.add_argument("--pad-product", default="028e", help="USB product id in hex, so runs side by side each see only their own pad")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd
    os.makedirs(a.out, exist_ok=True)
    w, h = a.size.split("x")

    sink = "gamesmoke" + str(os.getpid())
    module = run("pactl", "load-module", "module-null-sink", f"sink_name={sink}",
                 f"sink_properties=device.description={sink}").strip()
    pad = None if a.no_pad else make_pad(int(a.pad_product, 16))
    time.sleep(0.5)

    display_file = tempfile.NamedTemporaryFile(prefix="smoke-display-", delete=False).name
    inner = 'echo "$DISPLAY" > "$SMOKE_DISPLAY_FILE"; exec "$@"'
    env = dict(os.environ, SMOKE_DISPLAY_FILE=display_file, SDL_VIDEODRIVER="x11", SDL_VIDEO_DRIVER="x11",
               SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT="0x045e/0x" + a.pad_product, PULSE_SINK=sink,
               SDL_AUDIO_DEVICE_NAME=sink)
    env.pop("WAYLAND_DISPLAY", None)
    for kv in a.env:
        k, _, v = kv.partition("=")
        env[k] = v
    log = open(os.path.join(a.out, "game.log"), "w")
    # The headless backend never opens a DRM device, so real monitors can't be affected.
    proc = subprocess.Popen(["gamescope", "--backend", "headless", "-W", w, "-H", h, "-w", w, "-h", h, "-r", "60", "--",
                             "bash", "-c", inner, "smoke"] + cmd,
                            cwd=a.cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    display = None
    for _ in range(100):
        time.sleep(0.2)
        try:
            display = open(display_file).read().strip()
        except OSError:
            pass
        if display:
            break

    # Audio: move this game's streams to the silent sink, then record the sink.
    parec = subprocess.Popen(["parec", "-d", sink + ".monitor", "--format=s16le", "--rate=44100", "--channels=2",
                              "--latency-msec=100"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    pcm = bytearray()
    threading.Thread(target=lambda: [pcm.extend(c) for c in iter(lambda: parec.stdout.read(65536), b"")], daemon=True).start()
    stop = threading.Event()

    def move_audio():
        while not stop.is_set():
            pids = child_pids(proc.pid)
            data = run("pactl", "--format=json", "list", "sink-inputs")
            try:
                for si in json.loads(data or "[]"):
                    props = si.get("properties", {})
                    if int(props.get("application.process.id", "0") or 0) in pids:
                        run("pactl", "move-sink-input", str(si["index"]), sink)
            except ValueError:
                pass
            stop.wait(1.0)
    threading.Thread(target=move_audio, daemon=True).start()

    events = parse_keys(a.keys)

    def keys():
        start = time.time()
        for t, b in events:
            if stop.wait(max(0, start + t - time.time())):
                return
            if pad:
                name, _, hold = b.partition("~")
                press(pad, name, float(hold) if hold else 0.12)
    threading.Thread(target=keys, daemon=True).start()

    shots, sigs, peak_vram, busy = [], [], 0, []
    start = time.time()
    next_shot = a.shots_every
    vram_paths = [p for p in ("/sys/class/drm/card1/device/mem_info_vram_used", "/sys/class/drm/card0/device/mem_info_vram_used") if os.path.exists(p)]
    busy_paths = [p for p in ("/sys/class/drm/card1/device/gpu_busy_percent",) if os.path.exists(p)]
    while time.time() - start < a.seconds and proc.poll() is None:
        time.sleep(0.5)
        for p in vram_paths[:1]:
            peak_vram = max(peak_vram, int(open(p).read()))
        for p in busy_paths:
            busy.append(int(open(p).read()))
        if time.time() - start >= next_shot and display:
            name = os.path.join(a.out, f"t{int(next_shot):04d}.jpg")
            # The root window of gamescope's X server is always black: grab the game's own window.
            tree = run("xwininfo", "-display", display, "-root", "-tree")
            found = re.findall(r"^\s+(0x[0-9a-f]+) \"(?!steamcompmgr)[^\"]+\":", tree, re.M)
            if found:
                try:
                    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "x11grab", "-window_id", found[0],
                                    "-i", display, "-frames:v", "1", "-q:v", "2", name], env=env, timeout=30,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except subprocess.TimeoutExpired:
                    pass
            if os.path.exists(name):
                shots.append(name)
                sigs.append(frame_signature(name))
            next_shot += a.shots_every

    alive = proc.poll() is None
    exit_code = proc.poll()
    stop.set()
    # Close the game first so it saves and restores what it should, then gamescope.
    pids = child_pids(proc.pid) - {proc.pid}
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for _ in range(25):
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        time.sleep(1)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    parec.terminate()
    time.sleep(0.3)
    run("pactl", "unload-module", module)
    if pad:
        pad.close()
    os.unlink(display_file)

    report = {"alive_at_end": alive, "exit_code": exit_code, "seconds": round(time.time() - start, 1), "shots": len(shots),
              "peak_vram_mb": peak_vram // (1024 * 1024), "gpu_busy_avg": round(sum(busy) / len(busy), 1) if busy else None}
    changes = []
    for prev, cur in zip(sigs, sigs[1:]):
        n = min(len(prev), len(cur))
        changes.append(round(sum(abs(prev[i] - cur[i]) for i in range(n)) / max(n, 1), 2))
    report["picture_change"] = changes
    report["brightness"] = [round(sum(s) / max(len(s), 1), 1) for s in sigs]
    audio = []
    try:
        import numpy as np
        samples = np.frombuffer(bytes(pcm[: len(pcm) // 4 * 4]), dtype=np.int16).astype(np.float64) / 32768
        step = 44100 * 2 * 10
        for i in range(0, len(samples), step):
            chunk = samples[i:i + step]
            if len(chunk):
                audio.append({"rms": round(float(np.sqrt((chunk ** 2).mean())), 4), "peak": round(float(np.abs(chunk).max()), 3)})
    except ImportError:
        pass
    report["audio"] = audio
    drew = any(c > 0.5 for c in changes) or any(b > 3 for b in report["brightness"])
    made_sound = any(x["rms"] > 0.002 for x in audio)
    report["drew"], report["made_sound"] = drew, made_sound
    report["ok"] = bool(alive and drew and (made_sound or not a.expect_audio))
    json.dump(report, open(os.path.join(a.out, "report.json"), "w"), indent=1)
    print(json.dumps(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
