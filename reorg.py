#! /usr/bin/env python

import argparse
import os.path
import sys
import logging
import pprint
import pathlib
import re
import unicodedata
import shutil
import operator
import functools

import colorlog
import unidecode
from pymediainfo import MediaInfo

class NotAudioException(Exception):
    pass

ACTION_LINK=1
ACTION_MOVE=2
ACTION_COPY=3
ACTION_SYMLINK=4

def processArgs():
    _def = ' (default: %(default)s)'

    parser = argparse.ArgumentParser(description="Reorganize music files", add_help=True)

    parser.add_argument('--base', '-b', dest='base', default='.',                                                   help='Base destination directory' + _def)
    parser.add_argument('--split', '-s', dest='split', default=False, action=argparse.BooleanOptionalAction,        help='Split by type' + _def)
    parser.add_argument('--typebase', '-B', dest='bases', default=[], nargs='*',                                    help='Bases for each type.   Ex: flac=/music/flac mp3=/music/mp3')

    action = parser.add_mutually_exclusive_group()
    action.add_argument('--move', dest='action', action='store_const', default=ACTION_MOVE, const=ACTION_MOVE,      help='Move (rename) the files')
    action.add_argument('--link', dest='action', action='store_const', const=ACTION_LINK,                           help='Hard link the files')
    action.add_argument('--copy', dest='action', action='store_const', const=ACTION_COPY,                           help='Copy the files')
    action.add_argument('--slink', dest='action', action='store_const', const=ACTION_SYMLINK,                       help='Symbolic link the files')

    parser.add_argument('--dry-run', '-n', dest='test', default=False, action=argparse.BooleanOptionalAction,       help='Rename files.  If false, only')
    parser.add_argument('--drag', '-d', dest='drag', nargs='*', default=['cover.jpg'],                              help='List of files to copy along with the music files' + _def)

    parser.add_argument('--ascii', '-A', dest='ascii', default=False, action=argparse.BooleanOptionalAction,        help='Convert to ASCII characters')
    parser.add_argument('--normalize', '-N', dest='normalize', default=True, action=argparse.BooleanOptionalAction, help='Normalize Unicode Strings')
    parser.add_argument('--inplace', '-i', dest='inplace', default=False, action=argparse.BooleanOptionalAction,    help='Rename files inplace')
    parser.add_argument('--albartist', '-a', dest='albartist', default=True, action=argparse.BooleanOptionalAction, help='Use album artist for default directory if available' + _def)
    parser.add_argument('--various', '-V', dest='various', default="VariousArtists",                                help='"Artist" name for various artists collections' + _def)
    parser.add_argument('--the', '-T', dest='useArticle', default=True, action=argparse.BooleanOptionalAction,      help='Use articles')
    parser.add_argument('--classical', '-C', dest='classical', default=False, action=argparse.BooleanOptionalAction,    help='Use classical naming if the genre starts with this')
    parser.add_argument('--length', dest='maxlength', default=75, type=int,                                         help='Maximum length of file names' + _def)
    parser.add_argument('--clean', '-c', dest='cleanup', default=False,                                             help='Cleanup empty directories and dragged files when done' + _def)

    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0,                               help='Increase the verbosity')

    parser.add_argument('files', nargs='+', default=['.'], help='List of files/directories to reorganize')

    args = parser.parse_args()
    return args

def munge(name):
    if args.normalize:
        name = unicodedata.normalize('NFKC', name)
    if args.ascii:
        name = unidecode.unidecode(name)
    name = re.sub('[/&\.\[\]\$\"\'\?\(\)\<\>\!\:\;\~]', '', name)
    name = re.sub('\s', '_', name)
    name = re.sub('_+', '_', name)
    if not args.useArticle:
        name = re.sub("^(The|A|An)\s+", "", name)
    name = name.strip('_')
    return name


def noSlash(tag):
    if tag.find('/') != -1:
        tag = tag[0:tag.find('/')]
    return tag

def makeFName(f, tags):
    name = ""
    diskno = None
    if 'part_position' in tags:
        diskno = str(tags.get('part_position'))
    elif 'set' in tags:
        diskno = str(tags.get('set'))
    elif 'part' in tags:
        diskno = str(tags.get('part'))

    title = tags.get('title')
    title = title if title else tags.get('track_name', 'Unknown')
    if 'title__more' in tags:
        title = title + " " + tags.get('title__more')
    elif 'track_name__more' in tags:
        title = title + " " + tags.get('track_name__more')
    #elif 'part' in tags:
    #    title = title + " " + str(tags.get('part'))

    if 'track_name_position' in tags:
        track = noSlash(str(tags['track_name_position']))
    elif 'track' in tags:
        track = noSlash(str(tags['track']))
    else:
        track = '0'


    if diskno:
        trk = "{0}-{1}".format(noSlash(diskno), track.zfill(2))
    else:
        trk = noSlash(track).zfill(2) 

    #name = name + '.' + tags.get('track_name')

    # Don't take the suffix length into account, confuses things when suffixes are different lengths
    # .flac vs .mp3 for instance.
    m = max(args.maxlength - len(trk), 5)

    name = "{0}.{1}{2}".format(trk, munge(title)[0:m].strip(), f.suffix)
    log.debug(f"Name {f.name} -> {name}")
    return name

def makeComposerString(composers):
    # Make a unique list of composers.
    unique = list(map(munge, list(dict.fromkeys(composers))))

    string = ",_&_".join(unique[0:2])
    if len(unique) > 2:
        string += '_et_al'

    return string

def getArtist(tags):
    if 'artist' in tags:
        artist = tags.get('artist')
    elif 'artists' in tags:
        artist = tags.get('artists')
    else:
        artist = tags.get('performer', 'Unknown')
    log.debug(f"Retrieved artist: {artist}")
    return artist

def makeDName(f, tags, dirname=None):
    if args.inplace:
        base = f.parent
    else:
        base = pathlib.Path(bases.get(tags['format'], args.base))

        if dirname is None:
            compilation = str(tags.get('compilation', 'No')).lower()
            if compilation in ['yes', '1', 'true']:
                dirname = args.various
            elif args.albartist and tags.get('album_performer'):
                dirname = tags.get('album_performer')
            else:
                dirname = getArtist(tags)

        base = base.joinpath(munge(dirname), munge(tags.get('album', 'Unknown')))

    log.debug(f"Dir: {f.parent} -> {base}")
    return base

interestingTags = ['format', 'set', 'part_position', 'track_name_position', 'track_name', 'album', 'performer']
def getTags(f):
    info = MediaInfo.parse(f.absolute())
    if len(info.audio_tracks) > 0:
        tags = info.general_tracks[0].to_data()
        if args.verbose > 3:
            log.debug(f"Info for {f}")
            interesting = dict(filter(lambda x: x[0] in interestingTags, tags.items()))
            log.debug(interesting)

        return tags
    else:
        raise NotAudioException(f"{f} is not an audio type")

def makeName(f, tags, dirname = None):
    dirname = makeDName(f, tags, dirname)

    newFile = dirname.joinpath(makeFName(f, tags))
    
    log.debug(f"FullName {f} -> {newFile}")
    return newFile

def dragFiles(dragfiles, destdir):
    action = actionName()
    for f in dragfiles:
        dest = destdir.joinpath(f.name)
        if f.exists() and not dest.exists():
            log.info(f"{action} {f}\t==>  {dest}")
            doMove(f, dest)

def doMove(src, dest):
    if not args.test:
        if not dest.parent.exists():
            log.debug(f"Creating {dest.parent}")
            dest.parent.mkdir(parents=True, exist_ok=True)
        elif not dest.parent.is_dir():
            #log.warning(f"{dest.parent} exists, and is not a directory")
            raise Exception("{dest.parent} exists, and is not a directory")

        if args.action == ACTION_LINK:
            dest.hardlink_to(src)
        elif args.action == ACTION_SYMLINK:
            dest.symlink_to(src)
        elif args.action == ACTION_MOVE:
            src.rename(dest)
        elif args.cation == ACTION_COPY:
            shutil.copy2(src, dest)
        else:
            raise Exception("Unknown action: %s", args.action)


def actionName():
    if args.action == ACTION_LINK:
        name = "Linking"
    elif args.action == ACTION_MOVE:
        name = "Moving"
    elif args.cation == ACTION_COPY:
        name = "Copying"
    elif args.action == ACTION_SYMLINK:
        name = "SymLinking"
    if args.test:
        name = "[-] " + name
    return name


def renameFile(f, tags, dragfiles=[], dirname=None):
    action = actionName()
    dest = makeName(f, tags, dirname)
    try:
        if dest.exists():
            if not f.samefile(dest):
                log.warning(f"{dest} exists, skipping ({f})")
            return
        log.info(f"{action} {f}\t==>  {dest}")

        doMove(f, dest)
        dragFiles(dragfiles, dest.parent)

    except NotAudioException as e:
        log.warning(e)
    except FileExistsError as e:
        log.warning(f"Destination file {f} exists.  Cannot move")
    except Exception as e:
        log.warning(f"Caught exception {e} processing {f.name}")
        log.exception(e)

def isDraggable(f):
    for pat in args.drag:
        if f.match(pat):
            return True
    return False

def reorgDir(d):
    try:
        log.info(f"Processing Directory {d}")
        dirs = []
        audio = []
        composers = []
        dragfiles = []
        files = sorted(filter(lambda x: not x.name.startswith('.'), list(d.iterdir())))

        composerStr = None

        for f in files:
            try:
                log.debug(f"Checking {f}")
                if f.is_dir():
                    dirs.append(f)
                elif f.is_file():
                    if isDraggable(f):
                        dragfiles.append(f)
                    else:
                        tags = getTags(f)
                        audio.append((f, tags))
                        if args.classical and tags.get('composer'):
                            composers.append(tags.get('composer'))
            except NotAudioException as e:
                log.warning(e)
            except Exception as e:
                log.warning(f"Caught exception processing {name}: {e}")
                log.exception(e)

        if args.classical and composers:
            composerStr = munge(makeComposerString(composers))

        for f in audio:
            renameFile(f[0], f[1], dragfiles=dragfiles, dirname=composerStr)

        for f in dirs:
            reorgDir(f)
    except Exception as e:
        log.warning(f"Caught exception processing {name}: {e}")
        log.exception(e)



def initLogging():
    handler = colorlog.StreamHandler()
    colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'red,bg_white',
    }
    #formatter = colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(name)s:%(message)s', log_colors=colors)
    formatter = colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(reset)s %(message)s', log_colors=colors)
    handler.setFormatter(formatter)

    levels = [logging.WARN, logging.INFO, logging.DEBUG] #, logging.TRACE]
    level = levels[min(len(levels)-1, args.verbose)]  # capped to number of levels

    logger = colorlog.getLogger('reorg')
    logger.addHandler(handler)
    logger.setLevel(level)

    return logger


global args, log, bases

args = processArgs()
log = initLogging()

if args.split:
    bases = dict(map(lambda y: [y[0].upper(), y[1]], map(lambda x: x.split("="), args.bases)))
    print(bases)
else:
    bases = {}

for name in args.files:
    try:
        log.info(f"Running {name}")
        p = pathlib.Path(name)
        if not p.exists():
            log.error(f"{name} doesn't exist")
        elif p.is_dir():
            reorgDir(p)
        elif p.is_file():
            tags = getTags(p)
            renameFile(p, tags)
    except KeyboardInterrupt:
        log.info("Aborting")
    except Exception as e:
        log.warning(f"Caught exception processing {name}: {e}")
        log.exception(e)
