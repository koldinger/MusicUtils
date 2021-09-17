#! /usr/bin/env python

import argparse
import logging
import json
import pathlib
import pprint

from pymediainfo import MediaInfo

class NotAudioException(Exception):
    pass

args = None
log = None

def initLogging():
    global log
    levels = [logging.WARN, logging.INFO, logging.DEBUG]
    level = min(args.verbose, len(levels))

    logging.basicConfig(level=levels[level])
    log = logging.getLogger("")

def parseArgs():
    parser = argparse.ArgumentParser("Generate a catalog of music files")
    parser.add_argument('--level', '-l', dest='level', choices=['artist', 'album', 'track'], default='track', help="Level of reporting")
    parser.add_argument('--fields', '-f', dest='fields', nargs='+', help='Fields to print',
                         choices=['title', 'artist', 'album', 'path', 'track', 'disk', 'length', 'size', 'genre', 'format'],
                         default=['artist', 'album', 'title', 'path'])
    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0, help="Increase verbosity.  May be repeated")
    #parser.add_argument('--test', '-t', metavar="(-100 to 100)", choices=range(-100, 100), help="Test")
    parser.add_argument('dirs', nargs="+", help='Base directories to catalog')
    args = parser.parse_args()
    return args

interestingTags = ['format', 'set', 'part_position', 'track_name_position', 'track_name', 'album', 'performer']



_maxlens = {}
def setMaxLen(name, value):
    _maxlens[name] = max(_maxlens.get(name, 0), len(value))

def getArtist(tags):
    artist = tags.get('performer', 'Unknown')
    albArtist = tags.get('album_performer', artist)
    #compilation = str(tag.get('compilation', 'No'))
    setMaxLen('artist', artist)
    setMaxLen('albartist', albArtist)

    return albArtist, artist

def getAlbum(tags):
    album =  tags.get('album', 'Unknown')
    setMaxLen('album', album)
    return album

def getTrackTitle(tags):
    title =  tags.get('title', 'Unknown')
    setMaxLen('title', title)
    return title

def getTags(f):
    info = MediaInfo.parse(f.absolute())
    if len(info.audio_tracks) > 0:
        tags = info.general_tracks[0].to_data()
        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"Info for {f}")
            interesting = dict(filter(lambda x: x[0] in interestingTags, tags.items()))
            log.debug(interesting)

        setMaxLen('format', tags.get('format', ''))
        return tags
    else:
        raise NotAudioException(f"{f} is not an audio type")

database = {}

_lastArtist = None
_lastAlbum  = None

def printTrackInfo(tag, f, fmt):
    artist = getArtist(tag)[1]
    album  = getAlbum(tag)
    title  = getTrackTitle(tag)
    frmt   = tag.get('format')
    length = tag.get('duration') / 1000

    length = f"{int(length / 60)}:{int(length % 60):02}"


    values = {"artist": artist, "album": album, "title": title, "path": f, "length": length, 'format': frmt}

    print(fmt.format(**values))


def makeFormatSpec():
    fmt = ""
    for i in args.fields:
        if fmt:
            fmt = fmt + " | "
        if i == 'path':
            fieldFmt = "{path}"
        elif i == 'length':
            fieldFmt = "{length:>6}"
        else:
            fieldFmt = f"{{{i}:{_maxlens.get(i, 20)}}}"
        fmt = fmt + fieldFmt
    print(fmt)
    return fmt

def printDatabase():
    fmt = makeFormatSpec()
    for artist in sorted(database.keys()):
        for album in sorted(database[artist].keys()):
            for track in sorted(database[artist][album].keys()):
                (f, t) = database[artist][album][track]
                printTrackInfo(t, f, fmt)

def processFile(f, base):
    try:
        tag = getTags(f)
        albArtist, artist = getArtist(tag)
        album = getAlbum(tag)
        title = getTrackTitle(tag)

        albums = database.setdefault(albArtist, {})
        tracks = albums.setdefault(album, {})
        tracks[title] = (f.relative_to(base), tag)
    except NotAudioException:
        log.warning(f"{f} is not an audio file")

def processDirTree(d, base):
    log.info(f"Processing {d}")
    dirs = []
    log.info(f"Processing directory {d}")
    if d.is_file():
        processFile(d, base)
    else:
        files = sorted(filter(lambda x: not x.name.startswith('.'), list(d.iterdir())))
        for f in files:
            if f.is_dir():
                dirs.append(f)
            else:
                processFile(f, base)

        for x in dirs:
            processDirTree(x, base)

def main():
    global args
    args = parseArgs()
    initLogging()
    print(args.fields)

    for d in args.dirs:
        dd = pathlib.Path(d)
        log.info(f"Starting {dd}")
        processDirTree(dd, dd)

    printDatabase()
    

if __name__ == "__main__":
    main()

