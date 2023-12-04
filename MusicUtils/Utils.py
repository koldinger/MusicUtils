#! /usr/bin/env python3

import magic

def isAudio(path):
    return magic.from_buffer(open(path, "rb").read(2048), mime=True).startswith('audio/')

def addTuples(*args):
    return tuple(map(sum, zip(*args)))
