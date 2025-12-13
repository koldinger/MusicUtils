#! /usr/bin/env python3

import argparse
import collections
import pprint
import sys
from functools import cache
from pathlib import Path

import magic
import music_tag

tag_counts = collections.defaultdict(collections.Counter)

def isAudio(path):
    return magic.from_file(str(path), mime=True).startswith('audio/')

def parse_args():
    p = argparse.ArgumentParser("Check music files for consistent tagging")
    p.add_argument('--recurse', '-R', dest='recurse', default=False, action=argparse.BooleanOptionalAction, help='Recurse through the tree')
    p.add_argument('--details', '-d', dest='details', default=False, action=argparse.BooleanOptionalAction, help='Print full details of inconsistencies')
    p.add_argument('directories', type=Path, nargs='+', help="Directories to check")

    args = p.parse_args()
    return args

def loadTags(d):
    #print(f"Loading tags for dir {d}")
    data = {}

    files = filter(Path.is_file, d.iterdir())

    for f in files:
        if isAudio(f):
            data[f.name] = music_tag.load_file(f.resolve())

    return data

def collectAndCheck(tag, data):
    values = {}
    missing = []

    for file in data:
        x = data[file].get(tag)
        if x:
            if tag == 'artwork':
                tagVals = map(str, x.values)
            else:
                tagVals = x.values
            val = tuple(sorted(tagVals))
            values.setdefault(val, []).append(file)
        else:
            missing.append(file)
    return values, missing


core_tags = ['genre']
core_values = {
    'genre': {'rock', 'jazz', 'classical', 'blues', 'reggae'}
}

collect_tags = ['genre', 'media']

def checkCoreValues(tag_values, coreVals: set[str]):
    missing_core = []
    for value, tracks in tag_values.items():
        if not coreVals.intersection(map(str.lower, value)):
            missing_core += tracks

    return missing_core

def getValues(tag, data):
    values = set()
    for file in data:
        x = data[file].get(tag)
        if x:
            values.add(x.first)
    return values

def splitByDisk(data):
    disks = {}
    for i in data:
        disknum = data[i].get('disknumber')
        if disknum:
            num = disknum.first
        else:
            num = 0
        disks.setdefault(num, {}).update({i: data[i]})

    return disks

def maxKey(details):
    return max(map(len, details.keys()))

def printDetails(details):
    names = {}
    for v in details.keys():
        names[v] = fmtTuple(v) + ": "
    maxLen = max(map(len, (names.values())))

    for k, v in details.items():
        lines = pprint.pformat(sorted(v), compact=True, width=120).splitlines()
        report(f"    {names[k]:{maxLen}} {lines[0]}")
        for l in lines[1:]:
            print(" " * (maxLen + 4), l)

def countline(data, width, header, maxwidth = 120):
    line = header
    ret = []

    for i, j in data.items():
        field = f"{i:{width}}: {j:-5}"
        line += "  " + field
        if len(line) > maxwidth:
            ret.append(line)
            line = header

    if line != header:
        ret.append(line)
    return ret

def printCounts(details: dict[str,collections.Counter]):
    names = {}
    for v in details.keys():
        names[v] = fmtTuple(v) + ": "
    maxLen = max(map(len, (names.values())))

    for k, v in details.items():
        fwidth = maxKey(v)
        lines = countline(v, fwidth, "\t", 120)
        report(f"    {names[k]:{maxLen}}")
        for line in lines:
            print(line)



album_tags = ['album', 'artist', 'albumartist', 'genre', 'artistsort', 'albumartistsort', 'totaldisks', 'artwork', 'media' ]
disk_tags =  ['disknumber', 'totaltracks']

def checkConsistency(directory, details):
    if not directory.is_dir():
        return

    data =  loadTags(directory)
    missing_core = {}

    if data:
        for tag in album_tags:
            tagVals, missing = collectAndCheck(tag, data)
            if len(tagVals) > 1:
                #print(tagVals.keys(), fmtTuples(tagVals.keys()))
                report(f"Inconsistent {tag} values: {fmtTuples(tagVals.keys())}")
                if details:
                    printDetails(tagVals)

            if missing:
                if len(missing) == len(data):
                    report(f"Missing tag {tag} in all files")
                else:
                    report(f"Missing tag {tag} in files in {pprint.pformat(sorted(missing), compact=True)}")

            if tag in core_tags:
                missing = checkCoreValues(tagVals, core_values[tag])
                if missing:
                    missing_core[(tag,)] = missing

            if tag in collect_tags:
                counter = tag_counts[(tag,)]
                for key, value in tagVals.items():
                    # Key is a tuple, so take each subkey
                    for subkey in key:
                        counter[subkey] += len(value)

        diskdata = splitByDisk(data)
        numdisks = getValues('totaldisks', data)
        if len(numdisks) > 1:
            report(f"Unable to check number of disks.  Inconsistent values: {list(numdisks)}")
        elif numdisks:
            num = numdisks.pop()
            if len(diskdata) != num:
                report(f"Number of disks listed {num} does not match number of disks {len(diskdata)}")
                disks = getValues('disknumber', data)
                alldisks = set(range(1, num + 1))
                report(f"Missing disks: {alldisks - disks}")

        for disk, dData in diskdata.items():
            for tag in disk_tags:
                tagVals, missing = collectAndCheck(tag, dData)
                if len(tagVals) > 1:
                    #report(f"{tagVals.keys()} {fmtTuples(tagVals.keys())}")
                    report(f"Inconsistent {tag} values in {disk}: {list(tagVals.keys())}")
                    if details:
                        printDetails(tagVals)
                if missing:
                    if len(missing) == len(dData):
                        report(f"Missing tag {tag} in all files for disk {disk}")
                    else:
                        report(f"Missing tag {tag} in files for disk {disk} in {missing}")
            totaltracks = getValues('totaltracks', dData)
            if len(totaltracks) > 1:
                report(f"Unable to check number of tracks.  Inconsistent values: {list(totaltracks)}")
            elif totaltracks:
                num = totaltracks.pop()
                if len(dData) != num:
                    report(f"Number of tracks listed {num} does not match number of tracks {len(dData)} for disk {disk}")
                    tracks = getValues('tracknumber', dData)
                    alltracks = set(range(1, num + 1))
                    report(f"Missing tracks: {alltracks - tracks}")

        if missing_core:
            report("Tracks missing core values")
            printDetails(missing_core)
            #for tag, tracks in missing_core.items():
            #report(f"Tracks missing core {tag}: {sorted(tracks)}")

_first = True
_dir = None
def setDir(d):
    global _first, _dir
    _dir = d
    _first = True

def report(string):
    global _first
    if _first:
        print("-" * 40)
        if _dir:
            print(_dir)
        _first = False
    print(string)

@cache
def fmtTuple(x):
    if len(x) == 1:
        return str(x[0])
    #return "(" + ", ".join(str(x)) + ")"
    return "(" + ", ".join(x) + ")"

@cache
def quoteComma(x):
    if ',' in x:
        return f'"{x}"'
    return x

def fmtTuples(x):
    ic(x)
    return ", ".join(map(fmtTuple, map(quoteComma, x)))


def checkDir(d, details, recurse):
    setDir(d)
    checkConsistency(d, details)
    if recurse:
        for i in sorted(filter(Path.is_dir, d.iterdir())):
            checkDir(i, details, True)

def main():
    try:
        args = parse_args()

        for i in args.directories:
            checkDir(i, args.details, args.recurse)

        setDir('')

        print('')
        print('-' * 60)
        print("Summary values")
        print('-' * 60)
        printCounts(tag_counts)

    except KeyboardInterrupt:
        sys.exit("Interupted")

if __name__ == "__main__":
    main()
