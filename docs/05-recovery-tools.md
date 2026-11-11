# 05 — The `/system/bin/recovery-tools` backend

The new menu actions do not contain C code for mounting or logging. The
recovery handler executes a shell script:

```
/system/bin/sh /system/bin/recovery-tools <action>
```

The script is included in the ramdisk with mode 0755 and the shebang
`#!/system/bin/sh`.

## Actions

| Number | Menu label | Function |
|---:|---|---|
| 20 | `Mount all` | Mount cache, logical partitions (if mapper nodes exist), and an external SD card under `/mnt/eng` |
| 21 | `Unmount` | Unmount everything mounted under `/mnt/eng` |
| 22 | `Part info` | Append `lpmap -l -v`, `/proc/mounts`, mapper nodes and `df -h` to the recovery log |
| 23 | `Save logs` | Write a complete diagnostic bundle to the cache partition |
| 24 | `Reboot rec` | Sync and reboot back into recovery |

Every invocation appends `action=N started` / `action=N finished` (or an
error explanation) to `/tmp/recovery.log`, which is the same file shown by
the stock `View recovery logs` menu entry.

## Paths

```
LOG        /tmp/recovery.log
ENG        /mnt/eng
CACHE      /mnt/eng/cache
CACHE_DEV  /dev/block/mmcblk0p52     (the cache partition)
LP         /system/bin/lpmap
PATH       /system/bin:/sbin:/bin
```

## Mount all (20)

1. `mkdir -p /mnt/eng`.
2. For `system`, `system_ext`, `vendor`, `product`:
   * if `/mnt/eng/<name>` is already mounted, keep it;
   * if `/dev/block/mapper/<name>` exists, mount it read-only;
   * otherwise look for the same block device already mounted elsewhere in
     `/proc/mounts` and bind-mount the existing mountpoint;
   * if neither exists, log
     `"<name>: no mapper node (...), skipped"` and continue.
3. Mount the cache partition read-write at `/mnt/eng/cache` (ext4).
4. Try `/dev/block/mmcblk1p1` or `/dev/block/mmcblk1` as a read-only VFAT
   external SD card at `/mnt/eng/sdcard`.

**Known limitation on this device:** the recovery kernel exposes no
`/dev/block/mapper/system`, `system_ext`, `vendor` or `product` nodes. The
log therefore shows all four logical partitions as skipped; only cache (and
possibly the SD card) mounts. Mapping the logical partitions with `lpmap`
inside recovery is a Phase 2 task.

## Unmount (21)

Unmounts, in reverse order:

```
/mnt/eng/sdcard
/mnt/eng/product
/mnt/eng/vendor
/mnt/eng/system_ext
/mnt/eng/system
/mnt/eng/cache
```

Only mountpoints that appear in `/proc/mounts` are touched. The stock
recovery's own `/cache` mount is **not** affected; the script only manages
its own `/mnt/eng/*` tree.

## Part info (22)

Appends the following to `/tmp/recovery.log` between two markers:

```
===== partition info =====
<date>
--- lpmap -l -v ---
... logical partition metadata ...
--- /proc/mounts ---
...
--- /dev/block/mapper ---
...
--- df -h ---
...
===== end partition info =====
```

This is the main diagnostic tool for Phase 2: it shows the `super`
partition's extents, the logical partition sizes and the free space.

## Save logs (23)

1. Ensures the cache partition is mounted (`mount_cache`).
2. Creates `/mnt/eng/cache/recovery/logs-YYYYmmdd-HHMMSS/`.
3. Copies or writes:
   * `recovery.log` — the full recovery log;
   * `dmesg.txt` — kernel log;
   * `mounts.txt` — `/proc/mounts`;
   * `lpmap.txt` — `lpmap -l -v` output;
   * `df.txt` — `df -h` output.
4. `sync`, then logs `logs saved to <dir>`.

The directory is created with the umask in effect (observed mode `0700`).
The bundle survives a reboot because it is on the cache partition. After a
reboot the cache is not mounted automatically at `/mnt/eng/cache`; mount it
manually or run `Mount all` again.

## Reboot rec (24)

```
sync
/system/bin/reboot recovery
```

The recovery `reboot` tool writes the recovery boot command and reboots. On
this device the result is a genuine kernel reboot into the recovery
partition; uptime resets and the recovery service starts again.

## Full script

The canonical copy is in [`tools/recovery-tools`](../tools/recovery-tools).
It is 4,234 bytes, SHA-256
`ce28726a84a1a666a206f1dcae28acc171534c398a20b61f6571997797658847`.
