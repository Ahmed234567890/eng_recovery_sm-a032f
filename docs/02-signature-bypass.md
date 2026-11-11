# 02 — Unsigned sideload: the four-byte signature bypass

## Goal

The stock Android 11 recovery verifies the signature of every OTA package
before running `update-binary`. On an unlocked engineering device the goal is
to accept **both signed and unsigned** packages, without rebuilding recovery
and without disabling the rest of the verification machinery.

## How it was found

Two `recovery` binaries were compared:

* the pristine executable extracted from the engineering image
  (`7780f3b1…`, 314,380 bytes), and
* the known-good executable from the rollback image (`7f59a0cd…`, same size),
  which had already been observed to accept an unsigned package.

A byte-by-byte diff showed **exactly one changed site**:

```
$ cmp -l pristine_recovery known_good_recovery
141577   0  55
141578  40 351
141579 160 360
141580 107 117
```

File offsets 141,577–141,580 are `0x22908`–`0x2290B` (1-based `cmp`
offsets; the zero-based range starts at `0x22908`). In a 32-bit ARM ELF with
the executable `PT_LOAD` at file offset `0x12360` / virtual address
`0x13360`, this maps to:

```
virtual address = 0x22908 + 0x1000 = 0x23908
```

## The patch

| | Bytes at file `0x22908` (VA `0x23908`) | Instruction |
|---|---|---|
| Pristine | `2d e9 f0 4f` | `push.w {r4-r11, lr}` |
| Known-good | `00 20 70 47` | `movs r0, #0` ; `bx lr` |

The first four bytes of the function are replaced by an immediate return of
zero. In the ARM AAPCS calling convention the return value is in `r0`, so
every caller sees **0**. Recovery's package verification path interprets `0`
as success — the same value the real verification routine returns for a
validly signed package.

Nothing else is changed: the rest of the function body, the signature parser,
the error strings and the AB/update logic remain intact. Because the return
is taken before the prologue, the function no longer creates a stack frame;
callers only consume `r0`, so there is no stack imbalance.

## Why this is sufficient

The recovery update path calls this verification function once per package
and branches on its return value. A zero return short-circuits the
"failed to verify whole-file signature" path. The actual installation still
goes through the normal `update-binary` execution, so package scripts behave
exactly as they do for a signed package.

The verification result is reported in the recovery log:

```
Update package verification took 0.0 s (result 0).
```

A `result 0` means "verified"; the elapsed time is zero because the check was
bypassed.

## Is the patched function `verify_file`?

The binary is stripped of a full symbol table; the nearest exported dynamic
symbol belongs to an unrelated `std::__tree` helper. The function is
identified by behaviour and by the strings used in its callers:

```
failed to verify whole-file signature
Failed to verify package
Verifying update package...
whole-file signature verified against RSA key
whole-file signature verified against EC key
Signature verification failed
```

The exact source-level name is not needed for the patch. The function entry
address (`0x23908`) and the four replacement bytes are all that matter.

## Deterministic application

`build/patch_phase1.py` starts from the known-good binary (which already
contains this patch) and asserts the patched bytes before adding the Phase 1
handler. The signature bypass is therefore inherited exactly, never
re-derived:

```
$ xxd -s 0x22908 -l 16 binaries/recovery_patched
00022908: 0020 7047 03af 81b0 2ded 088b deb0 0446  . pG....-......F
```

The first four bytes are `00 20 70 47` — the bypass is present in the
published Phase 1 binary.
