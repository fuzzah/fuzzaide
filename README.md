# fuzzaide
collection of helper tools for fuzzing

## tools
Fuzzing automator **fuzzman**, WinAFL and Application Verifier crashes minimizer **appverif-minimize.py**, unique files extractor **dupmanage** and other tools useful in daily fuzzing tasks. Python 3 compatible.<br>
Visit [tools](fuzzaide/tools) directory for more information.

## libs
Short descriptions are given below.<br>
Visit [libs](libs) directory for more info.<br>

### libexit
LD_PRELOAD this simple lib to force application exit after specified time with specified exit code.<br>
Used to exit closed source binaries running in infinite loop after feeding them fuzzed input with tools like AFL.<br>

### libpatchfuzz
EXAMPLE / TEMPLATE library for fuzzing closed-source binaries with use of hooking and patching techniques.<br>
Idea: LD_PRELOAD to your tested app, hook code that acquires input buffer data, replace data in buffer with data from stdin.<br>
