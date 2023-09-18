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
import pprint
import tempfile
import os
import sys
import json

from collections import Counter

import yaml
import music_tag
from termcolor import cprint, colored

from Utils import isAudio, addTuples

ALL_TAGS = list(filter(lambda x: not x.startswith('#') and not x.upper() == 'ARTWORK', music_tag.tags()))

def parseArgs():
    parser = argparse.ArgumentParser(description="Edit the tags in a collect of files")
    parser.add_argument("--replace", "-r", type=bool, action=argparse.BooleanOptionalAction, default=True,
                        help="Replace existing tags in destination")
    parser.add_argument("--delete", "-d", type=bool, action=argparse.BooleanOptionalAction, default=True,
                        help="Delete tags from destination that don't exist in source")
    parser.add_argument("--preserve", "-p", type=bool, action=argparse.BooleanOptionalAction, default=False,
                        help="Preserve timestamps")
    parser.add_argument("--save", "-s", type=argparse.FileType('w'), default=None, help="Save the generated tag data to a file")
    parser.add_argument("--load", "-l", type=argparse.FileType('r'), default=None, help="Load the generated tag data from a file")
    parser.add_argument("--edit", "-e", action=argparse.BooleanOptionalAction, default=True, help="Inoke an editor to edit the generated data")
    parser.add_argument("--format", "-f", type=str, choices=['json', 'yaml'], default='yaml', help="Format in which to save/load data")
    parser.add_argument("--promote", "-P", action=argparse.BooleanOptionalAction, default=True, help="Promote common elements to the album or disc level")
    parser.add_argument("--confirm", "-C", action=argparse.BooleanOptionalAction, default=True, help="Confirm writing of files")
    parser.add_argument("--dryrun", "-n", action=argparse.BooleanOptionalAction, default=False, help="Inoke an editor to edit the generated data")
    parser.add_argument("--editor", "-E", type=str, default=os.environ.get('EDITOR', 'nano'), help="Editor to use")
    parser.add_argument(type=pathlib.Path, nargs='+', dest='files', help='Files to change')

    return parser.parse_args()


def checkFile(file):
    try:
        if not (file.is_file() and isAudio(file)):
            #print(f"{colored('Error: ', 'red')} {file} isn't an audio file")
            return False
    except FileNotFoundError:
        print(f"{file} not found")
        return False
    return True


stats = Counter()

def doLoadFiles(files: list[pathlib.Path]):
    toLoad = [f for f in files if checkFile(f)]
    return list(map(music_tag.load_file, toLoad))

def loadFiles(files: list[pathlib.Path]):
    if len(files) == 1 and files[0].is_dir():
        return doLoadFiles(files[0].iterdir())
    return doLoadFiles(files)

def noList(value):
    if type(value) is list and len(value) == 1:
        return value[0]
    return value

def makeDict(tags):
    d = dict(map(lambda x: (x, noList(tags[x].values)),
                 [f for f in tags.keys() if f != 'artwork' and not f.startswith('#')]))
    return d

def consolidateTag(data, tag):
    values = Counter()
    for i in data:
        track = data[i]
        if tag in track:
            x = listToTuple(track[tag])

            values[x] += 1
    return values

def tupleToList(x):
    if isinstance(x, tuple):
        return list(x)
    return x

def listToTuple(x):
    if isinstance(x, list):
        return tuple(x)
    return x

def promoteTags(tags):
    consolidated = {}
    album = {}
    albumTags = {}
    numAlbums = len(tags)
    for tag in ALL_TAGS:
        consolidated = consolidateTag(tags, tag)
        # Check that there's only 1 tag
        if len(consolidated) == 1:
            item = consolidated.popitem()
            # And that it's in every file
            if item[1] == numAlbums:
                albumTags[tag] = tupleToList(item[0])
                for i in tags:
                    if tag in tags[i]:
                        del tags[i][tag]
    album['tracks'] = tags
    album['tags'] = albumTags

    return album

def demoteTags(album):
    tracks = album['tracks']
    tags = album['tags']
    for i in tracks:
        tracks[i] = tags | tracks[i]
    return tracks


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
            frValue = frTags.get(tag, None)
            if frValue and type(frValue) is not list:
                frValue = [frValue]

            # Get the "to" value
            # if the value is unparseable, just ignore it
            try:
                toValue = toTags[tag]
            except ValueError:
                toValue = None

            if frValue:
                if toValue:
                    #print(tag, "--", frValue, ":", toValue.values)
                    if tag == 'artwork':
                        # TODO: This should check all artwork, but I'm lazy, assuming only one in my library.
                        if frValue.first.data == toValue.first.data:
                            continue
                    elif set(frValue) == set(toValue.values):
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

def printSummary(file, details):
    cprint(f"Setting tags in {file.filename.name}", 'yellow')
    (added, replaced, deleted, errors) = details
    if added:
        tags = list(map(lambda x: x[0], added))
        print(f"{colored('Added', 'cyan'):17}: {pprint.pformat(tags, compact=True, width=132)}")
    if replaced:
        tags = list(map(lambda x: x[0], replaced))
        print(f"{colored('Replaced', 'cyan'):17}: {pprint.pformat(tags, compact=True, width=132)}")
    if deleted:
        tags = list(map(lambda x: x[0], deleted))
        print(f"{colored('Deleted', 'cyan'):17}: {pprint.pformat(tags, compact=True, width=132)}")
    #if not (added or deleted or replaced):
    #    cprint("Nothing changed", "cyan")


def setTags(newData, currentData, replace, delete):
    nChanged = 0
    results = []
    fChanged = []
    for file in currentData:
        details = ([], [], [], [])

        try:
            new = newData[file.filename.name]
            changed, stats = copyTags(new, file, ALL_TAGS, replace, delete, details=details)
            nChanged += changed
            if changed:
                fChanged.append(file.filename.name)
            results.append(stats)
            if changed:
                printSummary(file, details)
        except KeyError:
            print(f"Tags for {file.filename} not found.")
    if results:
        (added, replaced, deleted, errors) = addTuples(*results)
        print(f"Files Changed: {nChanged} Tags Added: {added} Tags Changed: {replaced} Tags Deleted: {deleted} Errors: {errors}")
    if fChanged:
        print(f"Changed: {sorted(fChanged)}")
    return fChanged

def saveTags(tags, file, format):
    match format:
        case 'json':
            json.dump(tags, file, indent=4)
        case 'yaml':
            file.write(yaml.dump(tags))

def loadTags(file, format):
    match format:
        case 'json':
            return json.load(file)
        case 'yaml':
            return yaml.load(file, yaml.SafeLoader)

def confirm(prompt, default='y'):
    while True:
        x = input(prompt).strip().lower()
        if not x:
            x = default.lower()
        if x in ['y', 'yes']:
            return True
        elif x in ['n', 'no']:
            return False

def main():
    global beQuiet
    args = parseArgs()

    fileData = list(loadFiles(args.files))

    if not fileData:
        cprint("No audio files found", "red")
        sys.exit(1)

    if args.load:
        origTags = loadTags(args.load, args.format)
    else:
        origTags = dict(map(lambda x: (x.filename.name, makeDict(x)), fileData))

    # If we're using the "promotion" feature, promote all and disc values
    if args.promote and len(origTags) > 1:
        origTags = promoteTags(origTags)

    with tempfile.NamedTemporaryFile("w+") as temp:
        temp.write(yaml.dump(origTags))
        temp.flush()
        loaded = False
        if args.edit:
            while loaded is False:
                os.system(f"{args.editor} {temp.name}")
                try:
                    temp.seek(0)
                    newTags = yaml.load(open(temp.name, "r"), yaml.SafeLoader)
                    #pprint.pprint(newTags)
                    loaded = True
                except yaml.YAMLError as y:
                    print(f"Error: {y}")
                    loaded = True  #
        else:
            newTags = origTags

        if args.save:
            saveTags(newTags, args.save, args.format)

        if args.promote and len(origTags) > 1:
            newTags = demoteTags(newTags)

        changedFiles = setTags(newTags, fileData, args.replace, args.delete)

        if not args.dryrun:
            if changedFiles:
                if not args.confirm or confirm("Write changes [Y/n]: "):
                    for i in fileData:
                        if not i.filename.name in changedFiles:
                            continue
                        times = i.filename.stat()
                        i.save()
                        if args.preserve:
                            os.utime(i.filename, times=(times.st_atime, times.st_mtime))
            else:
                cprint("No changes", "cyan")

        #pprint.pprint(newData, compact=True, width=132)

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        cprint("Interrupted", "red")
