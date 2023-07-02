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
import sys
import os
import pprint
import traceback

import magic
import music_tag

from termcolor import colored

from Utils import isAudio

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

def addTuples(*args):
    return tuple(map(sum, zip(*args)))

def matchFiles(srcs, dsts):
    return list(zip(sorted(srcs), sorted(dsts)))

def copyTree(srcDir, dstDir, backup=False, replace=False, delete=False, dryrun=False, preserve=False, tags=None, short=False, skiptags=['artwork']):
    #print("Processing Tree: {} to {}".format(colored(srcDir, "yellow"), colored(dstDir, "yellow")))
    changes = copyDir(srcDir, dstDir, backup=backup, replace=replace, delete=delete, preserve=preserve, dryrun=dryrun, tags=tags, short=short, skiptags=skiptags)

    subDirs = sorted([x.name for x in srcDir.iterdir() if x.is_dir()])
    for i in subDirs:
        subSrc = pathlib.Path(srcDir, i)
        subDst = pathlib.Path(dstDir, i)
        if subDst.is_dir():
            changes2 = copyTree(subSrc, subDst, backup=backup, replace=replace, delete=delete, preserve=preserve, dryrun=dryrun, tags=tags, short=short, skiptags=skiptags)
            changes = addTuples(changes, *changes2)
        elif subDst.exists():
            print("{} is not a directory".format(colored(subDst, "red")))
        else:
            print("{} does not exist".format(colored(subDst, "red")))

    return changes


def copyDir(srcDir, dstDir, backup=False, replace=False, delete=False, dryrun=False, preserve=False, tags=None, short=False, skiptags=[]):
    srcFiles = filter(lambda x: x.is_file() and isAudio(x), srcDir.iterdir())
    dstFiles = filter(lambda x: x.is_file() and isAudio(x), dstDir.iterdir())

    nChanges = (0, 0, 0, 0, 0)

    pairs = matchFiles(srcFiles, dstFiles)

    if pairs:
        print(f"Processing directory: {colored(srcDir, 'cyan')} into {colored(dstDir, 'cyan')}")

    for files in pairs:
        changes =  copyFile(files[0], files[1], backup=backup, replace=replace, delete=delete, preserve=preserve, dryrun=dryrun, tags=tags, short=short, skiptags=skiptags)
        nChanges = addTuples(nChanges, changes)

    return nChanges


def copyTags(frTags, toTags, tags, replace, delete, details=None):
    """ 
    Perform the actual copy of tags from one set to another.
    Arguments:
        frTags: The set of tags to copy from.   music_tags.MediaInfo
        toTags: The set of tags to copy to.     music_tags.MediaInfo
        tags:   A list of tag names to copy.    list[str]
        replace: Boolean, replace tags if they are in the target.  If false, don't overwrite existing tags
        delete:  Boolean.  If true, delete tags that exist in toTags (and tags), but not in frTags
        details: An optional tuple of lists which will be filled.   Contains 4 lists, added, replaced, deleted, and errors
                Upon return:
                    added will contain a list of tuples (tagname, newValue)
                    replaced will contain a list of tuples (tagname, newValue, oldValue)
                    deleted will contain a list of tuples (tagname, oldValue)
                    errors will contain a list of tuples (tagname, exception)
    Returns:
        A boolean indicating if anything changed
        A 4-tuple, containg a count of each value number of tags added, replaced, deleted, and errors
    """
    nReplaced = 0
    nAdded = 0
    nDeleted = 0
    nErrors = 0
    changed = False

    if details:
        (added, replaced, deleted, errors) = details

    for tag in tags:
        try:
            frValue = frTags[tag]

            # Get the "to" value
            # if the value is unparseable, just ignore it
            try:
                toValue = toTags[tag]
            except ValueError:
                toValue = None

            if frValue:
                if toValue:
                    #print(tag, frValue, toValue, type(frValue), type(toValue))
                    if tag == 'artwork':
                        # TODO: This should check all artwork, but I'm lazy, assuming only one in my library.
                        if frValue.first.data == toValue.first.data:
                            continue
                    elif frValue.values == toValue.values:
                        continue
                    if not replace:
                        continue
                    if details:
                        replaced.append((tag, frValue, toValue))
                    nReplaced += 1
                else:
                    if details:
                        added.append((tag, frValue))
                    nAdded += 1

                toTags[tag] = frValue
                changed = True
            elif delete and toValue:
                print("Deleting ", tag)
                if details:
                    deleted.append((tag, toValue))
                del toTags[tag]
                nDeleted += 1
                changed = True
        except Exception as exception:
            if details:
                errors.append((tag, exception))
            nErrors += 1
    return changed, (nAdded, nReplaced, nDeleted, nErrors)

def copyFile(fromPath, toPath, backup=False, replace=False, delete=False, dryrun=False, tags=None, preserve=False, short=False, skiptags=[]):
    added = []
    replaced = []
    deleted = []
    errors = []
    results = (added, replaced, deleted, errors)
    changed = False

    try:
        # If requested, backup the original file
        if backup and not dryrun:
            backupFile(toPath)

        times = toPath.stat()

        frTags = music_tag.load_file(fromPath)
        toTags = music_tag.load_file(toPath)

        if not tags:
            tags = list(filter(lambda x: not x.startswith('#') and not x in skiptags, set(toTags.tags()).union(frTags.tags())))

        changed, counts = copyTags(frTags, toTags, tags, replace, delete, results)
        print(f"{colored('Copying tags from', 'yellow')} {colored(fromPath, 'green')} to {colored(toPath, 'green')}")

        if short:
            if added:
                tags = list(map(lambda x: x[0], added))
                print(f"{colored('Added', 'cyan'):17}: {pprint.pformat(tags, compact=True, width=132)}")
            if replaced:
                tags = list(map(lambda x: x[0], replaced))
                print(f"{colored('Replaced', 'cyan'):17}: {pprint.pformat(tags, compact=True, width=132)}")
            if deleted:
                tags = list(map(lambda x: x[0], deleted))
                print(f"{colored('Deleted', 'cyan'):17}: {pprint.pformat(tags, compact=True, width=132)}")
            if not (added or deleted or replaced):
                print(colored("Nothing changed", "cyan"))
            #print()
        else:
            for (tag, value) in added:
                print("\tAdding    {:25}: {}".format(tag, value))
            for (tag, frValue, toValue) in replaced:
                print("\tReplacing {:25}: {} -> {}".format(tag, toValue, frValue))
            for (tag, value) in deleted:
                print("\tDeleting  {:25}: {}".format(tag, value))
            for (tag, exception) in errors:
                print(f"{colored('Error', 'red')} Failed copying tag {colored(tag, 'red')} from {colored(fromPath, 'yellow')} to {colored(toPath, 'yellow')}")
                print(str(exception))

        if changed and not dryrun:
            toTags.save()
            if preserve:
                os.utime(toPath, times=(times.st_atime, times.st_mtime))
    except Exception as e:
        print(colored("Error", "red") + " Error processing file {}".format(colored(fromPath, 'yellow')))
        print(str(e))
        nErrors += 1
        raise e

    return (int(changed), counts[0], counts[1], counts[2], counts[3])

def parseArgs():
    parser = argparse.ArgumentParser(description="Copy tags from one file to another, or via directories")
    parser.add_argument("--backup", "-b",   type=bool, action=argparse.BooleanOptionalAction, default=False, help="Backup destination files before modification")
    parser.add_argument("--replace", "-r",  type=bool, action=argparse.BooleanOptionalAction, default=False, help="Replace existing tags in destination")
    parser.add_argument("--delete", "-d",   type=bool, action=argparse.BooleanOptionalAction, default=False, help="Delete tags from destination that don't exist in source")
    parser.add_argument("--preserve", "-p", type=bool, action=argparse.BooleanOptionalAction, default=False, help="Preserve timestamps")
    parser.add_argument("--short", "-s",    type=bool, action=argparse.BooleanOptionalAction, default=False, help="Short report")
    parser.add_argument("--dryrun", "-n",   type=bool, action=argparse.BooleanOptionalAction, default=False, help="Don't save, dry run")
    parser.add_argument("--recurse", "-R",  type=bool, action=argparse.BooleanOptionalAction, default=False, help="Recurse into subdirectories")
    parser.add_argument("--tags", type=str, nargs="+", default=None, help="Tags to copy")
    parser.add_argument("tagSource", type=pathlib.Path, nargs=1, help="tagSource")
    parser.add_argument("tagDest", type=pathlib.Path, nargs=1, help="tagDest")
    return parser.parse_args()

def main():
    args = parseArgs()
    src = args.tagSource.pop()
    dst = args.tagDest.pop()
    if src.is_dir() != dst.is_dir():
        print("Error: source and destination must both be files, or directories")
        sys.exit(1)
    if src.is_dir():
        if args.recurse:
            nChanges = copyTree(src, dst, backup=args.backup, tags=args.tags, dryrun=args.dryrun, preserve=args.preserve, replace=args.replace, delete=args.delete, short=args.short, skiptags=[])
        else:
            nChanges = copyDir(src, dst, backup=args.backup, tags=args.tags, dryrun=args.dryrun, preserve=args.preserve, replace=args.replace, delete=args.delete, short=args.short, skiptags=[])
    else:
        nChanges = copyFile(src, dst, backup=args.backup, tags=args.tags, dryrun=args.dryrun, preserve=args.preserve, replace=args.replace, delete=args.delete, short=args.short, skiptags=[])

    print("Files Changed: {} Tags Added: {} Tags Replaced: {} Tags Deleted: {} Errors: {}".format(*nChanges))

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted")
