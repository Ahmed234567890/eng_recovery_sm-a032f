# Documentation map

This directory records the complete Phase 1 engineering work: how the stock
recovery was analysed, exactly which bytes were changed, how the image was
packaged, how it was verified, and what is planned for Phase 2.

Read in order:

| # | Document | Contents |
|---:|---|---|
| 01 | [device-and-baseline.md](01-device-and-baseline.md) | Device, firmware, partition table, original recovery image layout, baseline hashes |
| 02 | [signature-bypass.md](02-signature-bypass.md) | Locating and patching the OTA signature check with four bytes |
| 03 | [menu-expansion.md](03-menu-expansion.md) | `librecovery_ui.so` internals, libc++ vector layout, PT_NOTE → PT_LOAD hook, five new labels |
| 04 | [action-handler.md](04-action-handler.md) | `recovery` binary default-case hook, register/stack discipline, fork/exec, tail jump |
| 05 | [recovery-tools.md](05-recovery-tools.md) | The `/system/bin/recovery-tools` backend and what each action does |
| 06 | [image-build.md](06-image-build.md) | Ramdisk packing, `mkbootimg` parameters, AVB wrapper, exact commands |
| 07 | [verification.md](07-verification.md) | Hardware verification transcript: boot, menu, all five actions, unsigned sideload |
| 08 | [usage-and-rollback.md](08-usage-and-rollback.md) | Day-to-day use, log locations, shell access, rollback |
| 09 | [phase2-plan.md](09-phase2-plan.md) | Planned super enlargement and MindTheGapps installation (not executed) |
| 10 | [pitfalls.md](10-pitfalls.md) | Every trap hit during the work and how it was solved |

## Terminology

* **Stock recovery** — the Android 11 engineering recovery extracted from the
  device (`recovery.img`, 64 MiB partition image).
* **Known-good binary** — the stock `recovery` executable with only the
  four-byte signature bypass. It was flashed and verified before any menu
  work; hash `7f59a0cd…`.
* **Phase 1** — signature bypass + five menu entries + shell tools + fixed
  image. This is what the current repository contains.
* **Phase 2** — enlarge the `super` partition, add a `product` partition and
  install MindTheGapps. Not started.

## One-paragraph summary

The stock recovery verifies OTA packages before installing them. A single
stripped function at virtual address `0x23908` returns the verification
result; replacing its first four bytes with `movs r0,#0; bx lr` makes it
return success. The recovery menu is built by `Device::GetMenuItems()` and
dispatched by `Device::InvokeMenuItem()` in `librecovery_ui.so`. Both
functions were redirected to a new code page appended to the library: the
getter expands the 13-entry label vector to 18 entries, and the dispatcher
maps indexes 13–17 to actions 20–24. The recovery binary's action switch was
redirected so actions 20–24 reach a new handler that `fork/exec`s
`/system/bin/sh /system/bin/recovery-tools <action>` and then rejoins the
original function epilogue. The ramdisk carries the patched binaries plus
static `bash`, `busybox`, `lpmap` and the backend script. The 64 MiB image
keeps the original kernel, DTB, recovery DTBO and OEM-signed `vbmeta` blob;
only the AVB footer is regenerated. All features were verified on the SM-A032F.
