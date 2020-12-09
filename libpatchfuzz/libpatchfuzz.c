#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

uint8_t *pPacketStr;
int32_t ulPacketSize;
char szDbgStr[0x1000];

void data_replacer(void) {
  // pushad && new code && popad
  // repeat overwritten code
  // push return address && ret

  asm volatile("pusha\n\t"
               "movl %eax, ulPacketSize\n\t" // store to global variables
               "movl %edi, pPacketStr\n\t");

  /*
      if (pPacketStr && ulPacketSize > -1) {
      sprintf(szDbgStr,"[!pck] ");
      for(int32_t i=0; i<ulPacketSize; i++)	{
        sprintf(szDbgStr + 7 + i*3, "%02X ", pPacketStr[i]);
      }
      puts(szDbgStr);
          }
  */

  memset(pPacketStr, 0, 576);              // 576 - buffer size in application
  ulPacketSize = read(0, pPacketStr, 576); // read from stdin

  /* ORIGINAL CODE:
    0808eb9a 89 85 80 fd ff ff    MOV        dword ptr [EBP + 0xfffffd80],EAX
    0808eba0 83 f8 ff             CMP        EAX,-0x1
  */

  asm volatile(
      "popa\n\t"
      "pop %ebx\n\t"                    // repeat this function epilog
      "mov -0x4(%ebp),%ebx\n\t"
      "leave\n\t"
      "movl ulPacketSize, %eax\n\t"     // store new buffer size
      "movl %eax, 0xfffffd80(%ebp)\n\t" // repeat overwritten instruction
      "push $0x0808eba0\n\t"            // jump to next original instruction
      "ret\n\t");
}

int rand() // remove random in binary
{
  return 0x1337;
}

void exiter(void) { exit(0); }

#define PAGE_SIZE (4096) // $ getconf PAGE_SIZE

uintptr_t get_page_start(uintptr_t addr) { return addr & ~(PAGE_SIZE - 1); }

void change_memory_protection(uintptr_t start, size_t size,
                              uint32_t protection_flags) {
  for (uintptr_t addr = get_page_start(start);
       addr <= get_page_start(start + size - 1); addr += PAGE_SIZE) {
    if (0 > mprotect((void *)addr, PAGE_SIZE, protection_flags)) {
      fprintf(stderr,
              "libpatchfuzz error: wasn't able to change memory protection for "
              "address 0x%p\n",
              (void *)addr);
      exit(299);
    }
  }
}

void hook(uintptr_t hook_from, void *hook_to) {
  change_memory_protection(hook_from, 5, PROT_READ | PROT_WRITE | PROT_EXEC);
  *(uint8_t *)hook_from = 0xE9;
  *(uintptr_t *)(hook_from + 1) =
      (uintptr_t)hook_to - hook_from - 5; // TODO: fix this for x64
  change_memory_protection(hook_from, 5, PROT_READ | PROT_EXEC);
}

void patch(uintptr_t start, size_t len, char *bytes) {
  char *_start = (char *)start;
  change_memory_protection(start, len, PROT_READ | PROT_WRITE | PROT_EXEC);
  for (size_t i = 0; i < len; i++) {
    _start[i] = bytes[i];
  }
  change_memory_protection(start, len, PROT_READ | PROT_EXEC);
}

__attribute__((constructor)) void enrtypoint(void) {
  hook(0x0808eb9a, data_replacer);
  hook(0x08074846, exiter);
  patch(0x080738c6, 6, "\xe9\x05\x04\x00\x00\x90");
  patch(0x0808ec22, 1, "\xeb");
}
