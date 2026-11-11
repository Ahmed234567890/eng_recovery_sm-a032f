# 01 — Device and baseline

## Device

| Property | Value |
|---|---|
| Model | Samsung Galaxy A03 Core `SM-A032F` |
| Platform | Unisoc SC9863A (`m168`), 4× Cortex-A55 + 4× Cortex-A55, 2 GB RAM |
| Display | 1600×720 |
| Bootloader | Unlocked (`androidboot.verifiedbootstate=orange`, `androidboot.flash.locked=0`) |
| Vendor OS | Android 11 (boot image `os_version 11.0.0`, patch level `2021-10`) |
| Installed system | LineageOS 21 GSI, Android 14, `21.0-20250125-UNOFFICIAL-a3core` |
| Recovery partition | `/dev/block/mmcblk0p41`, 64 MiB (`0x4000000`), raw |
| Cache partition | `/dev/block/mmcblk0p52` |

The bootloader reports a per-unit serial number; it is redacted in this
repository. ADB in recovery runs as `root` in the `su` SELinux domain, which
is what makes the live experiments below possible without a custom sepolicy.

## Partition requirements

`fastboot getvar partition-size:recovery` returns `0x4000000` (64 MiB) and
`partition-type:recovery` returns `raw`. The image built by this project is
exactly 64 MiB so it can be flashed to the raw partition without truncation.

## Original engineering recovery image

The stock image is a 64 MiB AVB-wrapped Android boot image. Its layout:

```
offset 0x00000000  Android boot image v2 (header + kernel + ramdisk +
                   recovery_dtbo + DTB), 31,823,872 bytes
offset 0x01E5A000  original vbmeta blob, 2,112 bytes
offset 0x03FFFFC0  AVB footer, 64 bytes
```

`avbtool info_image` on the original:

```
Footer version:           1.0
Image size:               67108864 bytes
Original image size:      31823872 bytes
VBMeta offset:            31825920
VBMeta size:              2112 bytes
Algorithm:                SHA256_RSA4096
Rollback Index:           0
Descriptors:
    Hash descriptor:
      Image Size:            31823872 bytes
      Hash Algorithm:        sha256
      Partition Name:        recovery
      Digest:                d0298a41cc57890b1d5d963d225fa2c440b6a3cb6c3c24121ff1bfddb36e865b
```

The vbmeta blob (SHA-256
`3b558db5c34974145337af0f472cc12fdf38f4ff0fc80e706ce468c14d8da205`) is
identical in the original image, the known-good rollback image and the
Phase 1 image. It is signed with the OEM key; the private key is not
available (and is not needed on an unlocked device).

### Boot image v2 parameters

Extracted with `unpack_bootimg --boot_img backup/recovery-current.img`:

| Field | Value |
|---|---|
| magic | `ANDROID!` |
| header version | 2 |
| page size | 2048 |
| kernel size | 22,845,456 |
| kernel load address | `0x00008000` |
| ramdisk size (stock) | 8,555,211 |
| ramdisk load address | `0x05400000` |
| second size | 0 |
| tags load address | `0x00000100` |
| OS version | 11.0.0 |
| OS patch level | 2021-10 |
| cmdline | `console=ttyS1,115200n8 buildvariant=userdebug` |
| recovery DTBO size | 294,408 |
| DTB size | 89,645 |
| DTB address | `0x01F00000` |
| header size | 1,660 |

Kernel, DTB and recovery DTBO are reused unchanged in the Phase 1 image.
Their hashes:

```
kernel          0b98b361b25accd86bdffda1883d1974caa3020bebac3fee19da989db0be69a3
dtb             b34fd2f27a6d20a9eab8cdda664030518e60fcacdff1c8dfcfac3eeaef86837b
recovery_dtbo   13e34fc63ec21418db375013192189e8b91ff91ac0ea877aa905d9c426716ae3
```

## Baseline binary hashes

| Binary | SHA-256 | Notes |
|---|---|---|
| `recovery` (pristine from engineering image) | `7780f3b102a06d50cac7a0c5f918163d2d7cf0e6a2863964b89ab86e72254f69` | stock, still verifies packages |
| `recovery` known-good (signature bypass only) | `7f59a0cdda36e520a0c16f2087be7fe0e7883e15b766da39de80582bcc3b2055` | flashed and tested |
| `librecovery_ui.so` pristine | `f3e10ef33f248069c820f3357ce1427b86adcc99ee8f1cf905f551780e313d26` | identical in original and rollback ramdisks |
| `librecovery_ui.so` bad first attempt | `f1b07f315a4b17e387793af9bf73c00e3265f10d3bc439552cb79a2d262d4b8a` | hook at wrong address; crashed |
| `recovery` bad first attempt | `6bdc4c261b45fcb71cc7e85eb8468d1cc9b103a06455554263c2c0c37f470ed1` | handler-only build |

The bad first-attempt pair is documented because it explains the
`signal 11` crash seen during development: its libui hook was linked at live
code address `0x14d54` instead of a new segment. The final build uses
`0x3c000` in libui and `0x4e200` in recovery, both in newly created executable
segments.

## Ramdisk

The stock ramdisk is a gzip-compressed `newc` cpio archive:

* compressed size 8,555,211 bytes; uncompressed 15,992,216 bytes
* 446 entries in the staging tree (mostly toybox symlinks)
* key files:
  * `/system/bin/recovery` — 314,380 bytes, mode 0755
  * `/system/lib/librecovery_ui.so` — 238,860 bytes, mode 0644
  * `/system/bin/sh` — 215,880 bytes, mode 0755
  * `/system/bin/toybox` — 370,460 bytes, mode 0755

The Phase 1 ramdisk starts from the known-good ramdisk root, replaces the two
recovery binaries, and adds `bash`, `busybox`, `lpmap`, `recovery-tools` and
six busybox symlinks (`ash`, `awk`, `bb`, `unzip`, `vi`, `wget`). Its
compressed size is 9,863,349 bytes.

## Original recovery menu

The stock `librecovery_ui.so` exposes 13 entries. Their runtime order, labels
and action numbers were dumped from `/proc/<pid>/mem` and decoded as libc++
`std::string` objects:

| Index | Label | Action |
|---:|---|---:|
| 0 | Reboot system now | 1 |
| 1 | Reboot to bootloader | 7 |
| 2 | Enter fastboot | 14 |
| 3 | Apply update from ADB | 4 |
| 4 | Apply update from SD card | 2 |
| 5 | Wipe data/factory reset | 5 |
| 6 | Wipe cache partition | 6 |
| 7 | Mount /system | 10 |
| 8 | View recovery logs | 9 |
| 9 | Run graphics test | 11 |
| 10 | Run locale test | 12 |
| 11 | Enter rescue | 16 |
| 12 | Power off | 8 |

The vector sizes observed at runtime were:

* labels: 13 × 12 = **156 bytes**, capacity **192 bytes**
* `menu_items`: 13 × 16 = **208 bytes**

`menu_items` entries are a 12-byte `std::string` label plus a 4-byte action
number at offset `+0xc`. The labels vector is separate and is what
`GetMenuItems()` returns.
