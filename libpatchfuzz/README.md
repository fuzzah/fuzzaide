# fuzzaide
collection of helper tools for fuzzing

## libpatchfuzz
EXAMPLE / TEMPLATE library for fuzzing closed-source binaries.<br>
Idea: LD_PRELOAD to your tested app, hook code that acquires input buffer data, replace data in buffer with data from stdin.<br>
Optionally: install patches to allow better fuzzing (remove CRC checks), add call to exit after buffer parsing, nop something, etc.<br>
It's not very easy to implement correct hooking code, but will allow to replace arbitrary data in arbitrary chosen place when you don't have access to source code of tested app.<br>

Example use (e.g. to test if your hook works):<br>
 ```
 $ env LD_PRELOAD=./libpatchfuzz32.so ./myapp
 ```
This will make application to perform additional actions as you implemented in libpatchfuzz.c (probably read data from stdin and replace original input buffer)<br>
Using with AFL:<br>
 ```
 $ env AFL_PRELOAD=./libpatchfuzz32.so afl-fuzz -Q -m none -i in -o out -- ./some_udp_server
 ```

Some tips:<br>
1. Use IDA/Ghidra/Cutter/etc to find better place to hook code.<br>
2. Better place usually comes AFTER input decryption, CRC checking etc.<br>
3. Use debugger if something fails to work.<br>
4. If you're fuzzing some endlessly running server, don't forget to inject call to exit() after input procecssing.<br>

