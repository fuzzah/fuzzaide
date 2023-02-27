# file    :  common/fuzzaide_argparse.py
# repo    :  https://github.com/fuzzah/fuzzaide
# author  :  https://github.com/fuzzah
# license :  MIT
# check repository for more information

import os
import sys
import argparse

class FuzzaideArgumentParser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        argparse.ArgumentParser.__init__(self, *args, **kwargs)
        self.examples = []

    def __print_example(self, action="", cmd=""):
        print(action + ": \n\t" + os.path.basename(sys.argv[0]) + " " + cmd)

    def set_examples(self, examples):
        self.examples = examples

    def print_help(self, with_examples=True):
        argparse.ArgumentParser.print_help(self)
        if with_examples and len(self.examples) > 0:
            print()
            print("Invocation examples:")
            for action, cmd in self.examples:
                self.__print_example(action, cmd)
