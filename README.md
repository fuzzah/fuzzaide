# fuzzaide
collection of helper tools for fuzzing

### tools
Fuzzing automator **fuzzman**, Application Verifier crashes minimizer **appverif-minimize.py** and other tools useful in daily fuzzing tasks. Mostly coded in Python 3. See tools directory for more information.

### libexit
LD_PRELOAD this simple lib to force application exit after specified time with specified exit code.<br>
Used to exit closed source binaries running in infinite loop after feeding them fuzzed input with tools like AFL.<br>
See more in corresponding repo directory.

### libpatchfuzz
EXAMPLE / TEMPLATE library for fuzzing closed-source binaries with use of hooking and patching techniques.<br>
Idea: LD_PRELOAD to your tested app, hook code that acquires input buffer data, replace data in buffer with data from stdin.<br>
Optionally: install patches to allow better fuzzing (remove CRC checks), add call to exit after buffer parsing, nop something, etc.<br>
It's not very easy to implement correct hooking code, but will allow to replace arbitrary data in arbitrary chosen place when you don't have access to source code of tested app.<br>
See more in corresponding repo directory.
