#! /usr/bin/env python3

import argparse
import pathlib
import magic
import pprint

import music_tag


def isAudio(path):
    return magic.from_file(str(path), mime=True).startswith('audio/')

def parse_args():
    p = argparse.ArgumentParser("Check music files for consistent tagging")
    p.add_argument('--recurse', '-R', dest='recurse', default=False, action=argparse.BooleanOptionalAction, help='Recurse through the tree')
    p.add_argument('--details', '-d', dest='details', default=False, action=argparse.BooleanOptionalAction, help='Print full details of inconsistencies')
    p.add_argument('directories', type=pathlib.Path, nargs='+', help="Directories to check")

    args = p.parse_args()
    return(args)

def loadTags(d):
    #print(f"Loading tags for dir {d}")
    data = {}
    dirs = []

    files = d.iterdir()
    for f in files:
        #print(f"Loading tags for file {f}")
        if f.is_dir():
            dirs.append(f)
        elif isAudio(f):
            data[f.name] = music_tag.load_file(f.resolve())
        else:
            #print(f"Skipping non-audio file {f}")
            pass

    return data, dirs

def collectAndCheck(tag, data):
    values = {}
    missing = []

    for file in data:
        x = data[file].get(tag)
        if x:
            val = tuple(sorted(x.values))
            values.setdefault(val, []).append(file)
        else:
            missing.append(file)
    return values, missing

check_tags = ['album', 'artist', 'albumartist', 'genre', 'albumartistsort', 'disknumber', 'compilation' ]

def checkConsistency(d, details, recurse):
    if not d.is_dir():
        return

    data, subDirs = loadTags(d)

    tagVals = {}
    missing = []

    if data:
        for t in check_tags:
            tagVals, missing = collectAndCheck(t, data)
            if len(tagVals) > 1:
                print(f"Inconsistent {t} values in {d}: {list(tagVals.keys())}")
                if details:
                    for v in tagVals.keys():
                        print(f"    {v}: {tagVals[v]}")

            if missing:
                print(f"Missing tag {t} in files in {d}")
                pprint.pprint(missing, compact=True, indent=8)

    if recurse:
        for i in sorted(subDirs):
            print("-" * 80)
            print(i)
            checkConsistency(i, details, True)

def main():
    args = parse_args()

    for i in args.directories:
        checkConsistency(i, args.details, args.recurse)


if __name__ == "__main__":
    main()
