#! /usr/bin/env python3
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


import pathlib
import shutil
import os
import textwrap
import re
import json
import csv

from functools import lru_cache, partial
from argparse import ArgumentParser, BooleanOptionalAction, ArgumentTypeError, SUPPRESS, RawDescriptionHelpFormatter, FileType
from hashlib import md5

import magic
import music_tag
import yaml
from PIL import Image
from termcolor import cprint, colored

from MusicUtils.Utils import isAudio

# Extract the list of valid tags from the music_tag module.
ALL_TAGS = sorted(music_tag.tags())
VALID_TAGS = sorted([i for i in map(str.upper, ALL_TAGS) if not i.startswith('#')])

class TagArgument:
    """
    Creates an argument with two fields, tag and value, based on a equals sign (=) in
    the input.
    """
    def __init__(self, string):
        try:
            tag, value = string.split("=", 1)
            value=value.strip()
        except ValueError:
            tag=string.strip("=")
            value=None

        #print(f"Creating {tag} {value} from {string}")
        self.tag = checkTag(tag.strip())
        self.value=value
        if self.tag.startswith('#'):
            raise ArgumentTypeError(f"Cannot set readonly tag {tag}")

def makeTagArgument(tag, value):
    return TagArgument(f"{tag}={value}")

def backupFile(path):
    """
    Backup a file before processing it.
    """
    bupPath = pathlib.Path(path.with_suffix(path.suffix + '.bak'))
    print(f"Backing up {path} to {bupPath}")
    shutil.copy2(path, bupPath)


def makeTagValues(tags):
    ret = {}
    if tags:
        for t in tags:
            ret.setdefault(t.tag, set()).add(t.value)
    return ret

def checkTag(tag):
    """
    Make sure a tag is in a list of the valid tags that can be set.
    """
    tag = tag.upper()
    if not tag.upper() in VALID_TAGS:
        raise ArgumentTypeError(f"{tag} is not a valid tag")
    return tag

def parseArgs():
    epilog = "Tags can also be set with an option like --ARTIST xxx to set the artist tag to xxx.\n\n"+\
             "Valid tags are: \n" +\
             f"{textwrap.fill(', '.join(VALID_TAGS), width=80, initial_indent='    ', subsequent_indent='    ')}"

    parser = ArgumentParser(description="Set or print tags in an audio file",
                            epilog=epilog,
                            formatter_class=RawDescriptionHelpFormatter)
    setGroup = parser.add_argument_group("Tag Setting Options")
    setGroup.add_argument("--tags", "-t",     default=[], dest='tags', type=TagArgument, action='append', nargs='+', help='List of tags to apply.  Ex: --tags "artist=The Beatles" "album=Abbey Road"')
    setGroup.add_argument("--delete", "-d",   type=checkTag,  action='append', nargs='+', help='List of tags to delete.   Ex: --delete artist artistsort')
    setGroup.add_argument("--append", "-a",   type=bool, action=BooleanOptionalAction, default=False, help="Add values to current tag")
    setGroup.add_argument("--clear", '-C',    type=bool, action=BooleanOptionalAction, default=False, help='Remove all tags')
    setGroup.add_argument("--empty", '-e',    type=bool, action=BooleanOptionalAction, default=False, help='Remove empty tags')
    setGroup.add_argument("--preserve", "-p", type=bool, action=BooleanOptionalAction, default=False, help="Preserve timestamps")

    printGroup = parser.add_argument_group("Printing Options")
    printGroup.add_argument("--print", "-P",    type=checkTag,  action='append', nargs='*', metavar='TAG', default=None, help="Print current tags (no changes made)")
    printGroup.add_argument("--details", "-D",  type=bool, action=BooleanOptionalAction, default=False, help="Print tags, including read-only encoding details (starts with #)")
    printGroup.add_argument("--all", "-A",      type=bool, action=BooleanOptionalAction, default=False, help="Print all tags, regardless of whether they contain any data")
    printGroup.add_argument("--lists", "-L",    type=bool, action=BooleanOptionalAction, default=True, help="Print list values separately")
    printGroup.add_argument("--value", "-V",    type=TagArgument, action='append', nargs='+', metavar='TAG=Value', default=[], help="Print only if the tag matches (value is a regular expression)")
    printGroup.add_argument('--names', '-N',    type=bool, action=BooleanOptionalAction, default=False, help="Only list file names that match")


    andOr = printGroup.add_mutually_exclusive_group()
    andOr.add_argument("--and", dest='andOp', action='store_true',  default='True', help="Only print if all values match ")
    andOr.add_argument("--or",  dest='andOp', action='store_false', default='True', help="Print if any values match ")

    saveGroup = parser.add_argument_group("Tag Saving Options (not in music file)")
    saveGroup.add_argument('--save', '-S',     type=FileType('w'), default=None, help="Save tags to a file")
    saveGroup.add_argument('--format', '-F',   type=str, choices=['json', 'yaml', 'csv'], default='yaml', help="Format to use when saving files")

    pathGroup = saveGroup.add_mutually_exclusive_group()
    pathGroup.add_argument('--relative', '-R', type=pathlib.Path, default='.', help="Print paths relative to this directory")
    pathGroup.add_argument('--fullpath',       type=bool, action=BooleanOptionalAction, default=False, help="Use full paths")

    parser.add_argument("--dryrun", "-n",   type=bool, action=BooleanOptionalAction, default=False, help="Don't save, dry run")
    parser.add_argument("--stats", "-s",    type=bool, action=BooleanOptionalAction, default=False, help="Print stats")
    parser.add_argument("--quiet", "-q",    type=bool, action=BooleanOptionalAction, default=False, help="Run quietly (except for print and stats)")

    group = parser.add_argument_group("Tags")
    for arg in VALID_TAGS:
        makeTagValFunc = partial(makeTagArgument, arg)
        group.add_argument(f"--{arg.upper()}", f"--{arg.lower()}", nargs=1, dest="tags", type=makeTagValFunc, action='append', help=SUPPRESS)   #f"Set the {arg} tag")

    parser.add_argument(type=pathlib.Path,  nargs='+', dest='files', help='Files to change')

    return parser.parse_args()

def flatten(l):
    """
    Flatten nested sublists to all be a single list.
    """
    if isinstance(l, list):
        return [num for sublist in l for num in sublist]
    return l

@lru_cache(maxsize=64)
def readfile(name):
    """
    Read a file, and cache the results.   For artwork, so we don't have to read the art files multiple times
    :param name: The filename to read
    :return: The bytes in the file
    """
    with open(name, "rb") as f:
        return f.read()

@lru_cache(maxsize=64)
def imageInfo(name):
    """
    Read an image file, and generate it's image info

    """
    data = readfile(name)
    mime = magic.from_buffer(data, mime=True)
    image = Image.open(name)
    size = image.size
    hash = md5(data).hexdigest()
    info = f"{name} - {mime} {size[0]}x{size[1]} {hash}"
    return info

@lru_cache(maxsize=64)
def loadTags(file):
    return music_tag.load_file(file)

@lru_cache(maxsize=64)
def checkFile(file):
    """
    Check to determine if a file exists, and is an audio file.
    :param file:
    :return:
    """
    try:
        if file.is_dir():
            print(f"{colored('Error: ', 'red')} {file} is a directory")
            return False
        if not (file.is_file() and isAudio(file)):
            print(f"{colored('Error: ', 'red')} {file} isn't an audio file")
            return False
    except FileNotFoundError:
        print(f"{colored('Error: ', 'red')} {file} not found")
        return False
    return True


stats = { 'processed': 0, 'updated'  : 0, 'added'    : 0, 'changed'  : 0, 'deleted'  : 0 }

def processFile(file, tags, delete, preserve, append, empty, dryrun, save):
    if not checkFile(file):
        return

    qprint(colored(f"Processing file {file}", "green"))
    data = loadTags(file)
    updated = False


    stats['processed'] += 1
    times = file.stat()
    for tag in tags:
        if tag.lower() == 'artwork':
            values = map(readfile, tags[tag])
        else:
            values = tags[tag]
        try:
            curVals = set(data[tag].values)
            action = 'changed' if curVals else 'added'
            if values != set(data[tag].values):
                if append:
                    newVals = list(set(values).union(curVals))
                else:
                    newVals = list(values)
                if tag.lower() == 'artwork':
                    if append:
                        vals = list(set(map(imageInfo, tags[tag])).union(map(str, data[tag].values)))
                    else:
                        vals = list(map(imageInfo, tags[tag]))
                    qprint(f"    Setting tag {tag.upper()} to {vals}")
                else:
                    qprint(f"    Setting tag {tag.upper()} to {newVals}")
                data[tag.upper()] = list(newVals)
                stats[action] += 1
                updated = True
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
                stats['deleted'] += 1

    if empty:
        for tag, value in data.items():
            if not value:
                qprint(f"    Removing empty tag {tag}")
                data.remove_tag(tag)
                updated = True
                stats['deleted'] += 1

    if updated:
        stats['updated'] += 1
    if not dryrun and updated:
        data.save()
        if preserve:
            os.utime(file, times=(times.st_atime, times.st_mtime))

    return data

def removeTags(file, preserve, dryrun):
    """ Remove all tags from the file """
    if not checkFile(file):
        return
    times = file.stat()
    data = loadTags(file)
    qprint(f"Removing tags from {file}")
    data.remove_all()

    if not dryrun:
        data.save()
        if preserve:
            os.utime(file, times=(times.st_atime, times.st_mtime))

orderedTags = {
    'title': '00',
    'album': '01',
    'artist': '02',
    'tracknumber': '03',
    'discnumber': '03',
    'discsubtitle': '04'
    }

def tagKey(key):
    return orderedTags.get(key.lower(), '99') + key


def printTags(file, tags, empty, details, names, printList, save):
    """
    Print tags from a file.

    Parameters:
    file (Path):        file to load tags from and to print.
    tags (list[str]):   list of tags to print
    empty   (bool):     print all the tags, even those with empty/no value
    details (bool):     include those that start with a # sign
    names   (bool):     Only printh the name of the file
    printList(bool):    Print all elements of a list together
    save    (bool):     Save the tags for later processing
    """
    if not checkFile(file):
        return

    if names:
        print(file)
        return

    cprint(f"File: {file}", "green")
    data =  loadTags(file)

    for tag in map(str.upper, sorted(data.tags(), key=tagKey)):
        try:
            if tags and not tag in tags:
                continue
            if tag.startswith('#') and not details:
                continue
            if data[tag] or empty:
                if printList:
                    print(f"{tag:27}: {data[tag]}")
                else:
                    for i in data[tag].values:
                        print(f"{tag:27}: {i}")
        except Exception as e:
            cprint(f"Caught exception processing tag {tag}: {e}", 'red')
    return data

savedData={}
def saveTags(file, tagData, fullpath, relative):
    """
    Accumulate data to save a json/yaml/csv catalog file.

    Parameters:
    file (Path): Path of the file we're processing
    tagData(dict):  Tag data to save.
    fullpath(bool): Use full pathnames
    relative(Path): Print files relative to this path
    """

    if fullpath:
        file = file.absolute()
    elif relative:
        try:
            file = file.absolute().relative_to(relative.absolute())
        except ValueError:
            pass

    data = {}
    for tag in tagData.tags():
        d = tagData.get(tag).values
        if len(d) == 0:
            continue

        if len(d) == 1 and tag.lower() != 'artwork':
            # Ignore artwork, it will get converted to a string below.   We mostly want to keep Int's valid here.
            d = d[0]
        else:
            d = ", ".join(map(str, d))

        data[tag] = d
    savedData[str(file)] = data

beQuiet = False
def qprint(*args):
    """ Print as long as we're not expected to be quiet """
    if not beQuiet:
        print(*args)

def makeRegEx(values):
    checks = []
    for x in values:
        value = x.value
        if value is None:
            value=".*"
        regex = re.compile(value)
        checks.append((x.tag, regex))

    return checks

def checkTagRegEx(data, tag, regex):
    if current := data.get(tag):
        for value in current.values:
            if regex.match(str(value)):
                return True
    return False

def checkTagsRegEx(file, checks, andOp=True):
    if not checkFile(file):
        return False
    data = loadTags(file)
    if andOp:
        return all(map(lambda x: checkTagRegEx(data, x[0], x[1]), checks))
    else:
        return any(map(lambda x: checkTagRegEx(data, x[0], x[1]), checks))


def main():
    global beQuiet
    args = parseArgs()
    if args.quiet:
        beQuiet = True

    # If there's only one file, and it's a directory, list it
    if len(args.files) == 1 and args.files[0].is_dir():
        files = sorted(args.files[0].iterdir())
    else:
        files = args.files

    if args.print or not (args.tags or args.delete or args.clear or args.empty):
        # Printing files.   Compute the tags to print, then print 'em
        printtags = []
        if args.print:
            printtags = list(map(str.upper, flatten(args.print)))
        if args.value:
            checks = makeRegEx(flatten(args.value))
        else:
            checks = None
        for file in files:
            if not checks or checkTagsRegEx(file, checks, args.andOp):
                data = printTags(file, printtags, args.all, args.details, args.names, args.lists, args.save)
                if args.save and data:
                    saveTags(file, data, args.fullpath, args.relative)
    elif args.clear:
        # clear all the tags.
        for f in files:
            removeTags(f, args.preserve, args.dryrun)
    else:
        # Else we're setting tags.
        tags = makeTagValues(flatten(args.tags))
        delete = flatten(args.delete)
        for file in files:
            data = processFile(file, tags, delete, args.preserve, args.append, args.empty, args.dryrun, args.save)
            if args.save and data:
                saveTags(file, data, args.fullpath, args.relative)

        if args.stats:
            print(f"Files Processed: {stats['processed']} Files Changed: {stats['updated']} Tags added: {stats['added']} Tags changed: {stats['changed']} Tags deleted: {stats['deleted']}")

    if args.save:
        match args.format:
            case 'json':
                json.dump(savedData, args.save, indent=4)
            case 'yaml':
                args.save.write(yaml.dump(savedData, allow_unicode=True))
            case 'csv':
                writer = csv.DictWriter(args.save, fieldnames=['name'] + ALL_TAGS)
                writer.writeheader()
                for i in sorted(savedData.keys()):
                    row = savedData[i]
                    row['name'] = str(i)
                    writer.writerow(row)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        cprint("Interrupted", "red")
