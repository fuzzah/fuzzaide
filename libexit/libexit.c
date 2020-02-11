#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <pthread.h>

void* exit_thread(void *ptr)
{
  int ms = 0, ecode = 0;
  char *p = getenv("LIBEXIT_SLEEP");
  if (p) ms = abs(atoi(p));
  
  p = getenv("LIBEXIT_CODE");
  if (p) ecode = atoi(p);

  usleep(ms * 1000);
  exit(ecode);
}

__attribute__((constructor)) void wait_and_quit(void) {
  pthread_t pt;
  if(pthread_create(&pt, NULL, exit_thread, NULL))
	fputs("libexit error: wasn't able to create thread, will not exit!\n", stderr);
}
