#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <signal.h>

void handler(int a)
{
	printf("\nOk, I stop\n");
	exit(0);
}

void main(void)
{
	signal(SIGINT, handler);
	signal(SIGQUIT, handler);
	
	setbuf(stdout, NULL);
	printf("I am server, I only stop when you press Ctrl+C\nworking");
	int i=0;
	while(1)	{
		usleep(500000);
		if(i++ > 2)	{
			i = 0;
			printf("\r               ");
		}
		printf("\rworking");
		for(int j=0; j<i; j++, printf("."));
	}
}
