# Engineering Recovery for Samsung Galaxy A03 Core (SM-A032F)

Binary-only modification of the stock Android 11 engineering recovery for the
Samsung Galaxy A03 Core (Unisoc SC9863A / `m168`). No AOSP source tree is
rebuilt: the existing recovery executable, the existing `librecovery_ui.so`
and the existing ramdisk are patched in place.

**Phase 1 is complete and verified on hardware.** Phase 2 (super partition
enlargement + MindTheGapps) has not been started.

---

## What this project delivers

* **Unsigned sideload support** — the stock recovery's package signature check
  is bypassed with a four-byte patch. Both signed and unsigned OTA packages
  are accepted.
* **Five extra recovery menu entries** — `Mount all`, `Unmount`, `Part info`,
  `Save logs`, `Reboot rec`, appended after the stock 13 entries without
  touching the stock menu data.
* **A shell backend** — `/system/bin/recovery-tools` implements the new
  actions. Static ARM `bash`, `busybox` and `lpmap` are included in the
  ramdisk, so recovery has a usable shell environment.
* **A rebuildable 64 MiB recovery image** — raw Android boot image v2 +
  the original OEM-signed `vbmeta` blob + a regenerated AVB footer.

## Current status

| Item | State |
|---|---|
| Recovery boots on SM-A032F | ✅ verified |
| Unsigned sideload | ✅ verified (`result 0`, status `0`) |
| Stock 13 menu entries | ✅ intact |
| 5 new menu entries | ✅ verified |
| Actions 20–24 | ✅ verified end-to-end |
| `bash` / `busybox` / `lpmap` | ✅ run from recovery |
| GApps / super enlargement | ⏳ Phase 2, not started |

## Quick start

```bash
# Flash the finished image (device in fastboot / fastbootd)
fastboot flash recovery images/recovery_phase1_fixed.img
fastboot reboot recovery      # may only leave fastbootd; see note below

# If the device comes back up in Android instead:
adb reboot recovery
```

> **fastbootd vs. bootloader fastboot.** The recovery menu item
> `Enter fastboot` starts the *userspace* fastboot daemon (`fastbootd`) inside
> the running recovery kernel. `fastboot flash recovery` works there, but
> `fastboot reboot recovery` only leaves fastbootd and returns to the existing
> recovery UI — the kernel does not restart, so the freshly flashed ramdisk is
> not loaded. Use `adb reboot recovery` (or a real power cycle) to boot the
> new image.

### Menu navigation

| Key | Action |
|---|---|
| Volume Down | move selection down |
| Volume Up | move selection up |
| Power | select |

The selection **resets to index 0 after every action**. To reach entry *N*,
send *N* Volume Down presses and then Power. The new entries are indexes
13–17:

| Index | Label | Action |
|---:|---|---:|
| 13 | `Mount all` | 20 |
| 14 | `Unmount` | 21 |
| 15 | `Part info` | 22 |
| 16 | `Save logs` | 23 |
| 17 | `Reboot rec` | 24 |

## Repository layout

```
README.md                  this file
SHA256SUMS                 hashes for every published file
docs/                      detailed engineering notes (start at 00-index.md)
  00-index.md              documentation map
  01-device-and-baseline.md
  02-signature-bypass.md
  03-menu-expansion.md
  04-action-handler.md
  05-recovery-tools.md
  06-image-build.md
  07-verification.md
  08-usage-and-rollback.md
  09-phase2-plan.md
  10-pitfalls.md
build/                     exact patch/build sources used
  patch_phase1.py          builds the two patched ELF files
  build_phase1_fixed.py    stages the ramdisk and builds the 64 MiB image
  ui_hook2.s               libui hook source (Thumb-2)
  ui_hook2.bin             assembled 288-byte hook blob
  handler.s                recovery action handler source (Thumb-2)
  handler.ld               linker script for the handler
  handler.bin              assembled 155-byte handler blob
  README.md                build inputs and environment
tools/
  recovery-tools           menu backend shell script
  bash                     static ARM bash 5.2.37
  busybox                  static ARM busybox 1.28.1
  lpmap                    static ARM logical-partition mapper/dumper
binaries/
  recovery_patched         Phase 1 `/system/bin/recovery`
  librecovery_ui_patched.so
images/
  recovery_phase1_fixed.img  64 MiB flashable image
evidence/                  verification transcripts and hashes
  action-log-actions20-23.txt
  sideload-log.txt
  lpmap.txt
  mounts.txt
  df.txt
  runtime-labels.txt
  partition-hash.txt
  hashes.txt
```

The OEM `recovery`, `librecovery_ui.so`, kernel, DTB, recovery DTBO and
`vbmeta` blob are intentionally **not** published. The build scripts take
them as arguments; see [build/README.md](build/README.md).

## Artifact hashes

| File | Size | SHA-256 |
|---|---:|---|
| `images/recovery_phase1_fixed.img` | 67,108,864 | `82d6dbcf8687a9578b574e9b250057e3187c93aff385e39463c16d7849c3a9f9` |
| `binaries/recovery_patched` | 323,584 | `54009dd289d1898d2b940c4104fdad3743d55dc9b5936101f501f125116313fb` |
| `binaries/librecovery_ui_patched.so` | 249,856 | `75f03910470e8f1264db7c7abff4b5f3c7582813173d2bb26dd665415c90aead` |
| `tools/recovery-tools` | 4,234 | `ce28726a84a1a666a206f1dcae28acc171534c398a20b61f6571997797658847` |
| `tools/bash` | 1,256,856 | `0e7584355a46b83521276e670baaa74bee32876a0f1a5f24c0d9be0c321ba393` |
| `tools/busybox` | 1,079,156 | `06cfc0564ed51752bde77a142546486b3dde5cf894320834cf4e2c3ff3b1ac38` |
| `tools/lpmap` | 28,548 | `ce6affc26667df8861d00c0299092469fd0beb024bb0bee0bbeef19038c956ee` |

Rollback image (known-good signature bypass, stock menu):

| File | Size | SHA-256 |
|---|---:|---|
| `recovery-current.img` (not in repo) | 67,108,864 | `f94286f2aaa757d7dda7bf3ce6a8573dfc7f94d22c2b29579301a9869fba74d4` |

## Target device

* Samsung Galaxy A03 Core **SM-A032F** (`m168`, Unisoc SC9863A, 2 GB RAM)
* Android 11 vendor firmware, bootloader **unlocked** (`verifiedbootstate=orange`,
  `flash.locked=0`)
* Running a **LineageOS 21 GSI** (Android 14,
  `21.0-20250125-UNOFFICIAL-a3core`)
* Recovery partition: `/dev/block/mmcblk0p41`, **64 MiB**, raw

## Safety

* Flashing the recovery partition does **not** touch user data, but a wrong
  image can make recovery (and therefore sideload/factory reset) unusable
  until a known-good image is flashed again.
* This project was developed for one specific device and firmware. The
  offsets are specific to the recovery binaries extracted from that device.
  Do not flash this image on another model.
* The AVB footer is regenerated, but the embedded `vbmeta` blob is the
  original OEM-signed one and still describes the original 31,823,872-byte
  recovery image. Verification is therefore **not** valid on a locked device.
  This image is intended for unlocked devices, where AVB verification is
  skipped. Do not relock the bootloader with this image installed.
* Keep a known-good rollback image. See
  [docs/08-usage-and-rollback.md](docs/08-usage-and-rollback.md).

## Legal

The patched executables and the flashable image are derivative works of
Samsung/Unisoc firmware and are provided **as-is**, without warranty, for
personal recovery of the owner's device. Samsung, Android, LineageOS,
MindTheGapps, bash, busybox and lpmap remain the property of their respective
owners and are governed by their own licenses. No signing keys or other
secret material are included in this repository.
