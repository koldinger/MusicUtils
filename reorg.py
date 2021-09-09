#! /usr/bin/env python

import argparse
import os.path
import sys
import logging
import pprint
import pathlib
import re
import unicodedata

import colorlog
import unidecode
from pymediainfo import MediaInfo

class NotAudioException(Exception):
    pass

def processArgs():
    _def = ' (default: %(default)s)'

    parser = argparse.ArgumentParser(description="Reorganize music files", add_help=True)

    parser.add_argument('--base', '-b', dest='base', default='.',                                               help='Base destination directory' + _def)
    parser.add_argument('--split', '-s', dest='split', default=False,                                           help='Split by type' + _def)
    parser.add_argument('--flacbase', '-f', dest='flacbase', default='/srv/music/FLAC',                         help='Base dir for FLAC files, if --split' + _def)
    parser.add_argument('--mp3base', '-3', dest='mp3base', default='/srv/music/MP3/CD',                         help='Base dir for MP3 files, if --split' + _def)
    parser.add_argument('--mp4base', '-4', dest='mp4base', default='/srv/music/MP4/CD',                         help='Base dir for MP4 files, if --split' + _def)
    parser.add_argument('--link', '-l', dest='link', default=True, action=argparse.BooleanOptionalAction,       help='Hard link instead of moving')
    parser.add_argument('--rename', dest='rename', default=False, action=argparse.BooleanOptionalAction,        help='Rename files.  If false, only')
    parser.add_argument('--drag', '-d', dest='drag', nargs='*', default=['cover.jpg'],                          help='List of files to copy along with the music files' + _def)
    parser.add_argument('--ascii', '-A', dest='ascii', default=False, action=argparse.BooleanOptionalAction,    help='Convert to ASCII characters')
    parser.add_argument('--normalize', '-N', dest='normalize', default=True, action=argparse.BooleanOptionalAction, help='Normalize Unicode Strings')
    parser.add_argument('--inplace', '-i', dest='inplace', default=False, action=argparse.BooleanOptionalAction,    help='Rename files inplace')
    parser.add_argument('--albartist', '-a', dest='albartist', default=True,                                    help='Use album artist for default directory if available' + _def)
    parser.add_argument('--various', '-V', dest='various', default="VariousArtists",                            help='"Artist" name for various artists collections' + _def)
    parser.add_argument('--the', '-T', dest='useArticle', default=True, action=argparse.BooleanOptionalAction,  help='Use articles')
    parser.add_argument('--classical', '-C', dest='classical', default='Classical',                             help='Use classical naming if the genre starts with this' + _def)
    parser.add_argument('--classicaldir', '-D', dest='classicaldir', default='Classical',                       help='Store classical files in this subdirectory' + _def)
    parser.add_argument('--length', dest='maxlength', default=75, type=int,                                     help='Maximum length of file names' + _def)
    parser.add_argument('--clean', '-c', dest='cleanup', default=False,                                         help='Cleanup empty directories and dragged files when done' + _def)

    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0,                           help='Increase the verbosity')

    parser.add_argument('files', nargs='+', help='List of files/directories to reorganize')

    args = parser.parse_args()
    return args

def munge(name):
    if args.normalize:
        name = unicodedata.normalize('NFKC', name)
    if args.ascii:
        name = unidecode.unidecode(name)
    name = re.sub('[/&\.\[\]\$\"\'\?\(\)\<\>\!\:\;]', '', name)
    name = re.sub('\s', '_', name)
    name = re.sub('_+', '_', name)
    name.strip('_')
    return name


def noSlash(tag):
    if tag.find('/') != -1:
        tag = tag[0:tag.find('/')]
    return tag

def makeFName(f, tags):
    name = ""
    diskno = None
    if tags.get('part_position'):
        diskno = tags.get('part_position')
    elif tags.get('set'):
        diskno = tags.get('set')

    title = tags.get('title')
    title = title if title else tags.get('track_name', 'Unknown')
    if tags.get('title__more'):
        title = title + " " + tags.get('title__more')
    elif tags.get('track_name__more'):
        title = title + " " + tags.get('track_name__more')
    #elif tags.get('part'):
    #    title = title + " " + str(tags.get('part'))

    if diskno:
        trk = "{0}-{1}".format(noSlash(diskno), noSlash(tags.get('track_name_position', '0')).zfill(2))
    else:
        trk = noSlash(tags.get('track_name_position', '00')).zfill(2) 

    #name = name + '.' + tags.get('track_name')

    m = max(args.maxlength - len(f.suffix) - len(trk), 5)

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


def makeDName(f, tags, dirname=None):
    if args.inplace:
        base = f.parent
    else:
        base = pathlib.Path(bases[tags['format']])

        if dirname is None:
            if tags.get('compilation') == 'Yes':
                dirname = args.various
            elif args.albartist and tags.get('album_performer'):
                dirname = tags.get('album_performer')
            else:
                dirname = tags.get('performer', 'Unknown')

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

def dragFiles(dragfiles, srcdir, destdir):
    action = "Linking" if args.link else "Moving"
    if not args.rename:
        action = "[TESTING] " + action
    for f in dragfiles:
        src = srcdir.joinpath(f)
        dest = destdir.joinpath(f)
        if src.exists() and not dest.exists():
            doMove(src, dest)

def doMove(src, dest):
    if args.rename:
        if not dest.parent.exists():
            log.debug(f"Creating {dest.parent}")
            dest.parent.mkdir(parents=True, exist_ok=True)
        elif not dest.parent.is_dir():
            #log.warning(f"{dest.parent} exists, and is not a directory")
            raise Exception("{dest.parent} exists, and is not a directory")

        if args.link:
            src.link_to(dest)
        else:
            src.rename(dest)

def renameFile(f, tags, dragfiles=[], dirname=None):
    action = "Linking" if args.link else "Moving"
    if not args.rename:
        action = "[TESTING] " + action
    log.debug(f"Renaming {f.name}")
    dest = makeName(f, tags, dirname)
    try:
        if dest.exists():
            log.warning(f"{dest} exists, skipping")
            return
        log.info(f"{action} {f}\t==>  {dest}")

        if args.rename:
            doMove(f, dest)
        dragFiles(dragfiles, f.parent, dest.parent)

    except NotAudioException as e:
        log.warning(e)
    except Exception as e:
        log.warning(f"Caught exception {e} processing {f.name}")
        log.execption(e)

def reorgDir(d):
    try:
        log.info(f"Processing Directory {d}")
        dirs = []
        audio = []
        composers = []
        files = sorted(filter(lambda x: not x.name.startswith('.'), list(d.iterdir())))

        composerStr = None

        for f in files:
            try:
                log.debug(f"Checking {f}")
                if f.is_dir():
                    dirs.append(f)
                elif f.is_file():
                    tags = getTags(f)
                    audio.append((f, tags))
                    if tags.get('genre', '').startswith(args.classical) and tags.get('composer'):
                        composers.append(tags.get('composer'))
            except NotAudioException as e:
                log.warning(e)
            except Exception as e:
                log.warning(f"Caught exception processing {name}: {e}")
                log.exception(e)


        if composers:
            composerStr = pathlib.Path(args.classicaldir).joinpath(munge(makeComposerString(composers)))
            print(composers, composerStr)

        for f in audio:
            renameFile(f[0], f[1], dragfiles=args.drag, dirname=composerStr)

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

    levels = [logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG] #, logging.TRACE]
    level = levels[min(len(levels)-1, args.verbose)]  # capped to number of levels

    logger = colorlog.getLogger('reorg')
    logger.addHandler(handler)
    logger.setLevel(level)

    return logger


global args, log, bases

args = processArgs()
log = initLogging()

if args.split:
    bases = {
        'FLAC': args.flacbase,
        'MPEG Audio': args.mp3base,
        'MPEG-4': args.mp4base
    }
else:
    bases = {
        'FLAC': args.base,
        'MPEG Audio': args.base,
        'MPEG-4': args.base
    }

log.info("Starting")

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
            renameFile(p, tags, dragfiles=args.drag)
    except KeyboardInterrupt:
        log.info("Aborting")
    except Exception as e:
        log.warning(f"Caught exception processing {name}: {e}")
        log.exception(e)
