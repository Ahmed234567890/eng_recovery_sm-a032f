#!/usr/bin/env python3
"""Stage a recovery ramdisk and build the 64 MiB Phase 1 recovery image.

Inputs:
  --root          known-good ramdisk root (extracted from the rollback image)
  --kernel        kernel image from the same boot image
  --dtb           DTB from the same boot image
  --recovery-dtbo recovery DTBO from the same boot image
  --vbmeta        original 2112-byte AVB vbmeta blob
  --recovery      patched recovery binary (default ../binaries/recovery_patched)
  --libui         patched librecovery_ui.so (default ../binaries/librecovery_ui_patched.so)
  --tools         directory containing recovery-tools, bash, busybox, lpmap
                  (default ../tools)

Output:
  --out           64 MiB flashable image (default ../images/recovery_phase1_fixed.img)

The ramdisk is repacked as newc cpio with root:root ownership and gzip -9 -n.
The boot image is built with the original v2 header parameters and wrapped
with the original signed vbmeta blob using avbtool append_vbmeta_image.
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

PAGE_SIZE = 2048
HEADER_VERSION = 2
OS_VERSION = "11.0.0"
OS_PATCH_LEVEL = "2021-10"
CMDLINE = "console=ttyS1,115200n8 buildvariant=userdebug"
KERNEL_ADDR_OFF = "0x8000"
RAMDISK_ADDR_OFF = "0x05400000"
TAGS_ADDR_OFF = "0x100"
DTB_ADDR_OFF = "0x1f00000"
PARTITION_SIZE = 64 * 1024 * 1024

TOOL_NAMES = ["recovery-tools", "bash", "busybox", "lpmap"]
BUSYBOX_LINKS = ["ash", "awk", "bb", "unzip", "vi", "wget"]


def run(cmd, **kwargs):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def stage_root(args):
    stage = args.work / "fixed-root"
    if stage.exists():
        shutil.rmtree(stage)
    shutil.copytree(args.root, stage, symlinks=True)
    os.chmod(stage / "system/bin", 0o755)
    os.chmod(stage / "system/lib", 0o755)

    shutil.copy2(args.recovery, stage / "system/bin/recovery")
    os.chmod(stage / "system/bin/recovery", 0o755)
    shutil.copy2(args.libui, stage / "system/lib/librecovery_ui.so")
    os.chmod(stage / "system/lib/librecovery_ui.so", 0o644)

    for name in TOOL_NAMES:
        src = args.tools / name
        if not src.exists():
            sys.exit(f"missing tool: {src}")
        dst = stage / "system/bin" / name
        shutil.copy2(src, dst)
        os.chmod(dst, 0o755)

    for name in BUSYBOX_LINKS:
        link = stage / "system/bin" / name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to("busybox")

    config = stage / "config"
    if config.exists():
        os.chmod(config, 0o555)
    return stage


def pack_ramdisk(stage, work):
    find = subprocess.Popen(["find", "."], cwd=stage, stdout=subprocess.PIPE,
                            env={**os.environ, "LC_ALL": "C"})
    data = subprocess.run(
        ["cpio", "-o", "-H", "newc", "--owner", "0:0", "--quiet"],
        cwd=stage, stdin=find.stdout, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={**os.environ, "LC_ALL": "C"}, check=True,
    ).stdout
    find.wait()
    cpio_path = work / "fixed-ramdisk.cpio"
    gz_path = work / "fixed-ramdisk.gz"
    cpio_path.write_bytes(data)
    with open(gz_path, "wb") as f:
        subprocess.run(["gzip", "-9", "-n", "-c"], input=data, stdout=f,
                       check=True)
    return gz_path


def build_boot(args, ramdisk_gz):
    raw = args.work / "fixed-boot.img"
    run([
        "mkbootimg",
        "--kernel", str(args.kernel),
        "--ramdisk", str(ramdisk_gz),
        "--recovery_dtbo", str(args.recovery_dtbo),
        "--dtb", str(args.dtb),
        "--cmdline", CMDLINE,
        "--base", "0x0",
        "--kernel_offset", KERNEL_ADDR_OFF,
        "--ramdisk_offset", RAMDISK_ADDR_OFF,
        "--tags_offset", TAGS_ADDR_OFF,
        "--dtb_offset", DTB_ADDR_OFF,
        "--pagesize", str(PAGE_SIZE),
        "--header_version", str(HEADER_VERSION),
        "--os_version", OS_VERSION,
        "--os_patch_level", OS_PATCH_LEVEL,
        "-o", str(raw),
    ])
    return raw


def wrap_avb(args, raw):
    args.out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(raw, args.out)
    run([
        "avbtool", "append_vbmeta_image",
        "--image", str(args.out),
        "--partition_size", str(args.partition_size),
        "--vbmeta_image", str(args.vbmeta),
    ])


def verify(args, raw, ramdisk_gz):
    print("\n=== boot header ===")
    run(["unpack_bootimg", "--boot_img", str(raw)])
    print("\n=== AVB footer ===")
    run(["avbtool", "info_image", "--image", str(args.out)])
    print("\n=== hashes ===")
    for p in (raw, ramdisk_gz, args.out):
        print(f"{sha256(p)}  {p}  ({p.stat().st_size} bytes)")


def main():
    repo = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--kernel", required=True, type=Path)
    ap.add_argument("--dtb", required=True, type=Path)
    ap.add_argument("--recovery-dtbo", required=True, type=Path)
    ap.add_argument("--vbmeta", required=True, type=Path)
    ap.add_argument("--recovery", type=Path, default=repo / "binaries/recovery_patched")
    ap.add_argument("--libui", type=Path, default=repo / "binaries/librecovery_ui_patched.so")
    ap.add_argument("--tools", type=Path, default=repo / "tools")
    ap.add_argument("--out", type=Path, default=repo / "images/recovery_phase1_fixed.img")
    ap.add_argument("--work", type=Path, default=Path.cwd() / "work")
    ap.add_argument("--partition-size", type=int, default=PARTITION_SIZE)
    args = ap.parse_args()

    for p in (args.root, args.kernel, args.dtb, args.recovery_dtbo,
              args.vbmeta, args.recovery, args.libui, args.tools):
        if not p.exists():
            sys.exit(f"missing input: {p}")
    args.work.mkdir(parents=True, exist_ok=True)

    print("== staging ==")
    stage = stage_root(args)
    print("== packing ramdisk ==")
    ramdisk_gz = pack_ramdisk(stage, args.work)
    print("== building boot image ==")
    raw = build_boot(args, ramdisk_gz)
    print("== wrapping with AVB ==")
    wrap_avb(args, raw)
    verify(args, raw, ramdisk_gz)


if __name__ == "__main__":
    main()
