.syntax unified
.arch armv7-a
.thumb
.section .text
.global hook_get
.global hook_invoke

@ ---------------------------------------------------------------------------
@ libui is a shared library loaded at a randomized base, so every address must
@ be computed relative to the current PC.  hook_get lives at link-time VA
@ 0x3c000; the Device labels vector is at 0x3aa54 (delta 0x15ac) and the
@ operator new PLT stub is at 0x35e70 (delta 0x6190).
@
@ GetMenuItems() normally returns a reference to the 13-entry labels vector
@ (13 * 12 bytes = 156).  On the first call we replace it with a freshly
@ allocated 18-entry vector (216 bytes): the original 13 labels are copied
@ verbatim and five short libc++ SSO labels are appended.
@ ---------------------------------------------------------------------------
.thumb_func
hook_get:
.Lget_base:
    adr r3, .Lget_base
    movw r2, #0x15ac
    sub r0, r3, r2              @ r0 = &labels (0x3aa54)
    ldr r1, [r0]
    ldr r2, [r0, #4]
    subs r2, r2, r1
    cmp r2, #156
    bne .Lget_ret               @ already expanded (or unexpected) - leave alone

    push {r4, r5, r6, r7, r8, lr}
    mov r4, r0
    ldr r5, [r4]                @ old begin

    movs r0, #216
    adr r3, .Lget_base
    movw r2, #0x6190
    sub r2, r3, r2              @ _Znwj@plt
    blx r2

    mov r7, r0                  @ new begin
    mov r8, r0                  @ cursor

    movs r3, #156
.Lcopy:
    ldrb r2, [r5], #1
    strb r2, [r8], #1
    subs r3, r3, #1
    bne .Lcopy

    adr r1, .Llabels
    movs r2, #5
.Lappend:
    ldmia r1!, {r0, r3, r5}
    stmia r8!, {r0, r3, r5}
    subs r2, r2, #1
    bne .Lappend

    str r7, [r4]
    add r0, r7, #216
    str r0, [r4, #4]
    str r0, [r4, #8]

    mov r0, r4
    pop {r4, r5, r6, r7, r8, pc}

.Lget_ret:
    bx lr

@ Each entry is a 12-byte libc++ short string: byte 0 is len << 1, the
@ characters follow immediately, and the remainder is zero padding.
.balign 4
.Llabels:
    .byte 0x12
    .ascii "Mount all"
    .byte 0, 0
    .byte 0x0e
    .ascii "Unmount"
    .byte 0, 0, 0, 0
    .byte 0x12
    .ascii "Part info"
    .byte 0, 0
    .byte 0x12
    .ascii "Save logs"
    .byte 0, 0
    .byte 0x14
    .ascii "Reboot rec"
    .byte 0

.org 0x100

@ ---------------------------------------------------------------------------
@ InvokeMenuItem(index): for indexes 0..12 reproduce the original lookup in
@ the MenuItem vector (0x3aa48, 16-byte entries, action at +0xc).  Indexes
@ 13..17 map to builtin actions 20..24.
@ ---------------------------------------------------------------------------
.thumb_func
hook_invoke:
.Linv_base:
    cmp r1, #13
    bhs .Lnew
    adr r3, .Linv_base
    movw r2, #0x16b8
    sub r0, r3, r2              @ r0 = &menu_items (0x3aa48)
    ldr r0, [r0]
    add.w r0, r0, r1, lsl #4
    ldr r0, [r0, #0xc]
    bx lr
.Lnew:
    add r0, r1, #7              @ 13 -> 20 ... 17 -> 24
    bx lr
