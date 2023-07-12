#! /usr/bin/env python3

import argparse
import pprint
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import magic
import music_tag
import musicbrainzngs
from diskcache import Cache
from termcolor import cprint, colored

# Set your user agent (required by MusicBrainz API)
musicbrainzngs.set_useragent("AutoTag", "0.1")
ACOUSTID_KEY = "b'cL9ha5Xe"
cache = Cache(directory=Path("~/.local/cache/AutoTag").expanduser())



def banner(text, width=80, color="green", subbanner=False):
    hyphens = (width - len(text) - 2) / 2
    if not subbanner:
        cprint("-" * width, color)
    cprint(f"{'-' * int(hyphens)} {text} {'-' * round(hyphens)}", color)
    if not subbanner:
        cprint("-" * width, color)


def singletonTags(tags: dict):
    banner("Collecting singletons")
    singletons = {}
    for i in tags:
        if len(tags[i]) == 1:
            print(f"Singleton: {i} {next(iter(tags[i].keys()))}")
            singletons[i] = next(iter(tags[i].keys()))
    return singletons


def consolidate_tags(data: list):
    banner("Consolidate Tags")
    tags = defaultdict(lambda: defaultdict(list))
    for track in data.tracks:
        for tag in track.tags.keys():
             values = track.tags[tag]
             tags[tag][tuple(values)].append(track)
    return tags

def isAudio(file: Path):
    """
    Determine if a file is an audio file
    :param file: The path for the file to check
    :return: True if is audio, false otherwise
    """
    # use magic.from_buffer(read(2048)) rather than magic.from_file()   Is much faster for large files, like audio files
    if file.is_file() and magic.from_buffer(open(file, "rb").read(2048), mime=True).lower().startswith("audio/"):
        return True
    return False


def load_files(files):
    """
    Load the music_tag structures for each file
    :param files: List of files to parse.
    :return: A list of music_tag file objects
    """
    tags = []
    for file in files:
        if isAudio(file):
            print(f"Loading {file}")
            tags.append(music_tag.load_file(file))
    return tags


def process_args():
    parser = argparse.ArgumentParser("Test Musicbrainz stuff", add_help=True)
    parser.add_argument("--albumid", "-a", type=str, help="Album ID to process")
    parser.add_argument("files", nargs="+", type=Path, help="Files to process")
    return parser.parse_args()

@cache.memoize(expire=7200)
def getAlbumById(albumId: str):
    release = musicbrainzngs.get_release_by_id(albumId, includes=['recordings', 'artists', 'labels'])
    return release

@cache.memoize(expire=7200)
def getTrackById(trackId: str, releases=False):
    includes = ['artists']
    if releases:
        includes.append('releases')
    recording = musicbrainzngs.get_recording_by_id(trackId, includes=includes)
    return recording

def recordingToTrackTags(data: dict) -> dict:
    tags = {}
    for key, value in data.items():
        match key:
            case 'id':
                tag = 'musicbrainzrecordingid'
            case 'title':
                tag = 'tracktitle'
            case _:
                continue
        tags[tag] = value
    return tags


def trackToTrackTags(data: dict) -> dict:
    print(f"Track to Track Tags {data}")
    tags = {}
    for key, value in data.items():
        match key:
            case 'length':
                tag = '#length'
            case 'number':
                tag = 'tracknumber'
            case 'id':
                tag = 'musicbrainztrackid'
            case 'recording':
                tags.update(recordingToTrackTags(value))
                continue
            case _:
                continue
        tags[tag] = value
    print(tags)
    return tags


def mediaToDiscTags(data: dict) -> dict:
    tags = {}
    for key, value in data.items():
        match key:
            case 'format':
                tag = '#format'
            case 'position':
                tag = 'discnumber'
            case 'track-count':
                tag = 'totaltracks'
            case 'track-list':
                tag = '#tracks'
                value = list(map(trackToTrackTags, value))
            case _:
                continue
        tags[tag] = value
    return tags


def releaseToAlbumTags(release: dict) -> dict:
    tags = {}
    for key, value in release.items():
        match key:
            case 'id':
                tag = 'musicbrainzalbumid'
            case 'title':
                tag = 'albumtitle'
            case 'country':
                tag = '#country'
            case 'date':
                tag = 'year'
            case 'artist-credit-phrase':
                tag = 'artist'
            case 'medium-count':
                tag = 'totaldiscs'
            case 'medium-list':
                tag = '#discs'
                # print(type(value), type(value[0]))
                value = list(map(mediaToDiscTags, value))
            case _: continue
        tags[tag] = value
    return tags

class Tags:
    tags: dict
    tracks: list
    mbInfo: dict

    bannerColor = "green"

    def singletonTags(self, tags: dict):
        """
        Collect tags which are singletons, ie, there's a single value across all tracks
        :param tags: A dictionary, keyed on tag name, of dictionaries, keyed by tag value, of
            tracks.   eg:
                { "discnumber" : { (1, ): [Track1, Track2],
                                   (2, ): [Track3]
                                 }
                }
        :return: a list of tag names that only have a single value
        """
        banner("Collecting singletons", color=self.bannerColor)
        singletons = {}
        for i in tags:
            if len(tags[i]) == 1:
                print(f"Singleton: {i} {next(iter(tags[i].keys()))}")
                singletons[i] = next(iter(tags[i].keys()))
        return singletons


    def consolidate_tags(self):
        banner("Consolidate Tags", color=self.bannerColor)
        tags = defaultdict(lambda: defaultdict(list))
        for track in self.tracks:
            for tag in track.tags.keys():
                 values = track.tags[tag]
                 tags[tag][tuple(values)].append(track)
        return tags


@dataclass
class Track:
    tag_file: music_tag.file
    name: Path
    bannerColor = "blue"

    def __init__(self, file):
        super().__init__()
        banner(f"Creating Track {file.filename.name}", color="yellow", subbanner=True)

        self.tag_file = file
        self.name = file.filename
        self.tags = dict(map(lambda x: (x, self.tag_file[x].values), filter(lambda x: not x.startswith("#"), self.tag_file.keys())))

    def deduceInfo(self):
        print(self.name, type(self.name))
        fName = self.name.stem
        dName = self.name.parent.name
        aName = self.name.parent.parent.name

        dName = re.sub('_', ' ', dName)
        aName = re.sub('_', ' ', aName)
        if m := re.match(r"^(\d+)-(\d+)\.(\w+)$", fName):
            print(m)
            disc = int(m.group(1))
            track = int(m.group(2))
            fName = m.group(3)
        elif m := re.match(r"^(\d+)\.(\w+)$", fName):
            disc = None
            track = int(m.group(1))
            fName = m.group(2)
            fName = re.sub('_', ' ', fName)

        return(aName, dName, fName)


@dataclass
class Disc(Tags):
    track_tags: dict
    def __init__(self, files: list):
        super().__init__()
        self.tag_files = dict(map(lambda x: (x.name, x), files))

@dataclass
class Album(Tags):
    discs = list()
    track_tags = dict()
    tracks = list()

    def __init__(self, tag_files):
        #super().__init__(tag_files)
        banner("Creating Album")
        # First, build a dictionary of all the tags file objects
        self.tag_files = dict(map(lambda x: (x.filename.name, x), tag_files))
        banner("Tag Tracks", subbanner=True)
        # pprint.pprint(self.track_tags)

        self.tracks = []
        for track in tag_files:
            self.tracks.append(Track(track))
        #banner("PerTrack Info")
        # pprint.pprint(self.tracks)

    def getTrack(self, name):
        for i in self.tracks:
            if i.name == name:
                return i
        return None


def removeTags(tags, items):
    banner("Removing tags")
    print(tags)
    for i in tags:
        for j in items:
            del j.tags[i]


def build_album(current_tags):
    album = Album(current_tags)

    consAlb = consolidate_tags(album)
    album.tags = singletonTags(consAlb)
    removeTags(album.tags.keys(), album.tracks)

    if 'discnumber' in consAlb:
        for i in consAlb['discnumber']:
            disc = Disc(consAlb['discnumber'][i])
            tracks = list(map(lambda x: album.getTrack(x.name), consAlb['discnumber'][i]))
            album.discs.append(disc)
            disc.tracks = tracks
            consDisc = consolidate_tags(disc)
            disc.tags = singletonTags(consDisc)
            removeTags(disc.tags.keys(), disc.tracks)

    # pprint.pprint(album.discs)
    return album


def main():
    args = process_args()
    # print(args.files)
    current_tags = load_files(args.files)
    print(f"Loaded {len(current_tags)} files")
    album = build_album(current_tags)
    banner("Album Data", color="cyan")
    pprint.pprint(album.tags)

    banner("Full Album Structure:", color="yellow")
    pprint.pprint(album.tracks)
    if album.discs:
        for disc in album.discs:
            banner("Disc Data", color="cyan")
            pprint.pprint(disc.tags)
            for track in disc.tracks:
                banner(track.name.name, color="blue", subbanner=True)
                pprint.pprint(track.tags, compact=True)
    else:
        for i in album.tracks:
            banner(i.name.name, color="blue", subbanner=True)
            pprint.pprint(i.tags, compact=True)


if __name__ == "__main__":
    main()
