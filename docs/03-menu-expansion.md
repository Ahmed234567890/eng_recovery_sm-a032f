# 03 — Expanding the recovery menu (libui hooks)

## Target

Add five entries to the stock 13-entry recovery menu without touching the
stock entries and without rebuilding `librecovery_ui.so`. The new entries
must dispatch to new action numbers 20–24.

## `librecovery_ui.so` layout

ELF32 little-endian shared object, 238,860 bytes (pristine), loaded at a
randomized base. Program headers:

| # | Type | Offset | VirtAddr | FileSiz | MemSiz | Flags | Align |
|---:|---|---:|---:|---:|---:|---|---:|
| 0 | PHDR | 0x000034 | 0x00000034 | 0x00140 | 0x00140 | R | 0x4 |
| 1 | LOAD | 0x000000 | 0x00000000 | 0x130f8 | 0x130f8 | R | 0x1000 |
| 2 | LOAD | 0x013100 | 0x00014100 | 0x236a0 | 0x236a0 | R E | 0x1000 |
| 3 | LOAD | 0x0367a0 | 0x000387a0 | 0x012a0 | 0x012a0 | RW | 0x1000 |
| 4 | LOAD | 0x037a40 | 0x0003aa40 | 0x00008 | 0x00c28 | RW | 0x1000 |
| 5 | DYNAMIC | 0x0371cc | 0x000391cc | 0x00108 | 0x00108 | RW | 0x4 |
| 6 | GNU_RELRO | 0x0367a0 | 0x000387a0 | 0x012a0 | 0x01860 | R | 0x1 |
| 7 | GNU_STACK | 0 | 0 | 0 | 0 | RW | 0 |
| 8 | **NOTE** | **0x000174** | **0x00000174** | **0x00038** | **0x00038** | **R** | **0x4** |
| 9 | ARM_EXIDX | 0x00ee28 | 0x0000ee28 | 0x01290 | 0x01290 | R | 0x4 |

Two things matter:

* the labels vector object lives in the BSS of LOAD #4 at virtual address
  **`0x3aa54`**, and the `menu_items` vector object at **`0x3aa48`**;
* the file ends at 238,860 (`0x3a50c`), so the page at **`0x3c000`** is free
  space that can be appended and mapped by a new `PT_LOAD`.

`PT_NOTE` (#8) is not used by the dynamic loader. Replacing that program
header with an executable `PT_LOAD` adds a new segment without growing the
program-header table.

## The two accessors

### `Device::GetMenuItems()` — VA `0x143e8`

```
143e8: 4801   ldr  r0, [pc, #4]     @ literal at 0x143f0
143ea: 4478   add  r0, pc           @ r0 = &labels vector object (0x3aa54)
143ec: 4770   bx   lr
143ee: 00bf   nop
```

It returns a pointer to the 12-byte `std::vector<std::string>` object at
`0x3aa54`. The vector's heap buffer holds 13 × 12-byte libc++ strings
(156 bytes, capacity 192).

### `Device::InvokeMenuItem(unsigned)` — VA `0x143f4`

```
143f4: 4803        ldr  r0, [pc, #0xc]   @ literal at 0x14404
143f6: 4478        add  r0, pc           @ &menu_items vector object (0x3aa48)
143f8: 6800        ldr  r0, [r0]          @ begin pointer
143fa: eb00 1001   add.w r0, r0, r1, lsl #4
143fe: 68c0        ldr  r0, [r0, #0xc]    @ action field
14400: 4770        bx   lr
```

`menu_items` entries are **16 bytes**: a 12-byte `std::string` label followed
by a 4-byte action number at `+0xc`. The stock table has 13 entries
(208 bytes).

## Why not just append to the vectors?

Appending two more 16-byte entries to `menu_items` in place is not possible:
its capacity is exactly 208 bytes and the buffer is heap-allocated. More
importantly, the menu labels and the dispatch table are separate objects, and
`InvokeMenuItem` is called with an index that the menu derives from the
labels vector. The clean approach is to intercept both accessors:

1. `GetMenuItems()` returns an expanded label vector (18 entries).
2. `InvokeMenuItem(index)` returns the stock action for `index < 13`, and
   `index + 7` for `index 13..17` (13→20 … 17→24).

`menu_items` is therefore never modified; only the dispatcher is extended.
This keeps the stock 13 actions byte-for-byte identical.

## Hook placement: replace `PT_NOTE`

The new code is appended at virtual address/file offset **`0x3c000`**, and
program header #8 is rewritten:

| Field | Before (`PT_NOTE`) | After (`PT_LOAD`) |
|---|---|---|
| `p_type` | 4 | **1** |
| `p_offset` | 0x000174 | **0x03C000** |
| `p_vaddr` | 0x000174 | **0x03C000** |
| `p_paddr` | 0x000174 | **0x03C000** |
| `p_filesz` | 0x000038 | **0x001000** |
| `p_memsz` | 0x000038 | **0x001000** |
| `p_flags` | 4 (R) | **5 (R+X)** |
| `p_align` | 0x4 | **0x1000** |

The file is extended to `0x3D000` (249,856 bytes) with the hook blob at
`0x3C000`. The original note sections remain in the file; only the program
header entry is repurposed.

## Base-relative addressing (the critical detail)

`librecovery_ui.so` is a shared object; its runtime base is randomized by
ASLR. Every absolute address in the hook would need a relocation, and adding
dynamic relocations to a signed/loaded library is fragile. The hook therefore
computes everything from its own PC:

* `.Lget_base` is at `0x3c000`. The labels vector is
  `0x3c000 - 0x15ac = 0x3aa54`.
* The `operator new` PLT stub `_Znwj@plt` is
  `0x3c000 - 0x6190 = 0x35e70`.
* `.Linv_base` is at `0x3c100`. `menu_items` is
  `0x3c100 - 0x16b8 = 0x3aa48`.

Each sequence is:

```asm
adr r3, .Lget_base     @ r3 = PC-relative address of this instruction
movw r2, #0x15ac       @ constant delta
sub  r0, r3, r2        @ r0 = &labels (no relocation)
```

`adr` to a **local label** is resolved at assembly time with no relocation.
Using a global symbol here produces `R_ARM_THM_ALU_PREL_11_0` relocations,
which the final binary cannot resolve. This was one of the early build
failures (see [10-pitfalls.md](10-pitfalls.md)).

## Hook blob

Size: 288 bytes (`0x120`). Layout:

| Address | Content |
|---:|---|
| `0x3c000` | `hook_get` |
| `0x3c060` | five 12-byte SSO labels |
| `0x3c100` | `hook_invoke` |

### `hook_get` (0x3c000)

```
r0 = &labels vector
if (end - begin != 156) return r0;      @ already expanded or unexpected
new = operator new(216);
copy 156 bytes from old buffer;
append 5 x 12-byte SSO strings;
labels.begin = new;
labels.end   = new + 216;
labels.cap   = new + 216;
return &labels;
```

The `!= 156` guard makes the hook **idempotent**: `GetMenuItems()` may be
called more than once, and the second call must not append another five
entries. The comparison is against the original byte length, not the entry
count, because libc++ strings are 12 bytes on 32-bit ARM.

Register discipline: `hook_get` saves `r4-r8` and `lr`, uses `r4` for the
vector pointer, `r5` for the old buffer, `r7`/`r8` for the new buffer and
cursor, and returns `r0 = &labels` to the caller. All callee-saved registers
are restored; the `push`/`pop` pair is balanced.

### The five labels and the SSO limit

libc++'s 32-bit `std::string` uses **short-string optimisation** with a
maximum of **10 characters** (the first byte stores `length << 1`, leaving
11 bytes for characters including the terminator). A label longer than 10
characters would need a heap allocation and a different string layout; the
hook cannot create those safely. All five labels are therefore ≤ 10 bytes:

| Index | Label | Length | First byte |
|---:|---|---:|---:|
| 13 | `Mount all` | 9 | `0x12` |
| 14 | `Unmount` | 7 | `0x0e` |
| 15 | `Part info` | 9 | `0x12` |
| 16 | `Save logs` | 9 | `0x12` |
| 17 | `Reboot rec` | 10 | `0x14` |

Each entry is 12 bytes: `[len<<1][chars...][zero padding]`. Examples:

```
Mount all : 12 4d 6f 75 6e 74 20 61 6c 6c 00 00
Unmount   : 0e 55 6e 6d 6f 75 6e 74 00 00 00 00
Reboot rec: 14 52 65 62 6f 6f 74 20 72 65 63 00
```

### `hook_invoke` (0x3c100)

```
if (index < 13) {
    entry = menu_items.begin + index * 16;
    return *(u32 *)(entry + 0xc);
}
return index + 7;      @ 13 -> 20, 14 -> 21, 15 -> 22, 16 -> 23, 17 -> 24
```

No range check for `index > 17` is added: the menu only passes indexes that
exist in the returned label vector, which now has 18 entries.

## Entry-point patches

| Function | VA | File offset | Original bytes | Patched bytes | Meaning |
|---|---:|---:|---|---|---|
| `GetMenuItems` | `0x143e8` | `0x133e8` | `01 48 78 44` | `27 f0 0a be` | `b.w 0x3c000` |
| `InvokeMenuItem` | `0x143f4` | `0x133f4` | `03 48 78 44` | `27 f0 84 be` | `b.w 0x3c100` |

Both fit in the original 4-byte instruction slots; the following bytes are
untouched (`7047 00bf` after GetMenuItems, `0068 00eb` after
InvokeMenuItem). The `b.w` range is ±16 MiB, far more than the 0x27c14 /
0x27d08 displacement used here.

## Runtime proof

With libui loaded at base `0xece82000`, the `menu_items` vector object is at
`0xecebca48` and the labels vector object is at `0xecebca54`. A 24-byte dump
starting at `0xecebca48` shows both (labels are the last three words):

```
begin = 0xed449380
end   = 0xed449458
end - begin = 0xD8 = 216 bytes = 18 entries
```

Decoding the 216 bytes gives the 13 stock labels followed by:

```
13: SHORT len=9  b'Mount all'
14: SHORT len=7  b'Unmount'
15: SHORT len=9  b'Part info'
16: SHORT len=9  b'Save logs'
17: SHORT len=10 b'Reboot rec'
```

The `menu_items` vector remains at 13 × 16 bytes. Pressing Volume Down 13
times and Power executed action 20 and the backend log shows
`action=20 started/finished`. See [07-verification.md](07-verification.md).

## First failed attempt (why the segment matters)

The first build linked the hook at **`0x14d54`**, which is inside the live
`.text` of libui, and patched the accessors to branch there. Recovery died
with `signal 11` immediately. The hook overwrote real instructions and
corrupted the `Device` constructor / menu path. The fixed design uses a
dedicated appended segment (`0x3c000`) and leaves all existing code intact.
The bad artifacts are recorded in [01-device-and-baseline.md](01-device-and-baseline.md)
for reference.
