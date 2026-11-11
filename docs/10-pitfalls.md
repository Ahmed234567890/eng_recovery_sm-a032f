# 10 — Pitfalls and solutions

Every item below was hit during the work. They are recorded so a future
rebuild does not repeat them.

## Build environment

### `/tmp` quota

Writing sort lists or cpio archives under `/tmp` failed with:

```
sort: write failed: 'standard output': Disk quota exceeded
```

Solution: keep every temporary under the project directory:

```bash
export TMPDIR="$HOME/a032f-work/tmp"
mkdir -p "$TMPDIR"
```

### GNU `ld` cannot link ARM objects

`ld` on the host is x86-only:

```
/usr/bin/ld: branch_get3.o: relocations in generic ELF (EM: 40)
/usr/bin/ld: error adding symbols: file in wrong format
```

Solution: use `zig cc -target thumb-linux-androideabi -nostdlib` (bundled
LLD) or `clang --target=thumbv7-linux-androideabi` plus a Thumb-capable
linker. The published handler was linked with:

```
zig cc -target thumb-linux-androideabi -nostdlib -Wl,-T,handler.ld \
       -o handler.elf handler.o
```

### `adr` to a global symbol creates a relocation

Assembling `adr r3, hook_get` produced
`R_ARM_THM_ALU_PREL_11_0` relocations and encoded `PC-4`. The final binary
cannot resolve them without a linker.

Solution: use a **local** label at the instruction address:

```asm
.Lget_base:
    adr r3, .Lget_base
```

The assembler resolves it immediately and emits no relocation. Verify with
`llvm-objdump -r ui_hook2.o` — the relocation table must be empty.

### Byte order in assertions

Thumb halfwords are little-endian in the file. The libui instruction
`ldr r0, [pc, #4]` is `01 48` in memory, not `48 01`. An early assertion
written as `48 01 44 78` failed even though the patch bytes were correct.

Solution: assert the raw file bytes (`01 48 78 44`) or verify with
`llvm-objdump -d` on the file.

### `objdump` starting mid-instruction

`--start-address` can begin in the middle of a Thumb instruction, producing
nonsense. Also, symbol values in the symbol table may have the Thumb bit set
(`0x14409` means code at `0x14408`).

Solution: mask the low bit for Thumb symbols and start disassembly at a
known instruction boundary.

## Menu hook

### Overwriting live code crashes recovery

The first libui hook was linked at **`0x14d54`**, inside real `.text`. It
overwrote live instructions and recovery died immediately with `signal 11`
(boot loop). The address looked "free" statically but was not.

Solution: add a **new `PT_LOAD` segment** in file space that is beyond the
loadable data and replace an unused program header (`PT_NOTE`) with it. The
final hook is at `0x3c000` in libui and `0x4e200` in recovery. Existing code
is untouched.

### libc++ short strings are limited to 10 characters

On 32-bit ARM, `std::string` stores `length << 1` in byte 0 and at most 10
characters inline (11 bytes including the terminator). A longer label would
be laid out as a heap string and the hook's raw copy would not create a
valid object — the menu would free an invalid pointer or print garbage.

Solution: keep every appended label ≤ 10 bytes. The chosen labels are
`Mount all` (9), `Unmount` (7), `Part info` (9), `Save logs` (9),
`Reboot rec` (10).

### Expanding the vector more than once

`GetMenuItems()` is called repeatedly. Blindly appending five labels on each
call would grow the vector without bound and eventually exhaust memory.

Solution: the hook checks `end - begin` against the original **156 bytes**
and only expands when the size is exactly the stock value.

### Using absolute addresses

libui is a shared library; its load base is randomized. Absolute addresses
would need relocations that the appended segment does not have.

Solution: compute the labels vector and `_Znwj@plt` from the hook's own PC
with `adr` + `movw` subtraction.

## Action handler

### Returning with `pop {…, pc}` breaks the stack

The action switch's default branch jumps to `0x17d6a`, which is **inside the
original function's epilogue**, not a function entry. Returning directly to
the caller skips that epilogue and unbalances the stack.

Solution: the handler restores its own saved registers and executes
`b.w 0x17d6a`. It does not return through `lr`.

### Wrong source register for the action

The action number is in **`r5`** at the default branch (`mov r5, r0` at
`0x17298`), not in `r0`/`r1`. The handler uses `mov r4, r5` and range-checks
`20..24`.

### Handler/PLT addresses are relative

Calls to `fork`, `waitpid`, `execv` and `exit` must go to the existing PLT
stubs (`0x465d0`, `0x46d50`, `0x46d70`, `0x468b0`). They are PC-relative
`blx` instructions resolved at link time; no absolute calls or relocations
are added.

## Packaging

### `cpio` ownership

Extracting and repacking as a normal user produces `ahmed:ahmed` entries.
Init expects root-owned ramdisk files.

Solution: `cpio -o -H newc --owner 0:0`. Verify with `cpio -itv` that every
entry says `root root`.

### gzip determinism

`gzip` embeds a timestamp and the original file name by default, so two
builds differ. Use `gzip -9 -n -c` and generate the cpio from a fresh
staging tree.

### AVB footer field offsets

The footer format is `!4s2LQQQ28x` (64 bytes):

| Footer offset | Field |
|---:|---|
| 0 | magic `AVBf` |
| 4 | version major (1) |
| 8 | version minor (0) |
| 12 | original image size (big-endian u64) |
| 20 | vbmeta offset (big-endian u64) |
| 28 | vbmeta size (big-endian u64) |
| 36–63 | reserved |

The Q fields start at 12/20/28, **not** 16/24/32. Using the wrong offsets
silently reads garbage. `avbtool append_vbmeta_image` avoids manual footer
construction entirely and is the recommended path.

### AVB descriptor vs. new image

Reusing the OEM vbmeta blob keeps the original hash descriptor (original
image size and digest). The footer is valid, but the descriptor does not
match the new boot image. This is acceptable **only** because the device is
unlocked. Never relock the bootloader with this image installed.

## Flashing and testing

### fastbootd does not reboot the kernel

`fastboot reboot recovery` from the userspace fastboot daemon only exits the
daemon; uptime and dmesg continue, and the old ramdisk is still running. The
partition may already contain the new image, which is confusing.

Solution: verify the partition read-back hash, then issue a real reboot
(`adb reboot recovery` or a power cycle) before testing.

### Menu selection resets

After every action the selection returns to index 0. Sending a sequence that
assumes the previous position selects the wrong entry. This is how the first
verification accidentally chose `Enter fastboot` instead of the intended
entry.

Solution: always send exactly *N* Volume Down presses from index 0, then
Power.

### Interleaved log writers

`/tmp/recovery.log` is written by recovery, libfs_mgr and the backend script.
`tail` shows kernel/filesystem lines between `[recovery-tools]` lines.

Solution: filter with `grep '\[recovery-tools\]'` when checking action
results.

### Reading `/proc/<pid>/mem`

Busybox `dd` uses a 32-bit `skip`; a value like `0xec7ac` is fine but a
computed byte offset can overflow. A one-byte `bs=1 skip=<huge>` read
silently failed or read the wrong page.

Solution: use `bs=4096 skip=<page>` and then a second `dd bs=1 skip=<offset
within page>`, or dump the whole page over `adb exec-out` and slice it on the
host.

### Compute runtime addresses carefully

`libui base + VA` is not `base + 0x3aa54` if the base is misread: the first
attempt used `0xec402000 + 0x3aa54 = ec7aca54`, but the correct arithmetic is
`ec402000 + 0x3aa54 = ec43ca54`. Double-check with a known string address
before trusting a memory dump.
