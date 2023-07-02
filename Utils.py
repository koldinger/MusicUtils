#! /usr/bin/env python3

import magic

import music_tag

def isAudio(path):
    return magic.from_file(str(path), mime=True).startswith('audio/')


