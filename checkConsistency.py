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



album_tags = ['album', 'artist', 'albumartist', 'genre', 'artistsort', 'albumartistsort', 'totaldisks', 'artwork' ]
disk_tags =  ['disknumber', 'totaltracks']

def checkConsistency(d, details):
    if not d.is_dir():
        return

    data =  loadTags(d)

    if data:
        for t in album_tags:
            tagVals, missing = collectAndCheck(t, data)
            if len(tagVals) > 1:
                #print(tagVals.keys(), fmtTuples(tagVals.keys()))
                report(f"Inconsistent {t} values in {d}: {fmtTuples(tagVals.keys())}")
                if details:
                    for v in tagVals.keys():
                        report(f"    {v}: {tagVals[v]}")

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
        
        for disk in diskdata:
            d = diskdata[disk]
            for tag in disk_tags:
                tagVals, missing = collectAndCheck(t, d)
                if len(tagVals) > 1:
                    print(tagVals.keys(), fmtTuples(tagVals.keys()))
                    report(f"Inconsistent {t} values in {disk}: {list(tagVals.keys())}")
                    if details:
                        for v in tagVals.keys():
                            print(f"    {v}: {tagVals[v]}")
                if missing:
                    if len(missing) == len(d):
                        report(f"Missing tag {t} in all files for disk {disk}")
                    else:
                        report(f"Missing tag {t} in files for disk {disk} in {missing}")
            totaltracks = getValues('totaltracks', d)
            if len(totaltracks) > 1:
                report(f"Unable to check number of disks.  Inconsistent values: {list(totaltracks)}")
            elif totaltracks:
                num = totaltracks.pop()
                if len(d) != num:
                    report(f"Number of tracks listed {num} does not match number of tracks {len(d)} for disk {disk}")
                    tracks = getValues('tracknumber', d)
                    alltracks = set(range(1, num + 1))
                    report(f"Missing tracks: {alltracks - tracks}")


__first = True
__dir = None
def setDir(d):
    global __first, __dir
    __dir = d
    __first = True

def report(string):
    global __first, __dir
    if __first:
        print("-" * 40)
        print(__dir)
        __first = False
    print(string)

def fmtTuple(x):
    if len(x) == 1:
        return x[0]
    #return "(" + ", ".join(str(x)) + ")"
    return "(" + ", ".join(x) + ")"

def fmtTuples(x):
    return ", ".join(map(fmtTuple, x))


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
