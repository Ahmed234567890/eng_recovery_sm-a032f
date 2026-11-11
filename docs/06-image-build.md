# 06 — Building the 64 MiB recovery image

Two scripts rebuild the complete image:

1. **`build/patch_phase1.py`** — patches the two ELF files.
2. **`build/build_phase1_fixed.py`** — stages the ramdisk, packs it, builds
   the Android boot image and wraps it with AVB.

The published scripts are portable: every input and output path is an
explicit argument (there are no machine-specific path constants). A complete
invocation is shown in [`build/README.md`](../build/README.md). The scripts
are the same logic that produced the verified artifacts; only the path
handling was parameterized.

## Required inputs

| Input | Where it comes from | Hash / size |
|---|---|---|
| Known-good `recovery` binary | ramdisk of `backup/recovery-current.img` (signature bypass only) | `7f59a0cd…`, 314,380 B |
| Pristine `librecovery_ui.so` | `ramdisk/system/lib/` of the engineering ramdisk | `f3e10ef3…`, 238,860 B |
| Known-good ramdisk root | `unpack_bootimg` + `cpio` extraction of `backup/recovery-current.img` | 446 entries |
| Kernel | extracted from the same boot image | `0b98b361…`, 22,845,456 B |
| DTB | extracted from the same boot image | `b34fd2f2…`, 89,645 B |
| Recovery DTBO | extracted from the same boot image | `13e34fc6…`, 294,408 B |
| Original vbmeta blob | bytes at `0x1E5A000` of the engineering image | `3b558db5…`, 2,112 B |
| `handler.bin` | assembled from `build/handler.s` + `handler.ld` | 155 B |
| `ui_hook2.bin` | assembled from `build/ui_hook2.s` | 288 B |
| Tools | `tools/recovery-tools`, `tools/bash`, `tools/busybox`, `tools/lpmap` | see README |

`build/patch_phase1.py` asserts the original bytes at every patch site before
writing, so a wrong input binary fails loudly rather than producing a corrupt
image.

## Step 1 — Patch the ELF files

```
$ python3 build/patch_phase1.py \
    --recovery-base dump/root/system/bin/recovery \
    --libui-base    dump/root/system/lib/librecovery_ui.so
recovery: PT_NOTE phdr index 10
recovery: wrote binaries/recovery_patched (323584 bytes, handler 155 bytes)
libui: PT_NOTE phdr index 8
libui: wrote binaries/librecovery_ui_patched.so (249856 bytes, hook 288 bytes)
```

The script performs, in order:

**recovery**

1. Assert the default branch bytes `00 f2 64 85` at file `0x1629e`; write
   `36 f2 af 87`.
2. Replace program header #10 (`PT_NOTE`) with an R+X `PT_LOAD` at
   `0x4e000`.
3. Extend the file to `0x4f000` and write `handler.bin` at `0x4e200`.

**libui**

1. Assert `01 48 78 44` at file `0x133e8`; write `27 f0 0a be`.
2. Assert `03 48 78 44` at file `0x133f4`; write `27 f0 84 be`.
3. Replace program header #8 (`PT_NOTE`) with an R+X `PT_LOAD` at
   `0x3c000`.
4. Extend the file to `0x3d000` and write `ui_hook2.bin` at `0x3c000`.

The outputs are the files published under `binaries/`.

## Step 2 — Stage the ramdisk

Start from the known-good ramdisk root and overlay:

```
system/bin/recovery                 <- binaries/recovery_patched      (0755)
system/lib/librecovery_ui.so        <- binaries/librecovery_ui_patched.so (0644)
system/bin/recovery-tools           <- tools/recovery-tools          (0755)
system/bin/bash                     <- tools/bash                    (0755)
system/bin/busybox                  <- tools/busybox                 (0755)
system/bin/lpmap                    <- tools/lpmap                   (0755)
system/bin/{ash,awk,bb,unzip,vi,wget} -> busybox
```

`build/build_phase1_fixed.py` removes and recreates `<work>/fixed-root` on
each run, so the content is deterministic. The read-only `config` directory
keeps its original `0555` mode; all other modes come from the known-good
ramdisk.

## Step 3 — Pack the ramdisk

```
$ cd <work>/fixed-root
$ find . | cpio -o -H newc --owner 0:0 --quiet > ../fixed-ramdisk.cpio
$ gzip -9 -n -c ../fixed-ramdisk.cpio > ../fixed-ramdisk.gz
```

Key points:

* **`newc`** is the initramfs format expected by the Android 11 kernel.
* **`--owner 0:0`** forces every entry to `root:root`, regardless of the
  build user's UID/GID. The stock ramdisk is root-owned and init expects
  that.
* **`gzip -9 -n`** removes gzip's own timestamp and file name, so the
  compressed stream does not depend on when or where it was built. The cpio
  metadata (inode numbers and file mtimes) is still host-dependent; see
  [Reproducibility](#reproducibility).
* The cpio begins with the `.` entry, exactly like the stock ramdisk.

Result: **9,863,349 bytes**, SHA-256
`a572d0fa3c6a168f7de1633a62031b2e33e121b9a986c6a36af7964a53201581`.

Verification performed after packing:

* `cpio -itv` shows `root root` ownership and correct modes;
* extracting the archive and hashing the key files matches the patched
  binaries and tools;
* the six busybox symlinks point to `busybox`.

## Step 4 — Build the Android boot image v2

```
mkbootimg \
  --kernel        dump/kernel \
  --ramdisk       <work>/fixed-ramdisk.gz \
  --recovery_dtbo dump/recovery_dtbo \
  --dtb           dump/dtb \
  --cmdline       "console=ttyS1,115200n8 buildvariant=userdebug" \
  --base          0x0 \
  --kernel_offset 0x8000 \
  --ramdisk_offset 0x05400000 \
  --tags_offset  0x100 \
  --dtb_offset    0x1f00000 \
  --pagesize      2048 \
  --header_version 2 \
  --os_version    11.0.0 \
  --os_patch_level 2021-10 \
  -o <work>/fixed-boot.img
```

With `--base 0x0`, the offset arguments become the literal load addresses in
the header, matching the stock image:

| Header field | Value |
|---|---|
| kernel load address | `0x00008000` |
| ramdisk load address | `0x05400000` |
| tags load address | `0x00000100` |
| DTB address | `0x01F00000` |
| page size | 2048 |
| header version | 2 |
| OS version | 11.0.0 (encoded `0x1600015a`) |
| OS patch level | 2021-10 |
| cmdline | `console=ttyS1,115200n8 buildvariant=userdebug` |

Result: **33,099,776 bytes**, SHA-256
`510ac745a3b13c7ea0c50acf7b8c242c4e95241c2a9a761ebadd361b8222a861`.

`unpack_bootimg` on the result reproduces all fields, with the new ramdisk
size (9,863,349) and correspondingly recomputed `recovery_dtbo_offset`
(`0x1F33000`) and DTB position. The bootloader reads these from the header,
so the shift is expected and harmless.

## Step 5 — Wrap with AVB

The original 2,112-byte OEM-signed vbmeta blob is reused. Only the footer is
regenerated:

```
cp <work>/fixed-boot.img images/recovery_phase1_fixed.img
avbtool append_vbmeta_image \
  --image images/recovery_phase1_fixed.img \
  --partition_size 67108864 \
  --vbmeta_image dump/vbmeta-original.bin
```

`append_vbmeta_image`:

1. pads the raw boot image up to the 4096-byte block size (the raw image is
   already 4096-aligned, so no padding is needed here);
2. writes the vbmeta blob padded to 4096 bytes at `vbmeta_offset`;
3. fills the gap up to `partition_size - 4096` with don't-care zeros;
4. writes a 4096-byte footer block whose last 64 bytes are the `AVBf`
   footer.

Final layout:

```
0x00000000  raw boot image                                33,099,776 B
0x01F91000  vbmeta blob (2,112 B) + zero padding to 4 KiB
0x01F92000  zero fill
0x03FFF000  footer block (4,032 zero bytes + 64-byte footer)
0x04000000  end (64 MiB)
```

Result: **67,108,864 bytes**, SHA-256
`82d6dbcf8687a9578b574e9b250057e3187c93aff385e39463c16d7849c3a9f9`.

`avbtool info_image` confirms:

```
Footer version:           1.0
Image size:               67108864 bytes
Original image size:      33099776 bytes
VBMeta offset:            33099776
VBMeta size:              2112 bytes
Algorithm:                SHA256_RSA4096
Hash descriptor:
  Image Size:             31823872 bytes
  Partition Name:         recovery
  Digest:                 d0298a41...
```

## Important AVB caveat

The descriptor inside the reused vbmeta blob still describes the **original**
31,823,872-byte image and its digest. The footer correctly points at the blob
for the new image, but the blob's hash descriptor no longer matches the new
boot image. On a **locked** device, AVB verification would fail and recovery
would not boot.

The target device is unlocked (`androidboot.verifiedbootstate=orange`), so
the bootloader skips verification. This image is explicitly for unlocked
devices. Do not relock the bootloader while it is installed.

Re-signing with a key that the bootloader trusts is not possible without the
OEM private key. The original `vbmeta` blob is reused only so the partition
keeps the expected AVB structure and the bootloader's metadata path does not
see a malformed footer.

## Copy the artifacts

At the end of the build:

```
binaries/recovery_patched            323,584 B  sha256 54009dd2…
binaries/librecovery_ui_patched.so   249,856 B  sha256 75f03910…
<work>/fixed-ramdisk.gz            9,863,349 B  sha256 a572d0fa…
<work>/fixed-boot.img             33,099,776 B  sha256 510ac745…
images/recovery_phase1_fixed.img  67,108,864 B  sha256 82d6dbcf…
```

## Reproducibility

`build/patch_phase1.py` is byte-exact: running it against the same two input
binaries and the published `handler.bin` / `ui_hook2.bin` reproduces
`binaries/recovery_patched` (`54009dd2…`) and
`binaries/librecovery_ui_patched.so` (`75f03910…`) exactly. This was verified
with `cmp`.

The image build is content-reproducible but not byte-reproducible from a
**fresh** staging directory. The `newc` cpio format stores each file's host
inode number and modification time. `build_phase1_fixed.py` creates a new
staging tree on every run, so those values differ from the original build
even though every payload byte is identical.

Verification of a fresh rebuild against the published image:

* same 448 cpio entries in the same order;
* 0 differences in file contents, sizes, modes or symlink targets;
* only inode numbers (447 entries) and 13 staging mtimes differ;
* same boot header fields, kernel, DTB, recovery DTBO and AVB vbmeta blob;
* same 64 MiB partition size and footer layout.

Packing the **preserved** staging tree from the published build (not
published because it contains extracted OEM files) reproduces the published
compressed ramdisk exactly:
`a572d0fa3c6a168f7de1633a62031b2e33e121b9a986c6a36af7964a53201581`.
From that ramdisk the published image is reproduced bit-for-bit.

Therefore the authoritative hashes are the ones in
[`SHA256SUMS`](../SHA256SUMS) and the tables above. Treat a hash mismatch on
a fresh rebuild as expected metadata variation, and compare the extracted
ramdisk contents instead. If you need stable hashes for your own builds,
keep one staging tree and repack it, or normalize mtimes and inode numbers
with a custom `newc` writer.
