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
import json
import time

from collections import Counter

import magic
import yaml
import music_tag
from termcolor import cprint, colored

from Utils import isAudio, addTuples

# FIXME: These should be extract from music_tag
# VALID_TAGS = sorted([
#    "ACOUSTIDFINGERPRINT", "ACOUSTIDID", "ALBUM", "ALBUMARTIST", "ALBUMARTISTSORT", "ALBUMSORT", "ARTIST", "ARTISTSORT", "ARTWORK",
#    "COMMENT", "COMPILATION", "COMPOSER", "COMPOSERSORT", "DISCNUMBER", "DISCSUBTITLE", "GENRE", "ISRC", "KEY", "LYRICS", "MEDIA",
#    "MOVEMENT", "MOVEMENTNUMBER", "MOVEMENTTOTAL", "MUSICBRAINZALBUMARTISTID", "MUSICBRAINZALBUMID", "MUSICBRAINZARTISTID",
#    "MUSICBRAINZDISCID", "MUSICBRAINZORIGINALALBUMID", "MUSICBRAINZORIGINALARTISTID", "MUSICBRAINZRECORDINGID", "MUSICBRAINZRELEASEGROUPID",
#    "MUSICBRAINZTRACKID", "MUSICBRAINZWORKID", "MUSICIPFINGERPRINT", "MUSICIPPUID", "SUBTITLE", "TITLESORT", "TOTALDISCS",
#    "TOTALTRACKS", "TRACKNUMBER", "TRACKTITLE", "WORK", "YEAR" ])

VALID_TAGS = sorted([i for i in map(str.upper, music_tag.tags()) if not i.startswith('#')])


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
    parser.add_argument("--promote", "-P", action=argparse.BooleanOptionalAction, default=False, help="Promote common elements to the album or disc level")
    parser.add_argument("--dryrun", "-n", action=argparse.BooleanOptionalAction, default=False, help="Inoke an editor to edit the generated data")
    parser.add_argument("--editor", "-E", type=str, default=os.environ.get('EDITOR', 'nano'), help="Editor to use")
    parser.add_argument(type=pathlib.Path, nargs='+', dest='files', help='Files to change')

    return parser.parse_args()


def checkFile(file):
    print(file)
    try:
        if not isAudio(file):
            print(f"{colored('Error: ', 'red')} {file} isn't an audio file")
            return False
    except FileNotFoundError:
        print(f"{file} not found")
        return False
    return True


stats = Counter()


def doLoadFiles(files: list[pathlib.Path]):
    #print(files)
    toLoad = [f for f in files if checkFile(f)]
    #print(toCheck)
    return map(music_tag.load_file, toLoad)


def loadFiles(files: list[pathlib.Path]):
    if len(files) == 1 and files[0].is_dir():
        return doLoadFiles(list(files[0].iterdir))
    else:
        return doLoadFiles(files)

def noList(value):
    if type(value) is list and len(value) == 1:
        return value[0]
    else:
        return value


def makeDict(tags):
    d = dict(map(lambda x: (x, noList(tags[x].values)),
                    [f for f in tags.keys() if f != 'artwork' and not f.startswith('#')]))
    return d

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
                    elif frValue == toValue.values:
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

def printSummary(details):
    (added, replaced, deleted, errorrs) = details
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
def doCopy(newData, currentData, replace, delete):
    allTags = filter(lambda x: not x.startswith('#') and not x.upper() == 'ARTWORK', music_tag.tags())
    nChanged = 0
    results = []
    for file in currentData:
        details = ([], [], [], [])

        print(f"Copying tags to {file.filename.name}")
        pprint.pprint(newData)
        try:
            new = newData[file.filename.name]
            changed, stats = copyTags(new, file, allTags, replace, delete, details=details)
            nChanged += changed
            results.append(stats)
            printSummary(details)
        except KeyError as e:
            print(f"Tags for {file.filename} not found.")
    summary = addTuples(*results)
    print(summary)


def main():
    global beQuiet
    args = parseArgs()

    currentData = list(loadFiles(args.files))
    if args.load:
        allData = yaml.load(args.load.read(), yaml.SafeLoader)
    allData = dict(map(lambda x: (x.filename.name, makeDict(x)), currentData))
    with tempfile.NamedTemporaryFile("w+") as temp:
        temp.write(yaml.dump(allData))
        temp.flush()
        loaded = False
        if args.edit:
            while loaded is False:
                os.system(f"{args.editor} {temp.name}")
                try:
                    temp.seek(0)
                    newData = yaml.load(open(temp.name, "r"), yaml.SafeLoader)
                    pprint.pprint(newData)
                    loaded = True
                except yaml.YAMLError as y:
                    print(f"Error: {y}")
                    loaded = True  #
        else:
            newData = allData
        doCopy(newData, currentData, args.replace, args.delete)
        if not args.dryrun:
            for i in currentData:
                i.save()
        if args.save:
            if args.format == 'json':
                json.dump(newData, args.save, indent=4)
            else:
                args.save.write(yaml.dump(newData))
        #pprint.pprint(newData, compact=True, width=132)

if __name__ == '__main__':
    main()
