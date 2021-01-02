# fuzzaide
collection of helper tools for fuzzing

## libexit
LD_PRELOAD this simple lib to force application exit after specified time with specified exit code.<br>
Used to exit closed source binaries running in infinite loop after feeding them fuzzed input with tools like AFL.<br>

Library expects you to set environment variables:<br>
 LIBEXIT_SLEEP - pause before calling exit (in milliseconds)<br>
 LIBEXIT_CODE - exit code to use when calling exit (by default 0)<br>
Example use:<br>
 `$ env LD_PRELOAD=./libexit64.so LIBEXIT_SLEEP=3000 LIBEXIT_CODE=5 ./test`<br>
This will make app close after 3 seconds with exit code 5<br>
Using with AFL:<br>
 ```
 $ env AFL_PRELOAD=./socketfuzz64.so:./libexit64.so LIBEXIT_SLEEP=75 afl-fuzz -m none -Q -t 85 -i in -o out -- ./fuzzed_app -i @@
 ```
Beware of decreasing AFL fuzzing stability or not discovering new paths, in both cases you should probably increase LIBEXIT_SLEEP and afl-fuzz -t values so that application have enough time to process fuzzed input.<br>
