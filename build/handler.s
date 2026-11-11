.syntax unified
.arch armv7-a
.thumb
.section .text
.global action_handler
.thumb_func
action_handler:
    push {r4, r5, r6, r7, r8, r9, r10, r11, r12, lr}
    sub sp, sp, #64
    mov r4, r5
    cmp r4, #20
    blo .Ldone
    cmp r4, #24
    bhi .Ldone

    blx fork_stub
    cmp r0, #0
    blt .Ldone
    beq .Lchild

    mov r1, #0
    mov r2, #0
    blx waitpid_stub
    b .Ldone

.Lchild:
    sub r1, r4, #20
    add r1, r1, #0x30
    mov r2, #0x32
    strb r2, [sp, #16]
    strb r1, [sp, #17]
    mov r2, #0
    strb r2, [sp, #18]

    adr r0, sh_path
    str r0, [sp, #0]
    adr r0, tools_path
    str r0, [sp, #4]
    add r0, sp, #16
    str r0, [sp, #8]
    mov r0, #0
    str r0, [sp, #12]

    adr r0, sh_path
    mov r1, sp
    blx execv_stub

    mov r0, #127
    blx exit_stub

.Ldone:
    add sp, sp, #64
    pop.w {r4, r5, r6, r7, r8, r9, r10, r11, r12, lr}
    b.w default_path

.balign 4
sh_path:
    .asciz "/system/bin/sh"
.balign 4
tools_path:
    .asciz "/system/bin/recovery-tools"
