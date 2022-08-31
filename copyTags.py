#! /usr/bin/env python3

import argparse
import pathlib
import music_tag
import shutil
import magic
import sys
from termcolor import colored, cprint

def backupFile(path):
    bupPath = pathlib.Path(path.with_suffix(path.suffix + '.bak'))
    print("Backing up {} to {}".format(path, bupPath))
    shutil.copy2(path, bupPath)

def matchFiles(srcs, dsts):
    return(list(zip(sorted(srcs), sorted(dsts))))

def isAudio(path):
    return magic.from_file(str(path), mime=True).startswith('audio/')

def copyDir(srcDir, dstDir, backup=False, replace=False, delete=False, dryrun=False, tags=None, skiptags=['artwork']):
    srcFiles = filter(lambda x: x.is_file() and isAudio(x), srcDir.iterdir())
    dstFiles = filter(lambda x: x.is_file() and isAudio(x), dstDir.iterdir())

    pairs = matchFiles(srcFiles, dstFiles)

    for files in pairs:
        copyTags(files[0], files[1], backup=backup, replace=replace, delete=delete, tags=tags, skiptags=skiptags)

def copyTags(fromPath, toPath, backup=False, replace=False, delete=False, dryrun=False, tags=None, skiptags=['artwork']):
    print("Copying tags from {} to {}".format(colored(fromPath, 'green'), colored(toPath, 'green')))
    if backup and not dryrun:
        backupFile(toPath)

    frTags = music_tag.load_file(fromPath)
    toTags = music_tag.load_file(toPath)

    if not tags:
        tags = list(filter(lambda x: not x.startswith("#") and not x in skiptags, frTags.tags()))

    for tag in tags:
        if not tag in frTags:
            continue
        frValue = frTags[tag]
        if tag in toTags:
            toValue = toTags[tag]
        else:
            toValue = None

        if frValue:
            if toValue:
                #print(tag, frValue, toValue, type(frValue), type(toValue))
                if frValue.values == toValue.values:
                    continue
                if not replace:
                    continue
                print("\tReplacing {:25}: {} -> {}".format(tag, frValue, toValue))
            else:
                print("\tAdding    {:25}: {}".format(tag, frValue))
            toTags[tag] = frValue
        elif delete and toValue:
            print("\tDeleting  {:25}".format(tag))
            del toTags[tag]

    if not dryrun:
        toTags.save()

def parseArgs():
    parser = argparse.ArgumentParser(description="Copy tags from one file to another, or via directories")
    parser.add_argument("--backup", "-b", type=bool, nargs="?", default=False, const=True, help="Backup destination files before modification")
    parser.add_argument("--replace", "-r", type=bool, nargs="?", default=False, const=True, help="Replace existing tags in destination")
    parser.add_argument("--delete", "-d", type=bool, nargs="?", default=False, const=True, help="Delete tags from destination that don't exist in source")
    parser.add_argument("--preserve", "-p", type=bool, nargs="?", default=False, const=True, help="Preserve timestamps")
    parser.add_argument("--dryrun", "-n", type=bool, nargs="?", default=False, const=True, help="Don't save, dry run")
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
        copyDir(src, dst, backup=args.backup, tags=args.tags, dryrun=args.dryrun, replace=args.replace, delete=args.delete)
    else:
        copyTags(src, dst, backup=args.backup, tags=args.tags, dryrun=args.dryrun, replace=args.replace, delete=args.delete)

if __name__ == '__main__':
    main()
