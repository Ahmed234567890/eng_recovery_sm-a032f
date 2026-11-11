#!/usr/bin/env python3
"""Build the Phase 1 patched recovery binary and librecovery_ui.so.

Inputs (see build/README.md):
  --recovery-base  known-good `recovery` executable (signature bypass only)
  --libui-base     pristine librecovery_ui.so
  --handler        handler.bin (155-byte Thumb-2 blob)
  --hook           ui_hook2.bin (288-byte Thumb-2 blob)

Outputs:
  <outdir>/recovery_patched
  <outdir>/librecovery_ui_patched.so

Changes:
  recovery:
    - redirect the InvokeMenuItem default case (file 0x1629e) to the
      added action handler at VA 0x4e200
    - replace PT_NOTE program header #10 with an R+X PT_LOAD at 0x4e000
    - append the handler blob at 0x4e200
  libui:
    - branch GetMenuItems (file 0x133e8) to hook_get  (VA 0x3c000)
    - branch InvokeMenuItem (file 0x133f4) to hook_invoke (VA 0x3c100)
    - replace PT_NOTE program header #8 with an R+X PT_LOAD at 0x3c000
    - append the hook blob at 0x3c000
"""

import argparse
import struct
import sys
from pathlib import Path

PHDR_FMT = "<IIIIIIII"  # ELF32: type, offset, vaddr, paddr, filesz, memsz, flags, align
PT_LOAD = 1
PT_NOTE = 4


def read_phdrs(data):
    e_phoff = struct.unpack_from("<I", data, 0x1C)[0]
    e_phentsize = struct.unpack_from("<H", data, 0x2A)[0]
    e_phnum = struct.unpack_from("<H", data, 0x2C)[0]
    assert e_phentsize == 32, f"unexpected e_phentsize {e_phentsize}"
    phdrs = []
    for i in range(e_phnum):
        off = e_phoff + i * e_phentsize
        phdrs.append(struct.unpack_from(PHDR_FMT, data, off))
    return e_phoff, e_phentsize, phdrs


def find_note(phdrs):
    notes = [i for i, p in enumerate(phdrs) if p[0] == PT_NOTE]
    assert len(notes) == 1, f"expected one PT_NOTE, found {notes}"
    return notes[0]


def patch_recovery(base, handler, out):
    data = bytearray(base.read_bytes())
    blob = handler.read_bytes()
    assert len(blob) <= 0x1000, "handler too large"

    e_phoff, entsize, phdrs = read_phdrs(data)
    note_idx = find_note(phdrs)
    print(f"recovery: PT_NOTE phdr index {note_idx}")

    # default case -> handler (bhi.w 0x4e200; assembled from pristine 0x1629e)
    branch = bytes.fromhex("36f2af87")
    off = 0x1629E
    old = bytes(data[off:off + 4])
    assert old == bytes.fromhex("00f26485"), f"unexpected default branch bytes {old.hex()}"
    data[off:off + 4] = branch

    # PT_NOTE -> R+X PT_LOAD at 0x4e000
    off = e_phoff + note_idx * entsize
    struct.pack_into(PHDR_FMT, data, off, PT_LOAD, 0x4E000, 0x4E000, 0x4E000,
                     0x1000, 0x1000, 5, 0x1000)

    if len(data) < 0x4F000:
        data.extend(b"\0" * (0x4F000 - len(data)))
    data[0x4E200:0x4E200 + len(blob)] = blob

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"recovery: wrote {out} ({len(data)} bytes, handler {len(blob)} bytes)")


def patch_libui(base, hook, out):
    data = bytearray(base.read_bytes())
    blob = hook.read_bytes()
    assert len(blob) <= 0x1000, "hook blob too large"

    e_phoff, entsize, phdrs = read_phdrs(data)
    note_idx = find_note(phdrs)
    print(f"libui: PT_NOTE phdr index {note_idx}")

    # GetMenuItems -> hook_get, InvokeMenuItem -> hook_invoke
    get_off, get_new = 0x133E8, bytes.fromhex("27f00abe")
    inv_off, inv_new = 0x133F4, bytes.fromhex("27f084be")
    assert bytes(data[get_off:get_off + 4]) == bytes.fromhex("01487844")
    assert bytes(data[inv_off:inv_off + 4]) == bytes.fromhex("03487844")
    data[get_off:get_off + 4] = get_new
    data[inv_off:inv_off + 4] = inv_new

    # PT_NOTE -> R+X PT_LOAD at 0x3c000
    off = e_phoff + note_idx * entsize
    struct.pack_into(PHDR_FMT, data, off, PT_LOAD, 0x3C000, 0x3C000, 0x3C000,
                     0x1000, 0x1000, 5, 0x1000)

    if len(data) < 0x3D000:
        data.extend(b"\0" * (0x3D000 - len(data)))
    data[0x3C000:0x3C000 + len(blob)] = blob

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print(f"libui: wrote {out} ({len(data)} bytes, hook {len(blob)} bytes)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recovery-base", required=True, type=Path,
                    help="known-good recovery binary (signature bypass only)")
    ap.add_argument("--libui-base", required=True, type=Path,
                    help="pristine librecovery_ui.so")
    ap.add_argument("--handler", type=Path,
                    default=Path(__file__).with_name("handler.bin"))
    ap.add_argument("--hook", type=Path,
                    default=Path(__file__).with_name("ui_hook2.bin"))
    ap.add_argument("--outdir", type=Path,
                    default=Path(__file__).resolve().parent.parent / "binaries")
    args = ap.parse_args()

    for p in (args.recovery_base, args.libui_base, args.handler, args.hook):
        if not p.exists():
            sys.exit(f"missing input: {p}")

    patch_recovery(args.recovery_base, args.handler, args.outdir / "recovery_patched")
    patch_libui(args.libui_base, args.hook, args.outdir / "librecovery_ui_patched.so")
    print("done")


if __name__ == "__main__":
    main()
