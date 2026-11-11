# 09 — Phase 2 plan (not executed)

> **Status: not started.** Phase 1 ends with this repository. The user must
> explicitly start Phase 2 before any super-partition metadata, ext4
> filesystem or GApps changes are made.

## Goal

Enlarge the dynamic `system` and `system_ext` logical partitions, create a
`product` logical partition, and install MindTheGapps 14.0.0 (ARM) into the
GSI's `/system/product`.

## Chosen GApps package

```
MindTheGapps-14.0.0-arm-20250203_195950.zip
```

A prepared copy exists outside this repository at
`/path/to/MindTheGapps-prepared.zip` (258,819,588 bytes).
It has the expected metadata and a `/system/bin/sh` shebang in its installer.
It is **not** published here (size and third-party licensing).

## Current `super` layout (slot 0, active)

Extents are in 512-byte sectors:

| Partition | Extents | Size |
|---|---|---:|
| `system` | `2048..2,748,416`, `3,021,120..3,022,848`, `3,819,176..4,399,864` | 1,704,337,408 B |
| `system_ext` | `2,748,416..3,021,120` | 139,624,448 B |
| `vendor` | `3,022,848..3,819,176` | 407,719,936 B |
| `product` | absent | — |
| free | `4,399,864..6,451,200` | 1,050,284,032 B |

Slot 1 metadata is stale and still lists a `product` partition; it is not the
active slot.

## Planned new layout

Add the free extents to `system` and `system_ext`:

| Partition | Added extent | New total size |
|---|---|---:|
| `system` | `4,399,864..5,833,464` | **2,438,340,608 B** |
| `system_ext` | `5,833,464..5,931,768` | **189,956,096 B** |
| `vendor` | unchanged | 407,719,936 B |
| `product` | to be created (size TBD) | — |

Planned super group maximum: **3,298,820,096 bytes**.

These numbers were derived from `lpdump`/`lpmap` output on the live device.
They must be re-read and re-validated immediately before any Phase 2 write;
do not assume they are still current after a firmware update.

## Blockers discovered in Phase 1

1. **No `e2fsck` / `resize2fs` in the recovery ramdisk.** Toybox in this
   recovery does not provide them. Growing the ext4 filesystems after
   enlarging the logical partitions therefore requires either:
   * adding static ARM `e2fsck` and `resize2fs` binaries to the ramdisk, or
   * doing the resize offline from a host that can access the block device
     (e.g. via a USB mass-storage export or a dedicated recovery image).
2. **No `/dev/block/mapper/*` nodes in recovery.** `Mount all` currently
   skips all logical partitions. `lpmap` can create/map them, but the
   mapping and the filesystem resize order must be designed carefully.
3. **AVB / super metadata.** Changing the super metadata invalidates the
   vbmeta descriptor for `super`; the device is unlocked, so verification is
   skipped, but the metadata must remain structurally valid or the
   bootloader/GSI will fail to mount the logical partitions.
4. **GApps installation path.** The prepared package installs into
   `/system/product`. The GSI's product partition is currently absent, so
   the new `product` logical partition (or a product directory inside
   `system`) must exist before the package is applied.

## Planned order of operations (high level)

1. Re-read `lpmap -l -v`, `lpdump` and `df` from the current boot; confirm
   the free extents.
2. Back up the current `super` metadata (and, if practical, the affected
   logical partitions) to the host.
3. Add the new extents to `system` and `system_ext`; create `product`.
4. Update the super metadata and the slot-0 geometry.
5. `e2fsck -f` and `resize2fs` the enlarged ext4 filesystems.
6. Verify the GSI still boots and mounts `system`, `system_ext`, `vendor`.
7. Apply the prepared MindTheGapps package and verify the product files.
8. Re-run the Phase 1 recovery verification (menu, sideload, tools).

Steps 3–6 are the risky part: a metadata mistake can make the GSI unbootable.
A full `super` backup or a known-good GSI reflash path must be available
before starting.

## Explicit non-goals for Phase 1

* No `super` metadata writes.
* No ext4 resize.
* No GApps installation.
* No changes outside the recovery partition.
