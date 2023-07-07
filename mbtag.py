#! /usr/bin/env python3

import argparse
import pprint
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


@dataclass
class Track:
    tags: dict
    tag_file: music_tag.file
    name: Path

    def __init__(self, file):
        banner(f"Creating Track {file.filename.name}", color="yellow", subbanner=True)

        self.tag_file = file
        self.name = file.filename
        self.tags = dict(map(lambda x: (x, self.tag_file[x].values), filter(lambda x: not x.startswith("#"), self.tag_file.keys())))

@dataclass
class Disc:
    tags:dict
    tag_files: dict
    tracks = []

    def __init__(self, files: list):
        self.tag_files = dict(map(lambda x: (x.name, x), files))

@dataclass
class Album:
    tag_files: {}
    tags = {}
    discs = []
    tracks = []
    track_tags: dict

    def __init__(self, tag_files):
        banner("Creating Album")
        # First, build a dictionary of all the tags file objects
        self.tag_files = dict(map(lambda x: (x.filename.name, x), tag_files))
        banner("Tag Tracks", subbanner=True)
        # pprint.pprint(self.track_tags)

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
