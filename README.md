# fuzzaide
collection of helper tools for fuzzing

## tools
Fuzzing automator **fuzzman**, WinAFL and Application Verifier crashes minimizer **appverif-minimize.py**, unique files extractor **dupmanage** and other tools useful in daily fuzzing tasks. Python 3 compatible.<br>
Visit [tools](fuzzaide/tools) directory for more information.<br>

Note: the last working Python 2 version is in the `py2` branch, and the `py2_no_setup` branch has tools in their single-file form, which require no installation. For both the minimal python version is 2.6. These are not supported and only kept here for ancient systems with no updates available.<br>

## libs
Short descriptions are given below.<br>
Visit [libs](libs) directory for more info.<br>

### libexit
LD_PRELOAD this simple lib to force application exit after specified time with specified exit code.<br>
Used to exit closed source binaries running in infinite loop after feeding them fuzzed input with tools like AFL.<br>

### libpatchfuzz
EXAMPLE / TEMPLATE library for fuzzing closed-source binaries with use of hooking and patching techniques.<br>
Idea: LD_PRELOAD to your tested app, hook code that acquires input buffer data, replace data in buffer with data from stdin.<br>
