# 04 — New recovery actions (recovery binary handler)

## Target

The stock recovery menu dispatches actions by calling
`Device::InvokeMenuItem(index)`, then switching on the returned action
number. We need actions **20–24** to run five new operations. The stock
action switch has no cases for them; they fall into the `default:` branch.
The cleanest binary-only approach is to redirect that default branch to new
code that performs the work and then rejoins the original function epilogue.

## The stock switch

From the pristine recovery binary:

```
1728e: 9824          ldr   r0, [sp, #0x90]
17290: 6801          ldr   r1, [r0]
17292: 6a8a          ldr   r2, [r1, #0x28]
17294: 4631          mov   r1, r6
17296: 4790          blx   r2              @ InvokeMenuItem(index)
17298: 4605          mov   r5, r0          @ <-- action number lives in r5
1729a: 3801          subs  r0, #0x1
1729c: 2812          cmp   r0, #0x12
1729e: f200 8564     bhi.w 0x17d6a        @ out of range -> epilogue
172a2: f04f 0a01     mov.w r10, #0x1
172a6: e8df f010     tbh   [pc, r0, lsl #1]  @ 19-entry action jump table
```

Consequences:

* the valid switch range is **action 1 … 19** (`action - 1 <= 0x12`);
* actions **20 … 24** take the `bhi.w` to **`0x17d6a`**, the shared epilogue
  path;
* at that branch the action number is still in **`r5`**.

`0x17d6a` is *not* a function entry. It is inside the original function's
epilogue, expecting the original stack frame and saved registers:

```
17d6a: 9d10          ldr   r5, [sp, #0x40]
17d6c: f04f 0a00     mov.w r10, #0x0
17d70: 9f20          ldr   r7, [sp, #0x80]
...
```

The handler must therefore restore the register state it inherited and
**branch** to `0x17d6a`, not `pop {…, pc}`. Returning directly to the caller
would skip this epilogue and unbalance the stack.

## Handler design

New code at **VA/file `0x4e200`**, in a new executable segment. Behaviour:

```
action = r5;
if (action < 20 || action > 24) goto done;
pid = fork();
if (pid < 0) goto done;
if (pid == 0) {
    argv = { "/system/bin/sh",
             "/system/bin/recovery-tools",
             "2X" (action number as decimal),
             NULL };
    execv("/system/bin/sh", argv);
    exit(127);
}
waitpid(pid, NULL, 0);
done:
restore r4-r12, lr;
sp += 64;
b.w 0x17d6a;
```

The action string is built without `sprintf`:

```asm
sub  r1, r4, #20          @ 0..4
add  r1, r1, #0x30        @ '0'..'4'
mov  r2, #0x32            @ '2'
strb r2, [sp, #16]        @ "2"
strb r1, [sp, #17]        @ "0".."4"
strb r2, [sp, #18]        @ NUL  (r2 was zeroed just before)
```

so action 20 becomes `"20"` and action 24 becomes `"24"`. This avoids any
libc formatting dependency.

### Why fork/exec instead of doing the work in-process

The work is implemented as a shell script (`/system/bin/recovery-tools`) that
needs `mount`, `grep`, `date`, `lpmap`, &c. Running it in a child:

* keeps the recovery process's memory and file descriptors clean;
* lets the menu wait for completion with `waitpid`, preserving the expected
  "action finished, redraw menu" behaviour;
* isolates failures: a script crash cannot take recovery down;
* is simple to implement in position-independent Thumb-2.

The child calls `exit(127)` if `execv` fails, so a missing `/system/bin/sh`
or backend script still reaps cleanly.

### Register and stack discipline

The handler is entered at the branch target with the original function's
frame still live. It does:

```
push.w {r4-r12, lr}
sub    sp, #64
...
add    sp, #64
pop.w  {r4-r12, lr}
b.w    0x17d6a
```

This exactly undoes the handler's own frame. The sum of pushes/pops is zero,
so the original function's stack pointer is restored before the original
epilogue runs. `r4-r11` are callee-saved and are restored; `r12` is
caller-saved but is saved anyway for symmetry; `lr` is restored because the
epilogue path eventually returns through the original saved `lr`.

The handler never returns to the switch: it always branches to `0x17d6a`,
even for an unexpected action number. That preserves the original default
behaviour exactly.

## Code placement: replace `PT_NOTE` in `recovery`

The recovery ELF has 12 program headers. `PT_NOTE` is header **index 10**.
The last existing `PT_LOAD` ends at virtual address `0x4b9dc`, so `0x4e000`
is free. Header #10 is rewritten:

| Field | Before (`PT_NOTE`) | After (`PT_LOAD`) |
|---|---|---|
| `p_type` | 4 | **1** |
| `p_offset` | `0x0001b8` | **`0x04E000`** |
| `p_vaddr` | `0x000001b8` | **`0x04E000`** |
| `p_paddr` | `0x000001b8` | **`0x04E000`** |
| `p_filesz` | `0x00024` | **`0x001000`** |
| `p_memsz` | `0x00024` | **`0x001000`** |
| `p_flags` | 4 (R) | **5 (R+X)** |
| `p_align` | 0x4 | **0x1000** |

The file is extended to `0x4F000` (323,584 bytes) and the 155-byte handler is
written at `0x4E200`.

## Branch patch

| | VA | File offset | Bytes | Instruction |
|---|---:|---:|---|---|
| Original | `0x1729e` | `0x1629e` | `00 f2 64 85` | `bhi.w 0x17d6a` |
| Patched | `0x1729e` | `0x1629e` | `36 f2 af 87` | `bhi.w 0x4e200` |

The condition code is unchanged (`bhi`, unsigned higher), so actions 1–19
still use the stock jump table. Action 0 (if it ever occurred) also reaches
the handler; the range check ignores it and the tail jump performs the
original default behaviour.

## Handler blob layout

155 bytes at `0x4E200`:

| Address | Content |
|---:|---|
| `0x4E200` | entry: push, stack allocation, action range check |
| `0x4E210` | `fork` / `waitpid` / child path |
| `0x4E270` | `"/system/bin/sh"` |
| `0x4E280` | `"/system/bin/recovery-tools"` |
| `0x4E29B` | end of blob |

The blob contains no absolute data addresses. The PLT calls
(`fork@0x465d0`, `waitpid@0x46d50`, `execv@0x46d70`, `exit@0x468b0`) and the
tail branch are all PC-relative `blx`/`b.w` instructions resolved at link
time against the existing binary. No dynamic relocations are added.

## Runtime proof

Selecting the fifth new entry (`Reboot rec`, index 17) reboots the device.
Selecting `Mount all` (index 13) produces:

```
[recovery-tools] action=20 started
...
[recovery-tools] action=20 finished
```

and the device remains stable. All five actions were exercised end-to-end;
see [07-verification.md](07-verification.md).

## Why the first attempt crashed

The first handler build was correct, but the companion libui hook was placed
at live code `0x14d54`; recovery died with `signal 11` before the menu could
even be drawn. The handler design itself was retained. The final libui hook
uses a separate segment (`0x3c000`), which removed the crash.
