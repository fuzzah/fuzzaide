CC ?= gcc
CFLAGS ?= -O3

all: fuzzable

fuzzable:
	$(CC) -o fuzzable64 fuzzable.c -m64 -fPIC $(CFLAGS)
	$(CC) -o fuzzable32 fuzzable.c -m32 -fPIC $(CFLAGS)

clean:
	rm -f fuzzable64
	rm -f fuzzable32
