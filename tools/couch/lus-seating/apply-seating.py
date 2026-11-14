#!/usr/bin/env python3
"""Patch a libultraship checkout so each gamepad gets its own N64 port (couch seating).

Stock libultraship ignores every gamepad on ports 2-4 at each device refresh, so all pads drive player 1 until someone
reassigns them in the controller window, every session. This makes RefreshConnectedSDLGamepads seat each NEWLY
connected pad, in plug order (SDL instance id), on the lowest port that has no pad: pad 1 -> port 1, pad 2 -> port 2,
up to 4. Pads already seated keep their port when others connect or disconnect; a 5th pad is left unseated.
Single-player games only read port 1, so extra pads are harmless. LUS_AUTO_SEAT=0 in the environment restores the stock
behaviour. The logic is BattleShip's (JRickey/libultraship, ssb64 branch, commit cdb279c5), plus the sort and the switch.

  apply-seating.py <libultraship checkout>     (idempotent; exits 1 if the file no longer looks as expected)
"""
import re, sys, pathlib

root = pathlib.Path(sys.argv[1])
hits = list(root.glob("src/**/ConnectedPhysicalDeviceManager.cpp"))
if len(hits) != 1:
    sys.exit(f"expected one ConnectedPhysicalDeviceManager.cpp under {root}/src, found {len(hits)}")
path = hits[0]
src = path.read_text()
MARK = "Couch seating (PersonalUpdates)"
if MARK in src:
    print(f"already patched: {path}")
    sys.exit(0)

head = "void ConnectedPhysicalDeviceManager::RefreshConnectedSDLGamepads() {\n    mConnectedSDLGamepads.clear();\n"
if src.count(head) != 1:
    sys.exit("RefreshConnectedSDLGamepads() does not start as expected")
src = src.replace(head,
    "void ConnectedPhysicalDeviceManager::RefreshConnectedSDLGamepads() {\n"
    f"    // {MARK}: remember the pads that were already connected, so the ports they were\n"
    "    // given survive the refresh that every controller add/remove event triggers.\n"
    "    auto previouslyConnected = std::move(mConnectedSDLGamepads);\n"
    "    std::vector<int32_t> newInstanceIds;\n"
    "    mConnectedSDLGamepads.clear();\n")

stock = re.compile(r"\n        for \(uint8_t port = 1; port < 4; port\+\+\) \{\n"
                   r"            mIgnoredInstanceIds\[port\]\.insert\(instanceId\);\n"
                   r"        \}\n    \}\n\}\n")
if len(stock.findall(src)) != 1:
    sys.exit("the stock 'ignore on ports 2-4' loop was not found exactly once")
src = stock.sub(lambda _: r'''
        if (!previouslyConnected.contains(instanceId)) {
            newInstanceIds.push_back(instanceId);
        }
    }

    const char* autoSeat = std::getenv("LUS_AUTO_SEAT");
    if (autoSeat != nullptr && std::string(autoSeat) == "0") {
        // Stock behaviour: every pad drives port 1 only.
        for (const auto& [instanceId, gamepad] : mConnectedSDLGamepads) {
            for (uint8_t port = 1; port < 4; port++) {
                mIgnoredInstanceIds[port].insert(instanceId);
            }
        }
        return;
    }

    // Seat new pads in plug order (SDL instance ids grow as devices are opened), each on the
    // lowest port that has no connected pad yet. Hide each new pad from every port first, so
    // the occupancy scan does not count the pad being placed.
    std::sort(newInstanceIds.begin(), newInstanceIds.end());
    for (int32_t newId : newInstanceIds) {
        for (uint8_t port = 0; port < 4; port++) {
            mIgnoredInstanceIds[port].insert(newId);
        }
    }
    for (int32_t newId : newInstanceIds) {
        uint8_t freePort = UINT8_MAX;
        for (uint8_t port = 0; port < 4 && freePort == UINT8_MAX; port++) {
            bool occupied = false;
            for (const auto& [instanceId, gamepad] : mConnectedSDLGamepads) {
                if (!mIgnoredInstanceIds[port].contains(instanceId)) {
                    occupied = true;
                    break;
                }
            }
            if (!occupied) {
                freePort = port;
            }
        }
        if (freePort == UINT8_MAX) {
            SPDLOG_INFO("Couch seating: all 4 ports have a gamepad; '{}' (instance {}) is not seated",
                        mConnectedSDLGamepadNames[newId], newId);
            continue;
        }
        mIgnoredInstanceIds[freePort].erase(newId);
        SPDLOG_INFO("Couch seating: gamepad '{}' (instance {}) -> port {}", mConnectedSDLGamepadNames[newId], newId,
                    freePort + 1);
    }
}
''', src)

inc = "".join(f"#include <{h}>\n" for h in ("spdlog/spdlog.h", "algorithm", "cstdint", "cstdlib", "string", "vector")
              if f"#include <{h}>" not in src)
first_include_end = src.index("\n", src.index("#include")) + 1
src = src[:first_include_end] + inc + src[first_include_end:]
path.write_text(src)
print(f"patched: {path}")
