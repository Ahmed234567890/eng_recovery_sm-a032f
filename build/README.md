# Build sources and workflow

This directory contains the exact sources and scripts used to produce the
Phase 1 artifacts. The OEM `recovery`, `librecovery_ui.so`, kernel, DTB,
recovery DTBO and `vbmeta` blob are **not** published here; extract them from
your own device dump. The patched outputs are published under
`../binaries/` and `../images/`.

## Contents

| File | Purpose | Size | SHA-256 |
|---|---|---:|---|
| `patch_phase1.py` | patch the two ELF files | 5,175 B | see `../SHA256SUMS` |
| `build_phase1_fixed.py` | stage the ramdisk, build boot image, wrap AVB | 6,545 B | see `../SHA256SUMS` |
| `handler.s` | Thumb-2 action handler source | 1,006 B | see `../SHA256SUMS` |
| `handler.ld` | handler link addresses | 173 B | see `../SHA256SUMS` |
| `handler.bin` | assembled handler blob | 155 B | `cf0e45374076dc6ce9c6af87b6ce21594298571c37fae676643064a25eb7669c` |
| `ui_hook2.s` | Thumb-2 libui hook source | 2,909 B | see `../SHA256SUMS` |
| `ui_hook2.bin` | assembled hook blob | 288 B | `771de1e731dcbfac06815bf93c5217359a40a97c8c597493623ae547b7d6e5bd` |

## Host requirements

* Python 3.8+
* `cpio` (GNU cpio, `newc` support) and `gzip`
* Android `mkbootimg` / `unpack_bootimg`
* `avbtool` (the `append_vbmeta_image` and `info_image` subcommands)
* `clang` with the ARM Thumb target, plus `llvm-objcopy`
* `zig` 0.17.x (only for linking `handler.bin`; `ld.lld` from LLVM also works)

## Step 0 — Extract inputs from your own image

```bash
mkdir -p dump dump/root
unpack_bootimg --boot_img /path/to/known-good-recovery.img --out dump
(cd dump/root && gzip -dc ../ramdisk | cpio -idm --quiet)

# original signed vbmeta blob (2,112 bytes)
avbtool extract_vbmeta_image --image /path/to/original-recovery.img \
       --output dump/vbmeta-original.bin
```

The build expects:

| Input | Path in the examples | Expected SHA-256 |
|---|---|---|
| Known-good `recovery` (signature bypass already applied) | `dump/root/system/bin/recovery` | `7f59a0cdda36e520a0c16f2087be7fe0e7883e15b766da39de80582bcc3b2055` |
| Pristine `librecovery_ui.so` | `dump/root/system/lib/librecovery_ui.so` | `f3e10ef33f248069c820f3357ce1427b86adcc99ee8f1cf905f551780e313d26` |
| Kernel | `dump/kernel` | `0b98b361b25accd86bdffda1883d1974caa3020bebac3fee19da989db0be69a3` |
| DTB | `dump/dtb` | `b34fd2f27a6d20a9eab8cdda664030518e60fcacdff1c8dfcfac3eeaef86837b` |
| Recovery DTBO | `dump/recovery_dtbo` | `13e34fc63ec21418db375013192189e8b91ff91ac0ea877aa905d9c426716ae3` |
| Original vbmeta blob | `dump/vbmeta-original.bin` | `3b558db5c34974145337af0f472cc12fdf38f4ff0fc80e706ce468c14d8da205` |

The known-good recovery binary must already contain the four-byte signature
bypass at file offset `0x22908` (`2d e9 f0 4f` → `00 20 70 47`), as described
in [`../docs/02-signature-bypass.md`](../docs/02-signature-bypass.md). The
patch script adds the menu-action handler on top; it does not re-apply the
signature bypass.

## Step 1 — Rebuild the two blobs (optional)

The published `handler.bin` and `ui_hook2.bin` are checked in, so this step is
only needed if you modify the assembly.

```bash
# libui hook: no relocations, assembled at section offset 0
clang --target=thumbv7a-linux-androideabi -c build/ui_hook2.s -o ui_hook2.o
llvm-objcopy -O binary --only-section=.text ui_hook2.o build/ui_hook2.bin

# action handler: linked at VA 0x4e200 with the original PLT/default targets
clang --target=thumbv7a-linux-androideabi -c build/handler.s -o handler.o
zig cc -target thumb-linux-androideabi -nostdlib \
        -Wl,-T,build/handler.ld -o handler.elf handler.o
llvm-objcopy -O binary --only-section=.text handler.elf build/handler.bin
```

`ld.lld` prints `warning: cannot find entry symbol _start`; the blob is a raw
code fragment, not an executable, so the warning is expected and harmless.

Verify:

```bash
sha256sum build/handler.bin build/ui_hook2.bin
# cf0e4537...  build/handler.bin
# 771de1e7...  build/ui_hook2.bin
llvm-objdump -r ui_hook2.o        # must print no relocation records
```

## Step 2 — Patch the ELF files

```bash
python3 build/patch_phase1.py \
    --recovery-base dump/root/system/bin/recovery \
    --libui-base    dump/root/system/lib/librecovery_ui.so \
    --handler       build/handler.bin \
    --hook          build/ui_hook2.bin \
    --outdir        binaries
```

The script asserts every original byte before writing, so a mismatched input
fails loudly. Output:

```
recovery: PT_NOTE phdr index 10
recovery: wrote binaries/recovery_patched (323584 bytes, handler 155 bytes)
libui: PT_NOTE phdr index 8
libui: wrote binaries/librecovery_ui_patched.so (249856 bytes, hook 288 bytes)
```

Expected hashes:

```
54009dd289d1898d2b940c4104fdad3743d55dc9b5936101f501f125116313fb  binaries/recovery_patched
75f03910470e8f1264db7c7abff4b5f3c7582813173d2bb26dd665415c90aead  binaries/librecovery_ui_patched.so
```

The patch is byte-exact and was verified with `cmp` against the published
binaries.

## Step 3 — Build the 64 MiB image

```bash
python3 build/build_phase1_fixed.py \
    --root          dump/root \
    --kernel        dump/kernel \
    --dtb           dump/dtb \
    --recovery-dtbo dump/recovery_dtbo \
    --vbmeta        dump/vbmeta-original.bin \
    --recovery      binaries/recovery_patched \
    --libui         binaries/librecovery_ui_patched.so \
    --tools         tools \
    --out           images/recovery_phase1_fixed.img \
    --work          work
```

Defaults: `--recovery`, `--libui` and `--tools` point into the repository;
`--work` defaults to `./work`; `--partition-size` defaults to `67108864`.

The script:

1. copies `--root` to `<work>/fixed-root`;
2. overlays the patched binaries and the four tools, and creates six busybox
   symlinks (`ash`, `awk`, `bb`, `unzip`, `vi`, `wget`);
3. packs a `newc` cpio with `--owner 0:0`, then `gzip -9 -n`;
4. builds an Android boot image v2 with the original header parameters;
5. wraps it with the original signed vbmeta blob using
   `avbtool append_vbmeta_image --partition_size 67108864`.

Expected artifact sizes:

```
binaries/recovery_patched            323,584 B
binaries/librecovery_ui_patched.so   249,856 B
work/fixed-ramdisk.gz              9,863,349 B   (published build)
work/fixed-boot.img               33,099,776 B
images/recovery_phase1_fixed.img  67,108,864 B
```

## Reproducibility caveat

`patch_phase1.py` is byte-reproducible. The image build is
**content-reproducible** but not byte-reproducible from a fresh `--work`
directory: the `newc` cpio format stores host inode numbers and file mtimes,
and those differ between staging trees.

A fresh rebuild was compared with the published image:

* 448 cpio entries, same order;
* 0 differences in payload bytes, sizes, modes or symlinks;
* only 447 inode numbers and 13 staging mtimes differ;
* identical kernel, DTB, recovery DTBO, vbmeta blob and boot header fields.

Packing the preserved original staging tree reproduces the published ramdisk
exactly (`a572d0fa3c6a168f7de1633a62031b2e33e121b9a986c6a36af7964a53201581`),
and from it the published image bit-for-bit. The authoritative hashes are in
[`../SHA256SUMS`](../SHA256SUMS); compare extracted contents rather than the
whole-image hash when rebuilding from scratch.

## Flashing

```bash
fastboot flash recovery images/recovery_phase1_fixed.img
adb reboot recovery      # required after flashing from fastbootd
```

See [`../docs/08-usage-and-rollback.md`](../docs/08-usage-and-rollback.md).
