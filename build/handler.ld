SECTIONS {
  . = 0x4e200;
  .text : { *(.text) }
  fork_stub = 0x465d0;
  waitpid_stub = 0x46d50;
  execv_stub = 0x46d70;
  exit_stub = 0x468b0;
  default_path = 0x17d6a;
}
