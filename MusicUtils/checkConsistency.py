#! /usr/bin/env python3

import argparse
import pathlib
import magic
import pprint

from functools import cache

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

    files = d.iterdir()
    for f in files:
        if f.is_file() and isAudio(f):
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

def printDetails(details):
    names = {}
    for v in details.keys():
        names[v] = fmtTuple(v) + ": "
    maxLen = max(map(len, (names.values())))

    for v in details.keys():
        lines = pprint.pformat(details[v], compact=True, width=120).splitlines()
        report(f"    {names[v]:{maxLen}} {lines[0]}")
        for l in lines[1:]:
            print(" " * (maxLen + 4), l)

album_tags = ['album', 'artist', 'albumartist', 'genre', 'artistsort', 'albumartistsort', 'totaldisks', 'artwork', 'media' ]
disk_tags =  ['disknumber', 'totaltracks']

def checkConsistency(directory, details):
    if not directory.is_dir():
        return

    data =  loadTags(directory)

    if data:
        for t in album_tags:
            tagVals, missing = collectAndCheck(t, data)
            if len(tagVals) > 1:
                #print(tagVals.keys(), fmtTuples(tagVals.keys()))
                report(f"Inconsistent {t} values: {fmtTuples(tagVals.keys())}")
                if details:
                    printDetails(tagVals)

            if missing:
                if len(missing) == len(data):
                    report(f"Missing tag {t} in all files")
                else:
                    report(f"Missing tag {t} in files in {missing}")

        diskdata = splitByDisk(data)
        numdisks = getValues('totaldisks', data)
        if len(numdisks) > 1:
            report(f"Unable to check number of disks.  Inconsistent values: {fmtTuples(numdisks)}")
        elif numdisks:
            num = numdisks.pop()
            if len(diskdata) != num:
                report(f"Number of disks listed {num} does not match number of disks {len(diskdata)}")
                disks = getValues('disknumber', data)
                alldisks = set(range(1, num + 1))
                report(f"Missing disks: {alldisks - disks}")

        for disk, dData in diskdata.items():
            for tag in disk_tags:
                tagVals, missing = collectAndCheck(t, dData)
                if len(tagVals) > 1:
                    #report(f"{tagVals.keys()} {fmtTuples(tagVals.keys())}")
                    report(f"Inconsistent {t} values in {disk}: {list(tagVals.keys())}")
                    if details:
                        printDetails(tagVals)
                if missing:
                    if len(missing) == len(dData):
                        report(f"Missing tag {t} in all files for disk {disk}")
                    else:
                        report(f"Missing tag {t} in files for disk {disk} in {missing}")
            totaltracks = getValues('totaltracks', dData)
            if len(totaltracks) > 1:
                report(f"Unable to check number of disks.  Inconsistent values: {list(totaltracks)}")
            elif totaltracks:
                num = totaltracks.pop()
                if len(dData) != num:
                    report(f"Number of tracks listed {num} does not match number of tracks {len(dData)} for disk {disk}")
                    tracks = getValues('tracknumber', dData)
                    alltracks = set(range(1, num + 1))
                    report(f"Missing tracks: {alltracks - tracks}")

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
        print(_dir)
        _first = False
    print(string)

@cache
def fmtTuple(x):
    if len(x) == 1:
        return x[0]
    #return "(" + ", ".join(str(x)) + ")"
    return "(" + ", ".join(x) + ")"

@cache
def quoteComma(x):
    if ',' in x:
        return f'"{x}"'
    return x

def fmtTuples(x):
    return ", ".join(map(fmtTuple, map(quoteComma, x)))


def checkDir(d, details, recurse):
    setDir(d)
    checkConsistency(d, details)
    if recurse:
        for i in sorted(d.iterdir()):
            if i.is_dir():
                checkDir(i, details, True)

def main():
    args = parse_args()

    for i in args.directories:
        checkDir(i, args.details, args.recurse)


if __name__ == "__main__":
    main()
