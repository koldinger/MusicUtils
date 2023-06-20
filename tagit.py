#! /usr/bin/env python3
# vim: set et sw=4 sts=4 fileencoding=utf-8:
#
# MusicUtilities: A set of utilities for working with music files.
# Copyright 2013-2024, Eric Koldinger, All Rights Reserved.
# kolding@washington.edu
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import argparse
import pathlib
import shutil
import os

from functools import cache

import magic
import music_tag
from termcolor import cprint

class TagArgument:
    tag   = None
    value = None
    def __init__(self, string):
        tag, value = string.split("=", 1)
        self.tag = tag.strip()
        self.value = value.strip()
        if self.tag.startswith('#'):
            raise ValueError("Cannot set readonly tag {tag}")

def backupFile(path):
    bupPath = pathlib.Path(path.with_suffix(path.suffix + '.bak'))
    print(f"Backing up {path} to {bupPath}")
    shutil.copy2(path, bupPath)


def makeTagValues(tags):
    ret = {}
    if tags:
        for t in tags:
            ret.setdefault(t.tag, set()).add(t.value)
    return ret

def isAudio(path):
    try:
        return magic.from_file(str(path), mime=True).startswith('audio/')
    except:
        return False

def parseArgs():
    parser = argparse.ArgumentParser(description="Copy tags from one file to another, or via directories")
    parser.add_argument("--tags", "-t",     type=TagArgument, action='append', nargs='*', help='List of tags to apply.  Ex: --tags "artist=The Beatles" "album=Abbey Road"')
    parser.add_argument("--delete", "-d",   type=str,  action='append', nargs='*', help='List of tags to delete.   Ex: --delete artist artistsort')
    parser.add_argument("--append", "-a",   type=bool, action=argparse.BooleanOptionalAction, default=False, help="Add values to current tag")
    parser.add_argument("--preserve", "-p", type=bool, action=argparse.BooleanOptionalAction, default=False, help="Preserve timestamps")
    parser.add_argument("--print", "-P",    type=bool, action=argparse.BooleanOptionalAction, default=False, help="Print current tags (no changes made)")
    parser.add_argument("--details", "-D",  type=bool, action=argparse.BooleanOptionalAction, default=False, help="Print encoding details")
    parser.add_argument("--alltags", "-A",  type=bool, action=argparse.BooleanOptionalAction, default=False, help="Print all tags, regardless of whether they contain any data")
    parser.add_argument("--dryrun", "-n",   type=bool, action=argparse.BooleanOptionalAction, default=False, help="Don't save, dry run")
    parser.add_argument("--quiet", "-q",    type=bool, action=argparse.BooleanOptionalAction, default=False, help="Run quietly (except for print)")
    parser.add_argument(type=pathlib.Path,  nargs='+', dest='files', help='Files to change')

    return parser.parse_args()

def flatten(l):
    if isinstance(l, list):
        return [num for sublist in l for num in sublist]
    return l

@cache
def readfile(name):
    with open(name, "rb") as f:
        return f.read()

def processFile(file, tags, delete, preserve, append, dryrun):
    if not isAudio(file):
        print(f"{file} isn't an audio file")
        return
    qprint(f"Processing file {file}")
    data = music_tag.load_file(file)
    updated = False

    times = file.stat()
    for tag in tags:
        if tag.lower() == 'artwork':
            values = map(readfile, tags[tag])
        else:
            values = tags[tag]
        try:
            if values != set(data[tag].values):
                if append:
                    newvals = values.union(data[tag].values)
                else:
                    newvals = list(values)
                qprint(f"    Setting tag {tag} to {newvals}")
                data[tag] = list(newvals)
                updated = True
            #else:
            #    qprint(f"    Not changing tag {tag}.  Value already in tags")
        except KeyError as k:
            cprint(f'Invalid tag name {k}', 'red')
        except ValueError as v:
            cprint(v, 'red')

    if delete:
        for tag in delete:
            if tag in data:
                qprint(f"    Removing tag {tag}")
                data.remove_tag(tag)
                updated = True

    if not dryrun and updated:
        data.save()
        if preserve:
            os.utime(file, times=(times.st_atime, times.st_mtime))

def printFile(file, alltags, details):
    if not isAudio(file):
        return
    cprint(f"File: {file}", "green")
    data = music_tag.load_file(file)

    for tag in sorted(data.tags()):
        if tag.startswith('#') and not (alltags or details):
            continue
        try:
            if data[tag] or alltags:
                print(f"{tag.upper():27}: {data[tag]}")
        except Exception as e:
            cprint(f"Caught exception: {e}", 'red')


beQuiet = False
def qprint(*args):
    if not beQuiet:
        print(*args)

def main():
    global beQuiet
    args = parseArgs()
    if args.quiet:
        beQuiet = True
    if args.print or not (args.tags or args.delete):
        for f in args.files:
            printFile(f, args.alltags, args.details)
    else:
        tags = makeTagValues(flatten(args.tags))
        delete = flatten(args.delete)
        for f in args.files:
            processFile(f, tags, delete, args.preserve, args.append, args.dryrun)

if __name__ == '__main__':
    main()
