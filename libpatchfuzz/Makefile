CC = gcc
CFLAGS = -O0

all: clean libpatchfuzz

libpatchfuzz:
#	$(CC) -o libpatchfuzz64.so libpatchfuzz.c -m64 -fPIC -shared $(CFLAGS)
	$(CC) -o libpatchfuzz32.so libpatchfuzz.c -m32 -fPIC -shared $(CFLAGS)

clean:
#	rm -f libpatchfuzz64.so
	rm -f libpatchfuzz32.so

