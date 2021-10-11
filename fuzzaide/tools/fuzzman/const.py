# -*- coding: utf-8 -*-

# file    :  tools/fuzzman/const.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

# some terminal constants from AFL

cGRA = b"\x1b[1;90m"
cRST = b"\x1b[0m"

TERM_CLEAR = b"\x1b[H\x1b[2J"
cEOL = b"\x1b[0K"
CURSOR_HIDE = b"\x1b[?25l"
CURSOR_SHOW = b"\x1b[?25h"

SET_G1 = b"\x1b)0"  # /* Set G1 for box drawing    */
RESET_G1 = b"\x1b)B"  # /* Reset G1 to ASCII         */
bSTART = b"\x0e"  # /* Enter G1 drawing mode     */
bSTOP = b"\x0f"  # /* Leave G1 drawing mode     */

bSTG = bSTART + cGRA


# this part needs to be replaced with TERM_CLEAR from status screen in python2
TERM_CLEAR_PY2_REPLACE = b"\x1b[H"
