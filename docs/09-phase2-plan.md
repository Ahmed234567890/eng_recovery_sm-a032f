# 09 — Phase 2: super enlargement, GApps and AVB repair

> **Status: executed and verified on 2026-11-11.** Phase 1 is unchanged.
> The device boots the Android 14 GSI with MindTheGapps installed, dm-verity
> active, and the Phase 1 recovery still working. Touchscreen support is a
> separate follow-up, not part of this phase.

## Goal

Use the free space in the dynamic `super` partition to enlarge `system` and
`system_ext`, then install MindTheGapps 14.0.0 (ARM) into the GSI's
`/system/product`. No separate `product` logical partition is created: the
GSI already exposes `/product` as a symlink to `/system/product`, and the
enlarged `system` has enough room for it.

## Final `super` layout (slot 0, active)

Extents are in 512-byte sectors. The slot-0 table has seven extents:

| Partition | Extents (sectors) | Sectors | Size |
|---|---|---:|---:|
| `system` | `2,048..2,748,416`, `3,021,120..3,022,848`, `3,819,176..4,399,864`, `4,399,864..5,833,464` | 4,762,384 | **2,438,340,608 B** |
| `system_ext` | `2,748,416..3,021,120`, `5,833,464..5,931,768` | 371,008 | **189,956,096 B** |
| `vendor` | `3,022,848..3,819,176` | 796,328 | 407,719,936 B |
| free | `5,931,768..6,451,200` | 519,432 | 265,949,184 B |

Slot 1 metadata is stale, still describes the old layout, and was not
touched. Only slot 0 (primary at byte `12,288` and backup at byte `143,360`,
64 KiB each) was rewritten.

The two new extents are appended at sector `4,399,864` (for `system`) and
sector `5,833,464` (for `system_ext`). The final `system` table used by
device-mapper is:

```
0        2746368  linear super 2048
2746368  1728     linear super 3021120
2748096  580688   linear super 3819176
3328784  1433600  linear super 4399864
```

## What changed on the device

| Item | Before | After |
|---|---:|---:|
| `system` logical partition | 1,704,337,408 B | 2,438,340,608 B |
| `system` ext4 filesystem | grew with partition | 585,000 × 4,096 = 2,396,160,000 B |
| `system` used / free blocks | — | 551,485 used, 33,515 free |
| `system_ext` logical partition | 139,624,448 B | 189,956,096 B |
| `system_ext` ext4 filesystem | 34,088 blocks | 46,376 blocks, clean |
| `product` partition | absent | absent (uses `/system/product`) |
| GApps | absent | installed in `/system/product` |

The mounted GSI is system-as-root: `/system` is the root of `dm-3`
(`system-verity`), `/product -> /system/product`, and
`/system_ext -> /system/system_ext`. The separate `system_ext` logical
partition exists and was enlarged, but this GSI mounts its in-system copy.

## Backups and artifacts

Everything below lives outside this repository; only hashes are published.
The GApps ZIP is third-party material and is not committed.

| Artifact | Size | SHA-256 |
|---|---:|---|
| Original `system` image | 1,704,337,408 B | `f0a7c8a3f913f1574e23b8fb0c6db8d56e465c5781a551983d0086c63769b37c` |
| Original `system_ext` image | 139,624,448 B | `833dd2fb70f9a5a64c28873b8ec2772d8d8db89fe66a2eb69e0b03229b1b1ef3` |
| GApps-populated `system` before the emergency shrink | 2,438,340,608 B | `590c8b5717d2a2e4bb0f9093dda091b839c6d65d4034d3354899b2873df38f5f` |
| Original `super` metadata region | 274,432 B | `6adb9d54e61e5e086b76a4f0c70423c6fd65007b348d4b03e38646990ac58902` |
| New `super` metadata region | 274,432 B | `c23e2e66905c84d78dad3137581e54be970be8fd686cacc18080bc18bf57befc` |
| Final signed `system` image | 2,438,340,608 B | `5ade7b01b23c09d41d1e97abc030b7096043e693cb13c3d790c31383148708cd` |
| AVB tail written to the device | 42,180,608 B | `7a574af4f0eb2cdab2b33abe4de41873a770e51e9dbe7449d3b948cf0c77226e` |
| Final GApps sideload ZIP | 258,819,740 B | `0b1ede38fec59f14066a5bd4a0eacaa1be8f4f13e7a5e45cb3ea321fee9935e8` |

The slot-0 metadata blob has MD5 `f2e31bbf0594a928c0b64aac6bc1b204`; the
device read-back matched it. Its SHA-256 is
`fdd16e9bc5de6f7242e21aed4f04d213a555555ea6b7ca2a4e1242e66cbd0fe7`.

## Host tools

The recovery ramdisk has no `e2fsck`, `resize2fs` or liblp writer, so all
filesystem and metadata work was prepared on the host and executed from
recovery over ADB.

* **e2fsprogs 1.47.1**, cross-compiled as static 32-bit ARM
  (`e2fsck`, `resize2fs`, `tune2fs`, `dumpe2fs`) and smoke-tested under
  `qemu-arm` before being pushed.
* **`lpmap2`**, a static ARM liblp reader that builds a device-mapper table
  and issues `DM_TABLE_LOAD`/`DM_DEV_CREATE`. The first version of its table
  builder did not link targets: each `dm_target_spec.next` was left zero, so
  only the first extent was reachable. The fix is one line:
  `sp->next = rec`, where `rec` is the size of the current target record.
  Without it the four-extent `system` table maps only the first 1.3 GiB and
  reads return the wrong sectors.
* **`metawrite64`**, a chunked writer with `_FILE_OFFSET_BITS=64` and a
  read-back comparison. The earlier `metawrite` was built without 64-bit
  offsets; any offset ≥ 2 GiB became a negative `off_t` and `pwrite` returned
  `EINVAL`.

## 1. Extending the super metadata

`extend_meta.py` reads a byte-exact dump of `super[0:274432]`, validates the
liblp v10 headers, checksums and the original three-partition/five-extent
table, then appends the two new extents and rebuilds both slot-0 copies:

```
system:      first extent 0, 4 extents
system_ext:  first extent 4, 2 extents
vendor:      first extent 6, 1 extent
```

The script re-parses its own output through the same reader path and checks
that all data extents are non-overlapping and within the `super` block
device. Only `primary0.new` and `backup0.new` were written to the device:

```
/tmp/metawrite64 /dev/block/by-name/super 12288    /tmp/primary0.new
/tmp/metawrite64 /dev/block/by-name/super 143360   /tmp/backup0.new
```

Read-back MD5 of both 64 KiB blobs was `f2e31bbf0594a928c0b64aac6bc1b204`.
The new table maps `system` as four extents and `system_ext` as two; the
on-device `dm-1` table shown above is the proof.

## 2. Growing and shrinking the ext4 filesystem

The first attempt simply ran `resize2fs` to the new partition size. That grew
the ext4 filesystem over the GSI's original AVB footer, which lived at the end
of the old 1,704,337,408-byte `system` partition. On the next boot, first-stage
AVB found no `AVBf` footer, `fs_mgr` skipped `system`, and the device
bootlooped.

The fix is to leave room at the end of the partition for a complete AVB
hashtree, vbmeta and footer:

```sh
# On the device, with the logical system mapped:
/tmp/e2fsck -fy /dev/block/mapper/system
/tmp/resize2fs /dev/block/mapper/system 585000
/tmp/e2fsck -fn /dev/block/mapper/system
```

585,000 blocks = **2,396,160,000 bytes**, leaving 42,180,608 bytes for AVB.
The maximum filesystem that still fits a footer is 592,388 blocks; 585,000
was chosen for headroom. The filesystem was pulled exactly to that length and
checked again on the host:

```
e2fsck 1.47.4: 6866/143136 files, 551485/585000 blocks
sha256 a456e2e3700b5ff8ddd6783d6de5de6b79e886c477aed5ad755e987f24f46dfa
```

## 3. Rebuilding AVB

The GSI uses a **hashtree** descriptor for dm-verity, not a hash descriptor.
`avbtool add_hash_footer` produces the wrong descriptor type and was not
used. The correct command is:

```sh
avbtool add_hashtree_footer \
  --image system-resized.img \
  --partition_size 2438340608 \
  --partition_name system \
  --hash_algorithm sha1 \
  --salt ea2e46fb2195049723d888cd4c9d6ecb4c9e2bd7 \
  --do_not_generate_fec \
  --algorithm SHA256_RSA2048 \
  --key "$TESTKEY" \
  --prop com.android.build.system.os_version:14 \
  --prop 'com.android.build.system.fingerprint:google/lineage_a64_bvN/tdgsi_a64_ab:14/AP2A.240905.003/eng.crossg.20250125.124910:userdebug/test-keys' \
  --prop com.android.build.system.security_patch:2024-12-01
```

The salt, hash algorithm, os_version, fingerprint and security patch were
copied from the original footer's vbmeta. `avbtool` pads SHA-1 digests to the
same width as SHA-256, so the tree is **18,874,368 bytes**, not the ~11.8 MB
a 20-byte-digest calculation predicts.

Resulting footer values:

| Field | Value |
|---|---|
| Image size | 2,396,160,000 B |
| Tree offset | 2,396,160,000 |
| Tree size | 18,874,368 B |
| VBMeta offset | 2,415,034,368 |
| VBMeta size | 1,664 B |
| Root digest | `0d3a0bbabb866b2e2f8a1451120925739a55c7fd` |
| Public key SHA-1 | `cdbb77177f731920bbe0a0f94f84d9038ae0617d` |
| Flags | 0 |

`avbtool verify_image` passed both the vbmeta signature and the SHA-1
hashtree over the whole 2,396,160,000-byte image.

The replacement key is a test key, not the OEM key. This unit is unlocked
(`androidboot.flash.locked=0`, verified boot state `orange`); `fs_mgr`
allows an unknown footer key in that state, logs a warning and continues.
The top-level `vbmeta` and `vbmeta_system` partitions were not modified.

The 42,180,608-byte tail (hashtree + vbmeta + footer) was written at offset
`2,396,160,000` with `metawrite64`. An in-place read-back and an independent
`dd` both matched the host tail hash. A final full-partition comparison
matched the signed image byte-for-byte:

```
first 2,396,160,000 B sha256  a456e2e3...  (matches host)
tail                   sha256  7a574af4...  (matches host)
last 64 B                     "AVBf" footer
```

### The two-block write accident

During boundary testing, 4 KiB blocks were written at byte offsets
`1,800,000,000` and `2,000,000,000`, which are **not** 4 KiB-aligned. Each
write shifted a block and changed two filesystem blocks. `e2fsck` still
passed, but the full-partition hash did not. Both blocks were restored from
the clean pulled image and the full hash then matched. Do not write to a
device at unaligned offsets, even when writing back identical data.

## 4. GApps installation

The prepared package was MindTheGapps 14.0.0 (ARM). Its installer was
repacked with three changes:

1. `#!/sbin/sh` became `#!/system/bin/sh` (this recovery has no `/sbin/sh`).
2. The `system_ext` symlink check was removed. On this GSI
   `/system/system_ext` is a symlink, but a real enlarged `system_ext`
   logical partition exists. Keeping `SYSTEM_EXT_BLOCK` routes the payload to
   the real partition as well as the in-system copy created by the main
   `cp`. The `product` symlink is still ignored, so the payload lands in
   `/system/product` as intended.
3. Provision cleanup was extended to the real `/system_ext` path when
   `SYSTEM_EXT_BLOCK` is set.

The installer was sideloaded from the Phase 1 recovery. It is **not** in this
repository. Verified after boot:

| Component | Path | Version |
|---|---|---|
| Google Play services | `/system/product/priv-app/GmsCore` | 23.25.18 (190300-549347153) |
| Google Play Store | `/system/product/priv-app/Phonesky` | 36.6.25-29 |
| Google Services Framework | `/system/product/priv-app` | installed |
| SetupWizard | `/system/product/priv-app` | installed, `user_setup_complete=1` |

`/system/product` uses about 853 MB. `/system` has 131 MiB free (95% used),
which is expected for a GSI with a full GApps package.

## 5. Boot verification

```
ro.build.version.release       14
ro.build.version.sdk           34
sys.boot_completed             1
ro.boot.veritymode             enforcing
ro.boot.verifiedbootstate      orange
root mount                     /dev/block/dm-3 / ext4 ro,seclabel,relatime
```

`dm-3` is `system-verity`. `/vendor` is `dm-4`. `logcat -b crash` was empty
immediately after boot, and GMS, Play Store, SetupWizard and their background
processes were running.

One cosmetic issue was observed on a later boot: `bootanimation` crashed once
with `SIGSEGV` in `libgui` (`Transaction::setLayer`, null layer state) and did
not restart. Boot completed normally with no crash loop. This is a
GSI/vendor display-composer mismatch, not a partition or AVB failure.

## 6. Phase 1 recovery regression check

The recovery partition was never written in Phase 2. Its SHA-256 still
matches the Phase 1 image:

```
82d6dbcf8687a9578b574e9b250057e3187c93aff385e39463c16d7849c3a9f9
```

The device was rebooted into recovery and all five Phase 1 actions were
exercised again with key injection on `/dev/input/event1`:

| Action | Menu entry | Result |
|---:|---|---|
| 20 | `Mount all` | ran and finished |
| 21 | `Unmount` | ran and finished |
| 22 | `Part info` | wrote the partition-info markers to `/tmp/recovery.log` |
| 23 | `Save logs` | created a new bundle under `/mnt/eng/cache/recovery/` |
| 24 | `Reboot rec` | rebooted to a fresh recovery kernel (uptime reset) |

The recovery binary, `librecovery_ui.so`, `recovery-tools` and `lpmap`
hashes still match the Phase 1 build. Android was then booted again and
reached `sys.boot_completed=1`.

## Lessons learned

1. **Always leave room for AVB at the end of `system`.** `resize2fs` will
   happily overwrite an inline AVB footer; the first-stage mount then fails
   with no useful UI message. Calculate `filesystem + tree + vbmeta + 64`
   first, and choose a size below the maximum.
2. **`add_hashtree_footer`, not `add_hash_footer`.** A GSI with dm-verity
   needs a hashtree descriptor. A hash descriptor produces a valid-looking
   footer that will not set up `system-verity`.
3. **avbtool pads SHA-1 digests to 32 bytes.** Do not size the hashtree from
   the nominal 20-byte digest; let `avbtool` generate it and read the
   descriptor afterwards.
4. **32-bit `off_t` silently breaks writes above 2 GiB.** `pwrite` returns
   `EINVAL` for a negative offset. Cross-compile such tools with
   `-D_FILE_OFFSET_BITS=64` and chunk the writes.
5. **Android shell arithmetic is 32-bit.** `$((2438340608/4096-16))`
   overflowed and produced a negative `dd skip`. Use literal block numbers
   for large offsets, or compute on the host.
6. **Verify the whole partition, not just the bytes you wrote.** The
   in-place read-back proved the tail was correct while two earlier unaligned
   writes had corrupted unrelated blocks. Compare a full-image hash against
   the host artifact.
7. **Multi-extent device-mapper tables need `dm_target_spec.next`.** A
   zeroed `next` makes every target after the first invisible; `blockdev`
   still reports the full size, so the failure only shows up on reads.
8. **Test recovery after partition work.** Because recovery lives outside
   `super`, it is an independent known-good path; re-testing it costs a few
   minutes and proves the rollback route still exists.

## Rollback outline

The original `system`, `system_ext` and `super` metadata are backed up
outside the repository. To roll back:

1. Boot the Phase 1 recovery and map `super` with `lpmap2` (or write the
   original slot-0 metadata first).
2. Write `system-before.img` and `system_ext-before.img` back to their
   logical partitions, or restore the GApps-populated
   `system-gapps-before-shrink.img` if the GApps state should be kept.
3. Restore `super-meta-original.bin` to `super[0:274432]`.
4. `e2fsck -fn` both filesystems and confirm the Phase 1 recovery still
   boots.

Slot 1 was never used and remains stale; do not switch to it.

## Explicit non-goals

* No separate `product` logical partition.
* No changes to `vendor`, `vbmeta`, `vbmeta_system`, `boot` or `recovery`.
* No touchscreen enablement. That remains a separate follow-up.
