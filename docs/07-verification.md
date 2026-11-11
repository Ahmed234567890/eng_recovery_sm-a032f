# 07 — Hardware verification (Phase 1)

Everything below was executed on the actual SM-A032F. Timestamps are the
recovery device's local clock. The device serial and other identifying
values are redacted.

## 1. Flash

The final image was written over the recovery partition:

```
$ fastboot flash recovery out/recovery_phase1_fixed.img
Sending 'recovery' (65536 KB)                      OKAY [  1.825s]
Writing 'recovery'                                 OKAY [  1.071s]
Finished. Total time: 2.912s
```

The device was in **fastbootd** (the userspace daemon started by the
`Enter fastboot` menu action), not the bootloader. The flash still wrote the
raw partition. Reading the partition back from recovery proved it:

```
$ adb shell 'dd if=/dev/block/by-name/recovery bs=1048576 count=64 | sha256sum'
82d6dbcf8687a9578b574e9b250057e3187c93aff385e39463c16d7849c3a9f9
```

This matches `images/recovery_phase1_fixed.img` exactly.

Because fastbootd shares the running kernel, the first
`fastboot reboot recovery` only exited fastbootd; uptime and dmesg proved no
kernel restart had occurred. A real reboot was then issued:

```
adb reboot recovery
```

and the device came back with a fresh kernel and the new ramdisk
(`/system/bin/ash` symlink mtime matching the new cpio, uptime ~10 s).

## 2. Boot stability

```
$ adb shell cat /proc/uptime
10.33 73.93

$ adb shell dmesg | grep -E "starting service 'recovery'|received signal"
[    4.849747] init: starting service 'recovery'...
```

Only one recovery service start, no `signal 11`, no restart loop.

Binary hashes on the running device match the build:

```
54009dd289d1898d2b940c4104fdad3743d55dc9b5936101f501f125116313fb  /system/bin/recovery
75f03910470e8f1264db7c7abff4b5f3c7582813173d2bb26dd665415c90aead  /system/lib/librecovery_ui.so
ce28726a84a1a666a206f1dcae28acc171534c398a20b61f6571997797658847  /system/bin/recovery-tools
0e7584355a46b83521276e670baaa74bee32876a0f1a5f24c0d9be0c321ba393  /system/bin/bash
06cfc0564ed51752bde77a142546486b3dde5cf894320834cf4e2c3ff3b1ac38  /system/bin/busybox
ce6affc26667df8861d00c0299092469fd0beb024bb0bee0bbeef19038c956ee  /system/bin/lpmap
```

Shell tools work:

```
$ adb shell '/system/bin/bash --version | head -1'
GNU bash, version 5.2.37(1)-release (arm-unknown-linux-musleabihf)

$ adb shell '/system/bin/busybox | head -2'
BusyBox v1.28.1 (2018-02-15 14:34:02 CET) multi-call binary.
```

## 3. Expanded menu vector

`librecovery_ui.so` was mapped at base `0xece82000`. The `menu_items` vector
object is at base + `0x3aa48` = `0xecebca48`; the labels vector object is at
base + `0x3aa54` = `0xecebca54`. The 24-byte dump below starts at
`0xecebca48`, so its last three words are the labels vector:

```
$ adb shell 'dd if=/proc/269/mem bs=4096 skip=$((0xecebc)) count=1 |
             dd bs=1 skip=$((0xa48)) count=24 | od -An -tx4'
   ed4490e0  ed4491b0  ed4491b0  ed449380
   ed449458  ed449458
```

The last three words are the labels vector:

| Field | Value |
|---|---|
| begin | `0xed449380` |
| end | `0xed449458` |
| capacity | `0xed449458` |
| size | `0xD8` = **216 bytes = 18 entries** |

Decoding the 216 bytes gives the 13 stock strings followed by:

```
13: SHORT len=9  b'Mount all'
14: SHORT len=7  b'Unmount'
15: SHORT len=9  b'Part info'
16: SHORT len=9  b'Save logs'
17: SHORT len=10 b'Reboot rec'
```

The `menu_items` vector remained 13 × 16 bytes; the new actions bypass it via
`hook_invoke`.

## 4. Menu actions

Key injection used the `gpio-keys` device `/dev/input/event1`:
`KEY_VOLUMEDOWN=114`, `KEY_POWER=116`. Each test sent *N* Volume Down
presses followed by Power. The menu selection resets to index 0 after every
action, which was confirmed repeatedly.

### Action 20 — `Mount all` (13 downs)

```
[recovery-tools] action=20 started
[recovery-tools] system: no mapper node (/dev/block/mapper/system), skipped
[recovery-tools] system_ext: no mapper node (/dev/block/mapper/system_ext), skipped
[recovery-tools] vendor: no mapper node (/dev/block/mapper/vendor), skipped
[recovery-tools] product: no mapper node (/dev/block/mapper/product), skipped
[recovery-tools] mounted cache /dev/block/mmcblk0p52 -> /mnt/eng/cache
[recovery-tools] mount all finished
[recovery-tools] action=20 finished
```

`/proc/mounts` contained:

```
/dev/block/mmcblk0p52 /mnt/eng/cache ext4 rw,seclabel,relatime,data=ordered 0 0
```

### Action 21 — `Unmount` (14 downs)

```
[recovery-tools] action=21 started
[recovery-tools] unmounted /mnt/eng/cache
[recovery-tools] unmount all finished
[recovery-tools] action=21 finished
```

Afterwards `grep /mnt/eng /proc/mounts` returned nothing.

### Action 22 — `Part info` (15 downs)

```
[recovery-tools] action=22 started
[recovery-tools] partition information written to /tmp/recovery.log
[recovery-tools] action=22 finished
```

The log contained the markers `===== partition info =====` and
`===== end partition info =====` with `lpmap -l -v`, `/proc/mounts`, mapper
listing and `df -h` between them.

### Action 23 — `Save logs` (16 downs)

```
[recovery-tools] action=23 started
[recovery-tools] mounted cache /dev/block/mmcblk0p52 -> /mnt/eng/cache
[recovery-tools] logs saved to /mnt/eng/cache/recovery/logs-20261111-165247
[recovery-tools] action=23 finished
```

Bundle contents:

```
-rw------- 369     df.txt
-rw------- 231299  dmesg.txt
-rw------- 1488    lpmap.txt
-rw------- 1261    mounts.txt
-rw------- 38376   recovery.log
```

The bundle was still present after the next reboot, proving it is written to
the persistent cache partition.

### Action 24 — `Reboot rec` (17 downs)

The device rebooted. It returned to recovery with a fresh kernel:

```
$ adb shell cat /proc/uptime
6.70 43.38

$ adb shell dmesg | grep "starting service 'recovery'"
[    4.800344] init: starting service 'recovery'...
```

No crash, no manual intervention.

## 5. Unsigned sideload on the flashed image

From the recovery menu, `Apply update from ADB` (index 3, 3 downs + Power)
started sideload mode. The minimal unsigned test package contains:

```
META-INF/com/google/android/update-binary:
  #!/system/bin/sh
  echo "UNSIGNED-SIDELOAD-TEST-OK"
  exit 0
```

Host side:

```
$ adb sideload test-unsigned-ota.zip
serving: 'test-unsigned-ota.zip'  (~47%)    Total xfer: 1.00x
exit code: 0
```

Device log:

```
[   56.992666] Update package verification took 0.0 s (result 0).
[   57.082065] UNSIGNED-SIDELOAD-TEST-OK
[   57.286311] Install from ADB completed with status 0.
```

`result 0` is success; the marker proves `update-binary` actually ran; status
`0` proves the installation completed. Recovery returned to the menu
afterwards.

## 6. Stability summary

| Test | Result |
|---|---|
| Recovery boots from flashed image | ✅ |
| Recovery service crash loop | ✅ none (`signal 11` absent) |
| `librecovery_ui.so` hook | ✅ 216-byte/18-entry vector |
| Stock 13 labels | ✅ unchanged |
| Actions 20, 21, 22, 23, 24 | ✅ all executed |
| Action 24 real reboot | ✅ uptime reset |
| Unsigned sideload | ✅ result 0, status 0 |
| `bash`, `busybox`, `lpmap` | ✅ run |

## Evidence files

* `evidence/action-log-actions20-23.txt` — backend log from the saved bundle
* `evidence/sideload-log.txt` — verification/status lines
* `evidence/lpmap.txt`, `evidence/mounts.txt`, `evidence/df.txt` — bundle
* `evidence/runtime-labels.txt` — decoded runtime vector and labels
* `evidence/partition-hash.txt` — partition read-back hash
* `evidence/hashes.txt` — all artifact hashes

The raw `dmesg.txt` and `recovery.log` from the on-device bundle are not
published because they contain per-unit identifiers and serial numbers. Only
the filtered excerpts above are included.
