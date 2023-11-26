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
import os
import os.path
import logging
import pathlib
import unicodedata
import shutil
from collections import Counter, defaultdict
from functools import reduce

import regex as re

import colorlog
import unidecode
import music_tag
import magic

class NotAudioException(Exception):
    """ Class to indicate a file is not an audio file """

ACTION_LINK=1
ACTION_MOVE=2
ACTION_COPY=3
ACTION_SYMLINK=4

bases_default = os.environ.get('REORG_TYPES', '').split()
base_default = os.environ.get('REORG_BASE', '.')

args = None
log = None
bases = None

def processArgs():
    _def = ' (default: %(default)s)'

    parser = argparse.ArgumentParser(description="Reorganize music files", add_help=True)

    parser.add_argument('--base', '-b', type=pathlib.Path, dest='base', default=pathlib.Path(base_default),
                        help='Base destination directory' + _def)
    parser.add_argument('--types', '-t', dest='split', default=True, action=argparse.BooleanOptionalAction,
                        help='Split by type' + _def)
    parser.add_argument('--typebase', '-B', dest='bases', default=bases_default, nargs='*',
                        help='Bases for each type.   Ex: flac=/music/flac mp3=/music/mp3')

    action = parser.add_mutually_exclusive_group()
    action.add_argument('--move', dest='action', action='store_const', default=ACTION_MOVE, const=ACTION_MOVE,
                        help='Move (rename) the files')
    action.add_argument('--link', dest='action', action='store_const', const=ACTION_LINK,
                        help='Hard link the files')
    action.add_argument('--copy', dest='action', action='store_const', const=ACTION_COPY,
                        help='Copy the files')
    action.add_argument('--symlink', '--softlink', dest='action', action='store_const', const=ACTION_SYMLINK,
                        help='Symbolic link the files')

    parser.add_argument('--recurse', default=True, dest='recurse', action=argparse.BooleanOptionalAction, 
                        help='Recurse into directories' + _def)
    parser.add_argument('--dry-run', '-n', dest='test', default=False, action=argparse.BooleanOptionalAction,
                        help='Rename files.  If false, only')
    parser.add_argument('--drag', '-d', dest='drag', nargs='*', default=['cover.jpg'],
                        help='List of files to copy along with the music files' + _def)

    parser.add_argument('--ascii', '-A', dest='ascii', default=False, action=argparse.BooleanOptionalAction,
                        help='Convert to ASCII characters')
    parser.add_argument('--normalize', '-N', dest='normalize', default=True, action=argparse.BooleanOptionalAction,
                        help='Normalize Unicode Strings')
    parser.add_argument('--inplace', '-i', dest='inplace', default=False, action=argparse.BooleanOptionalAction,
                        help='Rename files inplace')
    parser.add_argument('--albartist', '-a', dest='albartist', default=True, action=argparse.BooleanOptionalAction,
                        help='Use album artist for default directory if available' + _def)
    parser.add_argument('--discnum', '-D', dest='alwaysdisc', default=False, action=argparse.BooleanOptionalAction,
                        help='Always use the disknumber in file names' + _def)
    parser.add_argument('--various', '-V', dest='various', default="VariousArtists",
                        help='"Artist" name for various artists collections' + _def)
    parser.add_argument('--the', '-T', dest='useArticle', default=True, action=argparse.BooleanOptionalAction,
                        help='Use articles')
    parser.add_argument('--classical', '-C', dest='classical', default=False, action=argparse.BooleanOptionalAction,
                        help='Use classical naming')
    parser.add_argument('--surname', '-S', dest='surname', default=False, action=argparse.BooleanOptionalAction,
                        help='Use the sorted name (ie, surname) of the composer if available' + _def)
    parser.add_argument('--length', dest='maxlength', default=75, type=int,
                        help='Maximum length of file names' + _def)
    parser.add_argument('--clean', '-c', dest='cleanup', default=False, action=argparse.BooleanOptionalAction,
                        help='Cleanup empty directories and dragged files when done' + _def)
    parser.add_argument('--ignore-case', '-I', dest='ignorecase', default=False,  action=argparse.BooleanOptionalAction,
                        help='Ignore case when determining if target exists' + _def)

    parser.add_argument('--unknown', dest='unknown', default=True, action=argparse.BooleanOptionalAction,
                        help="Ignore 'unknown' files without artist or album info")

    parser.add_argument('--warn-non-audio', dest='warnNonAudio', default=False, action=argparse.BooleanOptionalAction,
                        help="Ignore non-audio files")
    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0,
                        help='Increase the verbosity')

    parser.add_argument('files', nargs='+', type=pathlib.Path,
                        help='List of files/directories to reorganize')

    return parser.parse_args()

def munge(name):
    """ Mangle a name such that it's completely printable """
    if name is None:
        name = ""
    if args.normalize:
        name = unicodedata.normalize('NFKC', name)
    if args.ascii:
        name = unidecode.unidecode(name)
    #name = re.sub(r'[/&\.\[\]\$\"\'\?\(\)\<\>\!\:\;\~\p{P}]', '', name)
    #name = re.sub(r'[^\w\s,]', '', name)
    #name = re.sub(r'[/&\.\[\]\$\"\'\?\(\)\<\>\!\:\;\~]', '', name)

    # Remove all punctuation, except -,_
    name = re.sub(r'[^\P{Punct}-,_]', '', name)
    # Remove all control characters (what the f**k are these doing in a name anyhow?)
    name = re.sub(r'[\p{Cntrl}]', '', name)
    # Convert all spaces to underscores
    name = re.sub(r'\s', '_', name)
    # Convert multiple underscores to a single underscore
    name = re.sub(r'_+', '_', name)
    # Re
    if not args.useArticle:
        name = re.sub(r"^(The|A|An)\s+", "", name)
    name = name.strip('_')
    return name


def longestName(files):
    if files:
        return reduce(max, map(lambda x: len(str(x)), files))
    return 0

def noSlash(tag):
    if tag.find('/') != -1:
        tag = tag[0:tag.find('/')]
    return tag

def makeFName(file, tags):
    name = ""
    diskno = tags.get('discnumber').first
    totaldiscs = tags.get('totaldiscs').first

    title = tags.get('tracktitle').first
    if title is None:
        if not args.unknown:
            return None
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
        trk = f"{diskno}-{track.zfill(2)}"
    else:
        trk = noSlash(track).zfill(2)

    #name = name + '.' + tags.get('track_name')

    # Don't take the suffix length into account, confuses things when suffixes are different lengths
    # .flac vs .mp3 for instance.
    maxlen = max(args.maxlength - len(trk), 5)

    #name = "{0}.{1}{2}".format(trk, munge(title)[0:m].strip(), f.suffix)
    name = f"{trk}.{munge(title)[0:maxlen]}{file.suffix}"
    log.debug(f"Name {file.name} -> {name}")
    return name

def makeComposerString(composers, maxcomps=3):
    # Make a unique list of composers.
    unique = list(map(munge, sorted(composers)))

    listed = unique[:maxcomps]
    if len(listed) > 1:
        string = ",_".join(listed[:-1])
        if len(listed) > 1:
            string = "_&_".join([string, listed[-1]])
        if len(unique) > maxcomps:
            string += '_et_al'
    else:
        string = listed[0]

    return string

def getArtist(tags):
    artist = tags.get('artist').first
    log.debug(f"Retrieved artist: {artist}")
    return artist

def makeDName(file, tags, dirname=None):
    if args.inplace:
        base = file.parent
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

        album = tags.get('album').first
        if not album:
            if not args.unknown:
                return None
            album = 'Unknown'

        base = base.joinpath(dirname, munge(album))

    log.debug(f"Dir: {file.parent} -> {base}")
    return base


def isAudio(file):
    return magic.from_buffer(open(file, 'rb').read(2048), mime=True).startswith("audio")

def getTags(file):
    log.debug(f"Getting tags from file {file}")
    if not isAudio(file):
        raise NotAudioException(f"{file.resolve()} is not an audio file")
    try:
        tags = music_tag.load_file(file)
        return tags
    except NotImplementedError as exc:
        log.warning(f"Could not retrieve tags from {file}: {exc}")
        raise NotAudioException(file.resolve()) from exc

def makeName(file, tags, dirname = None):
    dirname = makeDName(file, tags, dirname)

    newFile = dirname.joinpath(makeFName(file, tags))

    log.debug(f"FullName {file} -> {newFile}")
    return newFile

def dragFiles(dragfiles, destdir, length):
    action = actionName()
    if not length:
        length = longestName(dragFiles)
    for file in dragfiles:
        dest = destdir.joinpath(file.name)
        if file.exists() and not dest.exists():
            log.log(logging.ACTION, f"{action} {str(file):{length}}\t==>  {dest}")
            doMove(file, dest)

def doMove(src, dest):
    if not args.test:
        if not dest.parent.exists():
            log.debug(f"Creating {dest.parent}")
            dest.parent.mkdir(parents=True, exist_ok=True)
        elif not dest.parent.is_dir():
            #log.warning(f"{dest.parent} exists, and is not a directory")
            raise NotADirectoryError("{dest.parent} exists, and is not a directory")

        if args.action == ACTION_LINK:
            dest.hardlink_to(src)
        elif args.action == ACTION_SYMLINK:
            dest.symlink_to(src)
        elif args.action == ACTION_MOVE:
            src.rename(dest)
        elif args.action == ACTION_COPY:
            shutil.copy2(src, dest)
        else:
            raise ValueError(f"Unknown action: {args.action}")


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


def renameFile(file, tags, dragfiles=None, dirname=None, length=0):
    action = actionName()
    if not length:
        length = len(str(file))
    try:
        dest = makeName(file, tags, dirname)
        if dest is None:
            log.info(f"Skipping file {file.name}.   Unknown album or artist")
            return None

        if file.expanduser().absolute() == dest.expanduser().absolute():
            log.debug(f"Src {file} and dest {dest} are the same.   No changes")
            return dest

        if dest.exists():
            if not file.samefile(dest):
                log.warning(f"{dest} exists, skipping ({file})")
                return dest

        if args.ignorecase and file.name.lower() == dest.name.lower():
            log.debug(f"Not moving {file.name} to {dest.name}.   Change is only in case")
            return dest


        log.log(logging.ACTION, f"{action} {str(file):{length}s} \t==>  {dest}")

        doMove(file, dest)

        return dest
    except NotAudioException as exc:
        if args.warnNonAudio:
            log.warning(exc)
        return None
    except AttributeError as exc:
        log.warning(exc)
        return None
    except FileExistsError as exc:
        log.warning(f"Destination file {dest} exists.  Cannot move")
        return dest
    except Exception as exc:
        log.warning(f"Caught exception {exc} processing {file.name}")
        log.exception(exc)
        return None

def isDraggable(file):
    for pat in args.drag:
        if file.match(pat):
            return True
    return False

def classicalArtist(tags):
    if tags.get('composersort') and args.surname:
        return tags.get('composersort').first
    if tags.get('composer'):
        return tags.get('composer').first
    if tags.get('artist'):
        return tags.get('artist').first
    return None

def reorgDir(directory, recurse):
    try:
        log.info(f"Processing Directory {directory}")
        dirs = []
        audio = []
        composers = set()
        dragfiles = []
        destdirs = Counter()
        files = sorted(filter(lambda x: not x.name.startswith('.'), list(directory.iterdir())))
        maxLen = longestName(files)

        composerStr = None

        for file in files:
            try:
                log.debug(f"Checking {file} -- {file.is_dir()} {file.is_file()}")
                if file.is_dir():
                    dirs.append(file)
                elif file.is_file():
                    if isDraggable(file):
                        dragfiles.append(file)
                    else:
                        tags = getTags(file)
                        audio.append((file, tags))
                        if args.classical:
                            composers.add(classicalArtist(tags))

            except NotAudioException as exc:
                if args.warnNonAudio:
                    log.warning(exc)
            except Exception as exc:
                log.warning(f"Caught exception processing {file}: {exc}")
                log.exception(exc)

        if args.classical and composers:
            composerStr = makeComposerString(composers)

        for finfo in audio:
            dest = renameFile(finfo[0], finfo[1], dragfiles=dragfiles, dirname=composerStr, length=maxLen)
            if dest:
                if not dest.parent in destdirs:
                    dragFiles(dragfiles, dest.parent, maxLen)
                destdirs[dest.parent] += 1

        if len(destdirs) > 1:
            log.warning(f"Not all files from {directory} went to the same directory: ")
            for targ in destdirs:
                log.warning(f"    {targ}: {destdirs[targ]} file(s)")

        if recurse:
            for subdir in dirs:
                reorgDir(subdir, recurse)

        if args.cleanup:
            if dragfiles:
                log.info("Removing dragged files: %s", " ".join(dragfiles))
                if not args.test:
                    map(pathlib.Path.unlink, dragfiles)
            if not any(directory.iterdir()):
                log.info("Removing empty directory %s", directory)
                if not args.test:
                    directory.rmdir()

    except Exception as exc:
        log.warning(f"Caught exception processing {directory}: {exc}")
        log.exception(exc)
        raise exc

def initLogging():
    # Create a custom logging attachment
    logging.ACTION = logging.INFO + 1
    logging.addLevelName(logging.ACTION, 'ACTION')

    handler = colorlog.StreamHandler()
    colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'ACTION':   'cyan,bold',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'red,bg_white',
    }

    formatter = colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(reset)s %(message)s',
                                          log_colors=colors)
    handler.setFormatter(formatter)

    levels = [logging.WARN, logging.ACTION, logging.INFO, logging.DEBUG] #, logging.TRACE]
    level = levels[min(len(levels)-1, args.verbose)]  # capped to number of levels

    logger = colorlog.getLogger('reorg')
    logger.addHandler(handler)
    logger.setLevel(level)

    return logger


def main():
    global args, log, bases

    args = processArgs()
    log = initLogging()

    bases = defaultdict(lambda: args.base)

    if args.split:
        # Create a dict of {codec: path, ...} from array [codec=path, codec=path, ...]
        #bases = dict(map(lambda y: [y[0].lower(), pathlib.Path(y[1])], map(lambda x: x.split("="), args.bases)))
        for t, p in map(lambda y: [y[0].lower(), pathlib.Path(y[1])], map(lambda x: x.split("="), args.bases)):
            if not p.is_absolute():
                p = args.base.joinpath(p)
            bases[t] = p

    maxLength = longestName(args.files)

    for file in args.files:
        try:
            if not file.exists():
                log.error(f"{file} doesn't exist")
            elif file.is_dir():
                reorgDir(file, args.recurse)
            elif file.is_file():
                tags = getTags(file)
                renameFile(file, tags, length=maxLength)
        except KeyboardInterrupt:
            log.info("Aborting")
        except Exception as exc:
            log.warning(f"Caught exception processing {file}: {exc}")
            log.exception(exc)

def run():
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted")

if __name__ == "__main__":
    run()
