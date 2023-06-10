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
import os.path
import sys
import logging
import pathlib
import re
import unicodedata
import shutil
import operator
import functools

import colorlog
import unidecode
#from pymediainfo import MediaInfo
import music_tag

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
    parser.add_argument('--discnum', '-D', dest='alwaysdisc', default=False, action=argparse.BooleanOptionalAction, help='Always use the disknumber in file names' + _def)
    parser.add_argument('--various', '-V', dest='various', default="VariousArtists",                                help='"Artist" name for various artists collections' + _def)
    parser.add_argument('--the', '-T', dest='useArticle', default=True, action=argparse.BooleanOptionalAction,      help='Use articles')
    parser.add_argument('--classical', '-C', dest='classical', default=False, action=argparse.BooleanOptionalAction,    help='Use classical naming')
    parser.add_argument('--surname', '-S', dest='surname', default=True, action=argparse.BooleanOptionalAction,     help='Use the sorted name (ie, surname) of the composer if available' + _def)
    parser.add_argument('--length', dest='maxlength', default=75, type=int,                                         help='Maximum length of file names' + _def)
    parser.add_argument('--clean', '-c', dest='cleanup', default=False,                                             help='Cleanup empty directories and dragged files when done' + _def)
    parser.add_argument('--ignore-case', '-I', dest='ignorecase', default=False,  action=argparse.BooleanOptionalAction,
                                                                                                                    help='Ignore case when determining if target exists' + _def)

    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0,                               help='Increase the verbosity')

    parser.add_argument('files', nargs='*', default=['.'], help='List of files/directories to reorganize')

    args = parser.parse_args()
    return args

def munge(name):
    if name is None:
        name = ""
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
    diskno = tags.get('discnumber').first
    totaldiscs = tags.get('totaldiscs').first

    title = tags.get('tracktitle').first
    if title is None:
        title = 'Unknown'

    if 'subtitle' in tags:
        title = title + " " + tags.get('subtitle').first
    #elif 'part' in tags:
    #    title = title + " " + str(tags.get('part'))

    if 'tracknumber' in tags:
        track = str(tags.get('tracknumber'))
    else:
        track = '0'


    if diskno is not None and (args.alwaysdisc or  totaldiscs and totaldiscs > 1):
        trk = "{0}-{1}".format(noSlash(str(diskno)), track.zfill(2))
    else:
        trk = noSlash(track).zfill(2) 

    #name = name + '.' + tags.get('track_name')

    # Don't take the suffix length into account, confuses things when suffixes are different lengths
    # .flac vs .mp3 for instance.
    m = max(args.maxlength - len(trk), 5)

    name = "{0}.{1}{2}".format(trk, munge(title)[0:m].strip(), f.suffix)
    log.debug(f"Name {f.name} -> {name}")
    return name

def makeComposerString(composers, maxcomps=3):
    # Make a unique list of composers.
    unique = list(map(munge, sorted(composers)))

    listed = unique[:maxcomps]
    if len(listed) > 1:
        string = ",_".join(listed[:-1])
        if len(listed) > 1:
            string = ",_&_".join([string, listed[-1]])
        if len(unique) > maxcomps:
            string += '_et_al'
    else:
        string = listed[0]

    return string

def getArtist(tags):
    artist = tags.get('artist').first
    log.debug(f"Retrieved artist: {artist}")
    return artist

def makeDName(f, tags, dirname=None):
    if args.inplace:
        base = f.parent
    else:
        codec = tags.get('#codec').first.split('.')[0].lower()
        base = pathlib.Path(bases.get(codec, args.base))
        log.debug(f"BaseDir: {base}")

        if dirname is None:
            compilation = str(tags.get('compilation')).lower()
            if compilation in ['yes', '1', 'true']:
                dirname = args.various
            elif args.albartist and tags.get('albumartist'):
                dirname = tags.get('albumartist').first
            else:
                dirname = getArtist(tags)
            dirname = munge(dirname)

        album = tags.get('album').first or "Unknown"

        base = base.joinpath(dirname, munge(album))

    log.debug(f"Dir: {f.parent} -> {base}")
    return base

def getTags(f):
    log.debug(f"Getting tags from file {f}")
    try:
        tags = music_tag.load_file(f)
        return tags
    except NotImplementedError as e:
        log.warning(f"Could not retrieve tags from {f}")
        raise NotAudioException(f.resolve())

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
        elif args.action == ACTION_COPY:
            shutil.copy2(src, dest)
        else:
            raise Exception("Unknown action: %s", args.action)


def actionName():
    if args.action == ACTION_LINK:
        name = "Linking"
    elif args.action == ACTION_MOVE:
        name = "Moving"
    elif args.action == ACTION_COPY:
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
            return dest

        if args.ignorecase and f.name.lower() == dest.name.lower():
            log.debug(f"Not moving {f.name} to {dest.name}.   Change is only in case")
            return dest

        log.info(f"{action} {f}\t==>  {dest}")

        doMove(f, dest)
        dragFiles(dragfiles, dest.parent)

        return dest
    except NotAudioException as e:
        log.warning(e)
        return None
    except FileExistsError as e:
        log.warning(f"Destination file {f} exists.  Cannot move")
        return dest
    except Exception as e:
        log.warning(f"Caught exception {e} processing {f.name}")
        log.exception(e)
        return None

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
        composers = set()
        dragfiles = []
        files = sorted(filter(lambda x: not x.name.startswith('.'), list(d.iterdir())))

        composerStr = None

        for f in files:
            try:
                log.debug(f"Checking {f} -- {f.is_dir()} {f.is_file()}")
                if f.is_dir():
                    dirs.append(f)
                elif f.is_file():
                    if isDraggable(f):
                        dragfiles.append(f)
                    else:
                        tags = getTags(f)
                        audio.append((f, tags))
                        if args.classical:
                            if tags.get('composersort') and args.surname:
                                composers.add(tags.get('composersort').first)
                            elif tags.get('composer'):
                                composers.add(tags.get('composer').first)
                            elif tags.get('artist'):
                                composers.add(tags.get('artist').first)

            except NotAudioException as e:
                log.warning(e)
            except Exception as e:
                log.warning(f"Caught exception processing {name}: {e}")
                log.exception(e)

        if args.classical and composers:
            composerStr = makeComposerString(composers)

        destdirs = set()
        for f in audio:
            dest = renameFile(f[0], f[1], dragfiles=dragfiles, dirname=composerStr)
            destdirs.add(dest.parent)

        if len(destdirs) > 1:
            log.warning(f"Not all files from {d} went to the same directory: {list(map(str, destdirs))}")

        for f in dirs:
            reorgDir(f)
    except Exception as e:
        log.warning(f"Caught exception processing {name}: {e}")
        log.exception(e)
        raise e



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
    bases = dict(map(lambda y: [y[0].lower(), y[1]], map(lambda x: x.split("="), args.bases)))
else:
    bases = {}

for name in args.files:
    try:
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
