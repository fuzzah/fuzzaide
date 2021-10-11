# -*- coding: utf-8 -*-

# file    :  common/common.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

from __future__ import print_function

try:
    "".isnumeric()
except:
    def isnumeric(s):
        return unicode(s).isnumeric()
else:
    def isnumeric(s):
        return s.isnumeric()
