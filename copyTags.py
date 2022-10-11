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

def backupFile(path):
    bupPath = pathlib.Path(path.with_suffix(path.suffix + '.bak'))
    print("Backing up {} to {}".format(path, bupPath))
    shutil.copy2(path, bupPath)

def addTuple(a, b):
    return tuple(map(sum, zip(a, b)))

def matchFiles(srcs, dsts):
    return list(zip(sorted(srcs), sorted(dsts)))

def isAudio(path):
    return magic.from_file(str(path), mime=True).startswith('audio/')

def copyTree(srcDir, dstDir, backup=False, replace=False, delete=False, dryrun=False, preserve=False, tags=None, short=False, skiptags=['artwork']):
    print("Processing Tree: {} to {}".format(colored(srcDir, "yellow"), colored(dstDir, "yellow")))
    changes = copyDir(srcDir, dstDir, backup=backup, replace=replace, delete=delete, preserve=preserve, dryrun=dryrun, tags=tags, short=short, skiptags=skiptags)

    subDirs = sorted([x.name for x in srcDir.iterdir() if x.is_dir()])
    for i in subDirs:
        subSrc = pathlib.Path(srcDir, i)
        subDst = pathlib.Path(dstDir, i)
        if subDst.is_dir():
            changes2 = copyTree(subSrc, subDst, backup=backup, replace=replace, delete=delete, preserve=preserve, dryrun=dryrun, tags=tags, short=short, skiptags=skiptags)
            changes = addTuple(changes, changes2)
        elif subDst.exists():
            print("{} is not a directory".format(colored(subDst, "red")))
        else:
            print("{} does not exist".format(colored(subDst, "red")))

    return changes


def copyDir(srcDir, dstDir, backup=False, replace=False, delete=False, dryrun=False, preserve=False, tags=None, short=False, skiptags=['artwork']):
    print("Processing directory: {} into {}".format(colored(srcDir, "cyan"), colored(dstDir, "cyan")))
    srcFiles = filter(lambda x: x.is_file() and isAudio(x), srcDir.iterdir())
    dstFiles = filter(lambda x: x.is_file() and isAudio(x), dstDir.iterdir())

    nChanges = (0, 0, 0, 0, 0)

    pairs = matchFiles(srcFiles, dstFiles)

    for files in pairs:
        changes =  copyTags(files[0], files[1], backup=backup, replace=replace, delete=delete, preserve=preserve, dryrun=dryrun, tags=tags, short=short, skiptags=skiptags)
        nChanges = addTuple(nChanges, changes)

    return nChanges

def copyTags(fromPath, toPath, backup=False, replace=False, delete=False, dryrun=False, tags=None, preserve=False, short=False, skiptags=['artwork']):
    print("Copying tags from {} to {}".format(colored(fromPath, 'green'), colored(toPath, 'green')))
    added = []
    replaced = []
    deleted = []

    if backup and not dryrun:
        backupFile(toPath)

    times = toPath.stat()

    frTags = music_tag.load_file(fromPath)
    toTags = music_tag.load_file(toPath)

    changed = False
    nAdded = 0
    nReplaced = 0
    nDeleted = 0
    nErrors = 0

    if not tags:
        tags = list(filter(lambda x: not x.startswith("#") and not x in skiptags, frTags.tags()))

    for tag in tags:
        try:
            if not tag in frTags:
                continue
            frValue = frTags[tag]
            # Get the "to" value
            # if the value is unparseable, just ignore it
            try:
                if tag in toTags:
                    toValue = toTags[tag]
                else:
                    toValue = None
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
                    replaced.append(tag)
                    nReplaced += 1

                    if not short:
                        print("\tReplacing {:25}: {} -> {}".format(tag, frValue, toValue))
                else:
                    added.append(tag)
                    nAdded += 1
                    if not short:
                        print("\tAdding    {:25}: {}".format(tag, frValue))
                toTags[tag] = frValue
                changed = True
            elif delete and toValue:
                deleted.append(tag)
                if not short:
                    print("\tDeleting  {:25}".format(tag))
                del toTags[tag]
                nDeleted += 1
                changed = True
        except Exception as e:
            print(colored("Error:", "red") + " Failed copying tag {} from {} to {}".format(colored(tag, "red"), colored(fromPath, 'yellow'), colored(toPath, 'yellow')))
            print(str(e))
            # traceback.print_exc()
            nErrors += 1

    if short:
        if added:
            print("{:9}: {}".format(colored("Added", "cyan"), pprint.pformat(added, compact=True, width=132)))
        if replaced:
            print("{:9}: {}".format(colored("Replaced", "cyan"), pprint.pformat(replaced, compact=True, width=132)))
        if deleted:
            print("{:9}: {}".format(colored("Deleted", "cyan"), pprint.pformat(deleted, compact=True, width=132)))
        if not (added or deleted or replaced):
            print(colored("Nothing changed", "cyan"))
        print()

    if changed and not dryrun:
        toTags.save()
        if preserve:
            os.utime(toPath, times=(times.st_atime, times.st_mtime))
    return (int(changed), nAdded, nReplaced, nDeleted, nErrors)

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
        nChanges = copyTags(src, dst, backup=args.backup, tags=args.tags, dryrun=args.dryrun, preserve=args.preserve, replace=args.replace, delete=args.delete, short=args.short, skiptags=[])

    print("Files Changed: {} Tags Added: {} Tags Replaced: {} Tags Deleted: {} Errors: {}".format(*nChanges))

if __name__ == '__main__':
    main()
