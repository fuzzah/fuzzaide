CC = gcc
CFLAGS = -O3

all: clean libexit test

libexit:
	$(CC) -o libexit64.so libexit.c -m64 -fPIC -shared $(CFLAGS) -lpthread
	$(CC) -o libexit32.so libexit.c -m32 -fPIC -shared $(CFLAGS) -lpthread
test:
	$(CC) -o test test.c

clean:
	rm -f libexit64.so
	rm -f libexit32.so
	rm -f test
