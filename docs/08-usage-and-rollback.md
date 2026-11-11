# 08 — Usage and rollback

## Booting into recovery

Verified methods:

| From | Command / action |
|---|---|
| Android / LineageOS (ADB enabled) | `adb reboot recovery` |
| Bootloader fastboot | `fastboot reboot recovery` |
| Running recovery | menu entry `Reboot rec` (index 17, action 24) |

The device can also be started with its hardware key combination, but the
verified and scriptable paths are the three above.

## fastboot vs. fastbootd

This device distinguishes two fastboot modes:

* **Bootloader fastboot** — the SoC bootloader's fastboot implementation.
  The kernel is not running. `fastboot reboot recovery` performs a real
  reboot.
* **fastbootd** — the userspace fastboot daemon started by the recovery menu
  entry `Enter fastboot` (index 2, action 14). The recovery kernel and
  recovery UI process remain alive. `fastboot flash` works and writes the
  partition, but `fastboot reboot recovery` only exits fastbootd and returns
  to the already-running recovery; the kernel (and therefore the old
  ramdisk) is not restarted.

If you flash a new ramdisk from fastbootd, **always follow it with a real
reboot** (`adb reboot recovery`, a power cycle, or `Reboot rec` from the
menu) before judging the result.

## Menu navigation

```
Volume Down  -> move down one entry
Volume Up    -> move up one entry
Power        -> select
```

The selection resets to index 0 after each action. To reach index *N* in one
burst, send *N* Volume Down key events and then Power. For example, to run
`Save logs` (index 16):

```
16 x KEY_VOLUMEDOWN, then KEY_POWER
```

The menu is drawn on the device screen; the entries are:

```
0  Reboot system now
1  Reboot to bootloader
2  Enter fastboot
3  Apply update from ADB
4  Apply update from SD card
5  Wipe data/factory reset
6  Wipe cache partition
7  Mount /system
8  View recovery logs
9  Run graphics test
10 Run locale test
11 Enter rescue
12 Power off
13 Mount all
14 Unmount
15 Part info
16 Save logs
17 Reboot rec
```

## Shell access

ADB in recovery runs as root:

```
adb shell
```

Static tools are in `/system/bin`:

```
/system/bin/bash            GNU bash 5.2.37
/system/bin/busybox         BusyBox 1.28.1 (ash, awk, unzip, vi, wget, ...)
/system/bin/lpmap           logical partition mapper / dumper
/system/bin/recovery-tools  the menu backend (can be run manually)
```

Examples:

```bash
/system/bin/bash
# inside bash:
lpmap -l -v
recovery-tools 22          # append partition info to /tmp/recovery.log
```

## Logs

| File | Contents |
|---|---|
| `/tmp/recovery.log` | full recovery log, including backend messages |
| `/mnt/eng/cache/recovery/logs-YYYYmmdd-HHMMSS/recovery.log` | saved bundle |
| `.../dmesg.txt` | kernel log |
| `.../mounts.txt` | `/proc/mounts` |
| `.../lpmap.txt` | logical partition metadata |
| `.../df.txt` | free space |

The stock `View recovery logs` menu entry (index 8) displays
`/tmp/recovery.log`. Run `Save logs` (index 16) to persist a bundle to cache.

After a reboot the cache partition is not mounted at `/mnt/eng/cache`.
Mount it manually:

```bash
mkdir -p /mnt/eng/cache
mount -t ext4 -o rw /dev/block/mmcblk0p52 /mnt/eng/cache
ls /mnt/eng/cache/recovery/
```

or run `Mount all` (index 13) again.

## Rollback

The known-good rollback image is the stock engineering recovery with only the
signature bypass (stock 13-entry menu, no handler). Its hash is:

```
f94286f2aaa757d7dda7bf3ce6a8573dfc7f94d22c2b29579301a9869fba74d4
```

It is kept outside this repository as `backup/recovery-current.img`. To roll
back:

```bash
fastboot flash recovery backup/recovery-current.img
# real reboot required if flashing from fastbootd:
adb reboot recovery
```

If recovery itself is unbootable, enter bootloader fastboot or download mode
using the device's hardware key combination, then flash the rollback image
(or a full stock firmware) from there. Keep a copy of the rollback image on
the host, not only on the phone.

## Safety rules

1. **Do not relock the bootloader** while the Phase 1 image is installed.
   Its AVB hash descriptor still describes the original image, so a locked
   bootloader would refuse to boot recovery.
2. **Do not flash this image on another model or firmware.** The patch
   offsets are specific to the recovery binaries of this device.
3. Keep the rollback image and a copy of the original engineering image.
4. The new menu contains destructive stock actions (wipe data, power off).
   The selection-reset behaviour means a wrong number of key presses can land
   on a different entry; count the presses or watch the screen.

## Rebuilding

See [06-image-build.md](06-image-build.md) and `build/README.md`. The two
scripts, the assembly sources and the linker script are published in
`build/`.
