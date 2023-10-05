#! /usr/bin/env python

import argparse
import logging
import json
import csv
import pathlib
import pprint
import unicodedata
import os.path
import itertools

from pymediainfo import MediaInfo

class NotAudioException(Exception):
    pass

args = None
log = None

allfields = ['artist', 'albumartist', 'album', 'path', 'track', 'disk', 'duration', 'size', 'genre', 'format', 'disks', 'tracks', 'albums', 'title' ] 
trackfields = ['artist', 'albumartist', 'album', 'path', 'track', 'disk', 'duration', 'size', 'genre', 'format', 'title', 'isize', 'fullpath' ] 

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
                         choices=allfields, default=['albumartist', 'album', 'track', 'title', 'path'])
    parser.add_argument('--fullpath', '-F', dest='fullpath', default=False, action='store_true', help='Print full paths for files')
    parser.add_argument('--base', '-b', dest='base', default=None, help='Use as base for relative paths')
    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0, help="Increase verbosity.  May be repeated")
    #parser.add_argument('--test', '-t', metavar="(-100 to 100)", choices=range(-100, 100), help="Test")
    parser.add_argument('--save', '-S', dest='save', help='Save the database to a CSV file')
    parser.add_argument('--load', '-L', dest='load', help='Preload the database from a CSV file before parsing other files')
    parser.add_argument('dirs', nargs="*", type=pathlib.Path, help='Base directories to catalog')
    args = parser.parse_args()
    return args

interestingTags = ['format', 'set', 'part_position', 'track_name_position', 'track_name', 'album', 'performer']

_maxlens = {}
def setMaxLen(name, value):
    _maxlens[name] = min(max(_maxlens.get(name, 0), len(value)), 80)

def noSlash(tag):
    if tag.find('/') != -1:
        tag = tag[0:tag.find('/')]
    return tag

def clean(string):
    return unicodedata.normalize('NFKC', string).strip()

def getArtist(tags):
    if 'artist' in tags:
        artist = tags.get('artist')
    elif 'artists' in tags:
        artist = tags.get('artists')
    else:
        artist = tags.get('performer', 'Unknown')
    albArtist = clean(tags.get('album_performer', artist))
    #compilation = str(tag.get('compilation', 'No'))
    setMaxLen('artist', artist)
    setMaxLen('albumartist', albArtist)

    return albArtist, artist

def getAlbum(tags):
    album =  clean(tags.get('album', 'Unknown'))
    setMaxLen('album', album)
    return album

def getTrackTitle(tags):
    title =  clean(tags.get('title', 'Unknown'))
    setMaxLen('title', title)
    return title

def getTrackNumber(tags):
    if 'track_name_position' in tags:
        track = noSlash(str(tags['track_name_position']))
    elif 'track' in tags:
        track = noSlash(str(tags['track']))
    else:
        track = '0'
    return track

def getDiskNumber(tags):
    if 'part_position' in tags:
        diskno = str(tags.get('part_position'))
    elif 'set' in tags:
        diskno = noSlash(str(tags.get('set')))
    elif 'part' in tags:
        diskno = noSlash(str(tags.get('part')))
    else:
        diskno = ""
    return diskno

def getSize(tag):
    return tag['file_size'], tag['other_file_size'][0]

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
processed = {}

_lastArtist = None
_lastAlbum  = None

def printTrackInfo(values, fmt):
    print(fmt.format(**values))

def makeFormatSpec():
    fmt = ""
    for i in args.fields:
        if fmt:
            fmt = fmt + " | "
        if i == 'path':
            fieldFmt = "{path}"
        elif i == 'duration':
            fieldFmt = "{duration:>8}"
        elif i == 'disk' or i == 'track':
            fieldFmt = f"{{{i}:>5}}"
        else:
            fieldFmt = f"{{{i}:{_maxlens.get(i, 20)}}}"
        fmt = fmt + fieldFmt
    #print(fmt)
    return fmt

def makeHeaderLines(fmt):
    values = {}
    for i in args.fields:
        values[i] = i.title()
    header = fmt.format(**values)
    return header

def printAlbumInfo(artist, album, tracks, fmt):
    (disks, tracks, duration, size, genres) = getAlbumStats(tracks)
    duration = milliToTime(duration)
    size = fmtSize(size, 1024, ['', 'KiB', 'MiB', 'GiB', 'TB', 'PB'])
    values = {"artist": artist, "albumartist": artist, "album": album, "title": '', "path": '', "duration": duration, 'format': '', 'genre': '', 'track': '', 'tracks': tracks, 'disks': disks, 'albums': '', 'size': size}
    #print(genres)
    printTrackInfo(values, fmt)


def summarize(a):
    log.debug(f"{type(a[0])}, {a}")
    if isinstance(a[0], list):
        return set(itertools.chain(*a))
    else:
        return sum(a)

def printArtistInfo(artist, albums, fmt):
    albumInfo = [getAlbumStats(albums[x]) for x in albums]
    (disks, tracks, duration, size, genres) = tuple(map(summarize, zip(*albumInfo)))
    albums = len(albumInfo)
    duration = milliToTime(duration)
    genres = ",".join(genres)
    size = fmtSize(size, 1024, ['', 'KiB', 'MiB', 'GiB', 'TB', 'PB'])
    values = {"artist": artist, "albumartist": artist, "album": str(albums), "title": '', "path": '', "duration": duration, 'format': '', 'genre': '', 'track': '', 'disk': '', 'tracks': tracks, 'disks': disks, 'albums': albums, 'size': size, "genre": genres}
    printTrackInfo(values, fmt)

def printDatabase():
    fmt = makeFormatSpec()
    header = makeHeaderLines(fmt)
    print(header)
    for artist in sorted(database.keys()):
        albums = database[artist]
        if args.level == 'artist':
            printArtistInfo(artist, albums, fmt)
        else:
            for album in sorted(albums.keys()):
                tracks = albums[album]
                print(tracks)
                if args.level == 'album':
                    printAlbumInfo(artist, album, tracks, fmt)
                else:
                    for track in sorted(tracks):
                        t = tracks[track].copy()
                        t['duration'] = milliToTime(t['duration'])
                        printTrackInfo(t, fmt)

def milliToTime(length):
    length = int(length) / 1000
    length = f"{int(length / 60)}:{int(length % 60):02}"
    return length

def fmtSize(num, base=1024, formats = ['bytes','KB','MB','GB', 'TB', 'PB']):
    fmt = "%d %s"
    if num is None:
        return 'None'
    num = float(num)
    for x in formats:
        #if num < base and num > -base:
        if -base < num < base:
            return (fmt % (num, x)).strip()
        num /= float(base)
        fmt = "%3.1f %s"
    return (fmt % (num, 'EB')).strip()

def makeInfo(tag, f, base):
    #choices=['title', 'artist', 'albumartist', 'album', 'path', 'track', 'disk', 'duration', 'size', 'genre', 'format'],
    albartist, artist = getArtist(tag)
    album  = getAlbum(tag)
    title  = getTrackTitle(tag)
    frmt   = tag.get('format')
    duration = int(tag.get('duration', 0))
    genre  = tag.get('genre', 'Unknown')
    track  = getTrackNumber(tag)
    disk   = getDiskNumber(tag)
    isize, size = getSize(tag)

    fullpath = f.absolute()
    path = str(fullpath) if args.fullpath else str(f.absolute().relative_to(base))

    values = {"artist": artist, "albumartist": albartist, "album": album, "title": title, "path": path, "duration": duration, 'format': frmt, 'genre': genre, 'track': track, 'disk': disk, 'size': size, 'isize': isize, 'fullpath': fullpath, 'albumdpath': fullpath.parent}
    return values

def getAlbumStats(album):
    tracks = len(album)
    disks = len({album[x]['disk'] for x in album})
    duration = sum([album[x]['duration'] for x in album])
    size = sum([album[x]['isize'] for x in album])
    genres = list({album[x]['genre'] for x in album})
    #print(disks, tracks, duration)
    return (disks, tracks, duration, size, genres)

def processFile(f, base):
    try:
        path = f.absolute()
        if not processed.get(path, False):
            tag = getTags(f)
            info = makeInfo(tag, f, base)

            albums = database.setdefault(info['albumartist'], {})
            tracks = albums.setdefault(info['album'], {})
            tracks[(info['disk'].zfill(2), info['track'].zfill(2))] = info
            processed[path] = True
        else:
            log.info(f"Skipping {f}")
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

def loadDB(base):
    if args.load:
        with open(args.load) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Clean up some data
                track = int(row['track'])
                disk = int(row['disk']) if row['disk'] else 0
                row['path'] = row['fullpath'] if args.fullpath else pathlib.Path(row['fullpath']).absolute().relative_to(base)
                row['duration'] = int(row['duration'])
                row['isize'] = int(row['isize'])

                database.setdefault(row['artist'], {}).setdefault(row['album'], {})[(disk, track)] = row

                setMaxLen('artist', row['artist'])
                setMaxLen('albumartist', row['albumartist'])
                setMaxLen('album', row['album'])
                setMaxLen('title', row['title'])
                processed[pathlib.Path(row['fullpath'])] = True

def saveDB():
    if args.save:
        with open(args.save, "w") as f:
            writer = csv.DictWriter(f, fieldnames=trackfields, extrasaction='ignore')
            writer.writeheader()
            for artist in database:
                for album in database[artist]:
                    for track in database[artist][album]:
                        #pprint.pprint(database[artist][album][track], width=132, compact=True)
                        writer.writerow(database[artist][album][track])


def main():
    global args, database
    args = parseArgs()
    initLogging()
    #print(args.fields)

    #dirs = [pathlib.Path(x) for x in args.dirs]
    dirs = args.dirs
    if args.base:
        base = pathlib.Path(args.base)
        if not base.is_dir():
            raise Exception(f"{base} is not a directory")
    else:
        if len(dirs):
            base = pathlib.Path(os.path.commonpath([x.absolute() for x in dirs]))
        else:
            base = pathlib.Path("/")

    loadDB(base)
    log.warning(f"Loaded {len(processed)} entries")

    for d in dirs:
        log.info(f"Starting {d}")
        processDirTree(d, base)
    log.warning(f"Processed {len(processed)} entries")

    printDatabase()
    saveDB()
    

if __name__ == "__main__":
    main()

