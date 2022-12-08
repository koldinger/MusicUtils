#! /usr/bin/env python3

import argparse
import pathlib
import shutil
import sys
import os
import pprint
import traceback

import magic
import music_tag

from termcolor import colored

class PrintOnce:
    def __init__(self, message):
        self.message = message
        self.first = True

    def print(self):
        if self.first:
            print(self.message)
            self.first = False

def backupFile(path):
    bupPath = pathlib.Path(path.with_suffix(path.suffix + '.bak'))
    print("Backing up {} to {}".format(path, bupPath))
    shutil.copy2(path, bupPath)


def makeTagValues(tags):
    tags = map(lambda x: map(lambda y: y.strip(), x.split("=")), tags)
    ret = {}
    for x, y in tags:
        ret.setdefault(x, set()).add(y)
    return ret

def isAudio(path):
    return magic.from_file(str(path), mime=True).startswith('audio/')

def parseArgs():
    parser = argparse.ArgumentParser(description="Copy tags from one file to another, or via directories")
    parser.add_argument("--tags", "-t",     type=str,  action='append', nargs='*', help='List of tags to apply.  Ex: --tags "artist=The Beatles" "album=Abbey Road"')
    parser.add_argument("--delete", "-d",   type=str,  action='append', nargs='*', help='List of tags to delete.   Ex: --delete artist artistsort')
    parser.add_argument("--append", "-a",   type=bool, action=argparse.BooleanOptionalAction, default=False, help="Add values to current tag")
    parser.add_argument("--preserve", "-p", type=bool, action=argparse.BooleanOptionalAction, default=False, help="Preserve timestamps")
    parser.add_argument("--print", "-P",    type=bool, action=argparse.BooleanOptionalAction, default=False, help="Print current tags (no changes made)")
    parser.add_argument("--alltags", "-A",  type=bool, action=argparse.BooleanOptionalAction, default=False, help="Print all tags, regardless of if they exist")
    parser.add_argument("--dryrun", "-n",   type=bool, action=argparse.BooleanOptionalAction, default=False, help="Don't save, dry run")
    parser.add_argument(type=pathlib.Path,  nargs='+', dest='files', help='Files to change')

    return parser.parse_args()

def flatten(l):
    if isinstance(l, list):
        return [num for sublist in l for num in sublist]
    return l

def processFile(f, tags, delete, preserve, append, dryrun):
    if not isAudio(f):
        return
    print(f"Processing file {f}")
    data = music_tag.load_file(f)
    updated = False

    times = f.stat()
    for tag in tags:
        values = tags[tag]
        if values != set(data[tag].values):
            if append:
                newvals = values.union(data[tag].values)
            else:
                newvals = list(values)
            print(f"    Setting tag {tag} to {newvals}")
            data[tag] = list(newvals)
            updated = True
        else:
            print(f"    Not changing tag {tag}.  Already correct")

    if delete:
        for tag in delete:
            if tag in data:
                print(f"    Removing tag {tag}")
                data.remove_tag(tag)
                updated = True

    if not dryrun and updated:
        data.save()
        if preserve:
            os.utime(f, times=(times.st_atime, times.st_mtime))

def printFile(f, all):
    if not isAudio(f):
        return
    print(f"File: {f}")
    data = music_tag.load_file(f)

    for t in sorted(data.tags()):
        if data[t] or all:
            print("{:27}: {}".format(t.upper(), data[t]))


def main():
    args = parseArgs()
    if args.print or not args.tags:
        for f in args.files:
            printFile(f, args.alltags)
    else:
        tags = makeTagValues(flatten(args.tags))
        delete = flatten(args.delete)
        for f in args.files:
            processFile(f, tags, delete, args.preserve, args.append, args.dryrun)

if __name__ == '__main__':
    main()
