#! /usr/bin/env python

import argparse
import sys
import logging
import re
import pprint
import operator
from pathlib import Path
from collections import Counter, namedtuple
from dataclasses import dataclass

import colorlog
import music_tag
import magic
import diskcache
import musicbrainzngs
import acoustid
from termcolor import cprint, colored

# from pymediainfo import MediaInfo

logger = None
args = None

ACOUSTID_KEY = "b'cL9ha5Xe"

# Set your user agent (required by MusicBrainz API)
musicbrainzngs.set_useragent("AutoTag", "0.1")

cache = diskcache.Cache(directory=Path("~/.local/cache/AutoTag").expanduser())

CACHE_TTL=7200

@dataclass
class Track:
    file: Path
    tags: music_tag.file.AudioFile

    mb_albumid = None
    mb_trackid = None

    def __init__(self, file: Path):
        logger.info(f"Creating a track from {file}")
        self.file = file
        try:
            self.tags = music_tag.load_file(file)
            if self.tags:
                
        except Exception as e:
            logger.error(f"Caught Exception {e} loading {file}")
            pass

@dataclass
class Album:
    tracks: list[Track]


class NotAudioException(Exception):
    pass


class TaggerMBID:
    pass


@cache.memoize(expire=CACHE_TTL, tag="fingerprint")
def scan_file(file):
    cprint(f"Scanning {file}", "yellow")
    return acoustid.fingerprint_file(file)


@cache.memoize(expire=CACHE_TTL, tag="acoustid")
def acoustid_match(dur, fingerprint):
    cprint(f"Looking up ID", "yellow")
    return acoustid.lookup(ACOUSTID_KEY, fingerprint, dur)


@cache.memoize(expire=CACHE_TTL, tag="acoustid")
def acoustid_match_file(path):
    cprint(f"Matching File {path}", "yellow")
    return list(acoustid.match(ACOUSTID_KEY, path))


@cache.memoize(expire=CACHE_TTL, tag='search')
def search_recordings(artist_name, album_title):
    return musicbrainzngs.search_releases(artist=artist_name, release=album_title)


@cache.memoize(expire=CACHE_TTL, tag='recording')
def get_recording_by_id(recId):
    info = musicbrainzngs.get_recording_by_id(recId, includes=['releases', 'artists'])
    return info


@cache.memoize(expire=CACHE_TTL, tag='release')
def get_release_by_id(relId):
    info = musicbrainzngs.get_release_by_id(relId, includes=['recordings', 'artists', 'labels', 'release-groups'])
    return info

def processArgs():
    _def = ' (default: %(default)s)'

    parser = argparse.ArgumentParser(description="Reorganize music files", add_help=True)

    parser.add_argument('--dry-run', '-n', dest='test', default=False, action=argparse.BooleanOptionalAction,
                        help='Rename files.  If false, only')
    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0,
                        help='Increase the verbosity')
    parser.add_argument('files', nargs='*', default=[Path('.')], type=Path,
                        help='List of files/directories to reorganize')

    args = parser.parse_args()
    return args


def consolidateTags(data, *tags):
    values = Counter()
    for i in data:
        track = data[i]
        tagValues = []
        for j in tags:
            if track[j]:
                tagValues.append(track[j].value)

        if tagValues:
            if len(tags) > 1:
                v = tuple(tagValues)
            else:
                v = tagValues[0]
            values[v] += 1

    return values


def initLogging():
    handler = colorlog.StreamHandler()
    colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'red,bg_white',
    }
    # formatter = colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(name)s:%(message)s', log_colors=colors)
    formatter = colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(reset)s %(message)s', log_colors=colors)
    handler.setFormatter(formatter)

    levels = [logging.WARN, logging.INFO, logging.DEBUG] #, logging.TRACE]
    level = levels[min(len(levels)-1, args.verbose)]  # capped to number of levels

    logger = colorlog.getLogger('reorg')
    logger.addHandler(handler)
    logger.setLevel(level)

    return logger


def isAudio(file):
    return magic.from_buffer(open(file, "rb").read(2048), mime=True).lower().startswith("audio")


def buildTracks(files):
    tracks = []
    for file in files:
        if not isAudio(file):
            continue
        try:
            tracks.append(Track(file))
        except Exception as e:
            logger.error(f"Caught exception loading {file}: {e}")


def processFiles(files):
    logger.info(f"Processing {len(files)} files")
    tracks = buildTracks(files)

    #albumIds = consolidateTags(allTags, 'musicbrainzalbumid')
    #trackIds = consolidateTags(allTags, 'musicbrainztrackid')
    #albumInfo = consolidateTags(allTags, 'artist', 'album')
    #albumNames = consolidateTags(allTags, 'album')
    #trackNames = consolidateTags(allTags, 'tracknumber', 'tracktitle')


def processDir(d):
    logger.info(f"Processing directory {d}")
    dirs = [f for f in d.iterdir() if f.is_dir()]
    files = [f for f in d.iterdir() if f.is_file() and isAudio(f)]

    if files:
        processFiles(files)
    if dirs:
        for subdir in dirs:
            processDir(subdir)


def main():
    global args, logger
    print("main")
    args = processArgs()
    logger = initLogging()

    files = [f for f in args.files if f.is_file()]
    dirs =  [f for f in args.files if f.is_dir()]

    print(files)
    print(dirs)

    if files:
        processFiles(files)
    if dirs:
        for d in dirs:
            processDir(d)
    return 0


if __name__ == "__main__":
    retCode = main()

    sys.exit(retCode)
