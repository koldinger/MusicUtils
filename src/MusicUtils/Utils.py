#! /usr/bin/env python3

import magic


def isAudio(path):
    return magic.from_file(path, mime=True).startswith('audio/')

def addTuples(*args):
    return tuple(map(sum, zip(*args)))
