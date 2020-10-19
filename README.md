# fuzzaide
collection of helper tools for fuzzing

### tools
Fuzzing automator **fuzzman**, Application Verifier crashes minimizer **appverif-minimize.py** and other tools useful in daily fuzzing tasks. Mostly coded in Python 3. See tools directory for more information.

### libexit
LD_PRELOAD this simple lib to force application exit after specified time with specified exit code.<br>
Used to exit closed source binaries running in infinite loop after feeding them fuzzed input with tools like AFL.<br>
See more in corresponding repo directory.
