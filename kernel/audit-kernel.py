#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Validate built kernel, DTB, configuration and staged modules without devices."""
from pathlib import Path
import hashlib
import json
import re
import struct

p = Path(__file__).resolve().parent
build = p / "build"
staging = p / "staging/lib/modules/6.6.161-firefly"

def config(path):
    data = {}
    for line in path.read_text().splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            k, v = line.split("=", 1)
            data[k] = v
        elif line.startswith("# CONFIG_") and line.endswith(" is not set"):
            data[line[2:-11]] = "n"
    return data

requested = config(p / "firefly-ubuntu22.config")
resolved = config(build / ".config")
mismatches = {k: {"requested": v, "resolved": resolved.get(k)} for k, v in requested.items() if resolved.get(k) != v}
assert not mismatches, mismatches
release = (build / "include/config/kernel.release").read_text().strip()
assert release == "6.6.161-firefly", release
zimage = build / "arch/arm/boot/zImage"
dtb = build / "arch/arm/boot/dts/rockchip/rk3288-firefly-ubuntu22.dtb"
z = zimage.read_bytes()
d = dtb.read_bytes()
assert struct.unpack_from("<I", z, 0x24)[0] == 0x016f2818, "ARM zImage magic"
assert struct.unpack_from(">I", d, 0)[0] == 0xd00dfeed, "FDT magic"
assert struct.unpack_from(">I", d, 4)[0] == len(d), "FDT totalsize"
modules = list(staging.rglob("*.ko"))
assert modules, "no kernel modules"
expected_modules = ["panfrost.ko", "zram.ko", "brcmfmac.ko", "xpad.ko"]
for name in expected_modules:
    matches = [m for m in modules if m.name == name]
    assert len(matches) == 1, (name, matches)
    assert b"vermagic=6.6.161-firefly " in matches[0].read_bytes(), name
artifacts = {}
for name, path in {"zImage": zimage, "rk3288-firefly-ubuntu22.dtb": dtb, "config-6.6.161-firefly": build/".config", "System.map-6.6.161-firefly": build/"System.map"}.items():
    b = path.read_bytes()
    artifacts[name] = {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
report = {"kernel_release": release, "source_url": "https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.6.161.tar.xz", "source_sha256": "7d34405be5cd4989b2a5e9cbefa798e3a175218901271e034af3fe4e840b71c6", "requested_config_entries": len(requested), "config_mismatches": mismatches, "module_count": len(modules), "expected_modules_found": expected_modules, "artifacts": artifacts}
(p / "kernel-audit.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report, indent=2))
