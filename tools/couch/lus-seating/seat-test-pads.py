#!/usr/bin/env python3
"""Seating test pads: Xbox 360-style uinput pads (045e:028e), plugged and unplugged on a timeline.

  seat-test-pads.py DONEFILE

t=0  pads A and B plugged (before the game starts; the caller waits for READY on stdout)
t=20 pads C and D plugged             -> expect ports 3 and 4
t=30 pad B unplugged
t=35 pad E plugged                    -> expect port 2 (B's free seat)
t=45 everything unplugged, DONEFILE written
"""
import sys, time
from evdev import UInput, ecodes as e, AbsInfo

CAPS = {
    e.EV_KEY: [e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START,
               e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR],
    e.EV_ABS: [(e.ABS_X, AbsInfo(0, -32768, 32767, 16, 128, 0)), (e.ABS_Y, AbsInfo(0, -32768, 32767, 16, 128, 0)),
               (e.ABS_RX, AbsInfo(0, -32768, 32767, 16, 128, 0)), (e.ABS_RY, AbsInfo(0, -32768, 32767, 16, 128, 0)),
               (e.ABS_Z, AbsInfo(0, 0, 255, 0, 0, 0)), (e.ABS_RZ, AbsInfo(0, 0, 255, 0, 0, 0)),
               (e.ABS_HAT0X, AbsInfo(0, -1, 1, 0, 0, 0)), (e.ABS_HAT0Y, AbsInfo(0, -1, 1, 0, 0, 0))],
}


def pad(tag):
    return UInput(CAPS, name=f"Seat test pad {tag}", vendor=0x045e, product=0x028e, version=0x0114, bustype=e.BUS_USB)


def log(msg):
    print(f"{time.strftime('%T')} {msg}", flush=True)


pads = {}
try:
    for t in "AB":
        pads[t] = pad(t)
        time.sleep(0.5)
    log("plugged A, B")
    print("READY", flush=True)
    time.sleep(20)
    for t in "CD":
        pads[t] = pad(t)
        time.sleep(1)
    log("plugged C, D")
    time.sleep(10)
    pads.pop("B").close()
    log("unplugged B")
    time.sleep(5)
    pads["E"] = pad("E")
    log("plugged E")
    time.sleep(10)
finally:
    for p in pads.values():
        p.close()
    log("unplugged all")
    open(sys.argv[1], "w").close()
