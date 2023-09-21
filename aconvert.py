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

import pathlib
import argparse
import logging
import sys
import os
import time
from pprint import pprint
from multiprocessing import Pool
from collections import namedtuple

import magic
import colorlog
import music_tag
import progressbar
from pydub import AudioSegment

from rich.progress import *
import rich.logging
import rich.highlighter

Conversion = namedtuple("Conversion", ["source", "dest", "format", "codec", "bitrate", "params", "logger", "args"])
DefParams = namedtuple("DefParams", ["codec", "format", "bitrate", "suffix", "params"])

defaults = {
    "mp3":  DefParams("mp3", "mp3", "192k", ".mp3", None),
    "aac":  DefParams("aac", "ipod", "128k", ".m4a", None),
    "ogg":  DefParams("libvorbis", "ogg", None, ".ogg", None),
    "opus": DefParams("libopus", "opus", None, ".opus", None),
    "alac": DefParams("alac", "ipod", None, ".alac", None),
    "flac": DefParams("flac", "flac", None, ".flac", None)
}

formats = {
    "audio/flac" : "flac",
    "audio/mp3"  : "mp3",
    "audio/x-m4a": "mp4"
    }

inputtypes = {
            ".flac": "flac",
            ".m4a": "ipod",
            ".mp4" : "mp4",
            ".mp3" : "mp3",
            ".ogg" : "ogg",
            ".alac": "alac",
            ".ape": "ape"
            }

bitrates = {
            "mp3": "320k",
            "ipod": "92k",
            "mp4": "128k"
           }


logger = None
args = None

def initLogging(verbosity):
    #progressbar.streams.wrap_stderr()
    #handler = colorlog.StreamHandler()
    handler = rich.logging.RichHandler(show_time=True, show_path=False, highlighter=rich.highlighter.NullHighlighter())
    colors={
        'DEBUG':    'cyan',
        'INFO':     'green',
        'WARNING':  'yellow',
        'ERROR':    'red',
        'CRITICAL': 'red,bg_white',
    }
    #formatter = colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(name)s:%(message)s', log_colors=colors)
    #formatter = colorlog.ColoredFormatter('%(log_color)s%(levelname)s:%(reset)s %(message)s', log_colors=colors)
    #handler.setFormatter(formatter)

    levels = [logging.WARN, logging.INFO, logging.DEBUG] #, logging.TRACE]
    level = levels[min(len(levels)-1, verbosity)]        # capped to number of levels

    logger = colorlog.getLogger('reorg')
    logger.addHandler(handler)
    logger.setLevel(level)

    return logger

def collectFiles(src):
    dirs = []
    files = []

    logger.debug("Scanning directory {}".format(src))

    for i in sorted(src.iterdir()):
        if i.is_dir():
            dirs.append(i)
        elif i.suffix.lower() in inputtypes:
            #files.append(i)
            yield i

    for i in dirs:
        #files.extend(collectFiles(i))
        yield from collectFiles(i)

    #return files

def makeJobs(files: list[pathlib.Path], srcdir: pathlib.Path, destdir: pathlib.Path, suffix: str, fmt: str, codec: str, bitrate: str, overwrite=False, empty=False):
    logger.debug("Creating jobs specifications %s %s %s %s", suffix, fmt, codec, bitrate)
    jobs = []
    for src in files:
        dest = pathlib.Path(destdir, src.relative_to(srcdir).with_suffix(suffix))
        logger.debug("%s -> %s", src, dest)
        if not dest.exists() or overwrite or (empty and dest.exists() and dest.stat().st_size == 0):
            # TODO: Add the parameters argument.
            jobs.append(Conversion(src, dest, fmt, codec, bitrate, None, logger, args))
        else:
            logger.debug("Skipping %s.  Target %s exists", src, dest)
    return jobs

def convert(job):
    src = job.source
    dest = job.dest
    logger = job.logger
    args = job.args

    #print(f"Running job {src} ({src.suffix}) to {dest} ({dest.suffix}, {job.format})") 

    try:
        times = src.stat()
        tags = music_tag.load_file(src)
        audio = AudioSegment.from_file(src, inputtypes[src.suffix])
        logger.debug("Loaded %s", src)
    except Exception as e:
        print(f"Failed loading {src} {e}")
        return src, dest, f"{src} -> {dest} failed loading: {e}"

    logger.debug("Begining Conversion %s -> %s", src, dest)

    try:
        if not args.dryrun:
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = audio.export(dest,
                               format=job.format,
                               bitrate=job.bitrate,
                               codec=job.codec)
            tmp.close()
    except Exception as e:
        print(f"Failed writing {dest}: {e}")
        return src, dest, f"{src} -> {dest} failed writing: {e}"

    if args.copytags:
        try:
            dstTags = music_tag.load_file(dest)
            for tag in tags:
                if tags[tag] and not tag.startswith("#"):
                    logger.debug("Copying tag %s: %s", tag, tags[tag])
                    dstTags[tag] = tags[tag]
            dstTags.save()
        except Exception as e:
            return src, dest, f"{src} -> {dest} failed copying tags: {e}"

    if args.copytime:
        try:
            logger.debug("Setting times for %s to %s, %s", dest, time.ctime(times.st_atime), time.ctime(times.st_mtime))
            os.utime(dest, times=(times.st_atime, times.st_mtime))
        except Exception as e:
            return src, dest, f"{src} -> {dest} failed copying time {e}"

    logger.debug("Completed conversion %s -> %s", src, dest)
    return src, dest, None

def processArgs():
    _def = ' (default: %(default)s)'
    processors = os.cpu_count()

    parser = argparse.ArgumentParser(description="Convert audio file formats", add_help=True)

    parser.add_argument('--output',  '-o', type=str, choices=defaults.keys(), default='aac', help='List of files/directories to reorganize')
    parser.add_argument('--format', '-f', dest='format', default=None,  help="Output Format" + _def)
    parser.add_argument('--bitrate', '-b', dest='bitrate', type=str, default=None, help='Output bitrate' + _def)
    parser.add_argument('--codec', '-c', dest='codec', type=str, default=None, help='Codec to use')
    parser.add_argument('--suffix', '-s', dest='suffix', type=str, default=None, help='Suffix to use')
    parser.add_argument('--copytags', '-t', dest='copytags', action=argparse.BooleanOptionalAction, default=True, help="Copy tags from the source to the destination" + _def)
    parser.add_argument('--copytime', '-T', dest='copytime', action=argparse.BooleanOptionalAction, default=False, help="Copy time from the source to the destination" + _def)
    parser.add_argument('--overwrite', '-O', dest='overwrite', action=argparse.BooleanOptionalAction, default=False, help="Overwrite files if they exist" + _def)
    parser.add_argument('--empty', '-E', dest='empty', action=argparse.BooleanOptionalAction, default=False, help='Overwrite empty files' + _def)
    parser.add_argument('--workers', '-w', dest='workers', type=int, default=int(processors/2), choices=range(1, processors+1), metavar=f"[1-{processors}]", help="Number of concurrent jobs to use" + _def)
    parser.add_argument('--dry-run', '-n', dest='dryrun', action=argparse.BooleanOptionalAction, default=False, help="Dry Run.   Don't actually write output")
    parser.add_argument('--progress', '-p', dest='progress', action=argparse.BooleanOptionalAction, default=True, help="Show a progress bar" +  _def)
    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0, help='Increase the verbosity')

    parser.add_argument('srcdir',  type=pathlib.Path, help='Root input directory')
    parser.add_argument('destdir', type=pathlib.Path, help='Root output directory')

    args = parser.parse_args()
    return args

def main():
    global logger, args

    args = processArgs()
    logger = initLogging(args.verbose)

    srcdir  = args.srcdir
    destdir = args.destdir

    suffix  = args.suffix or defaults[args.output].suffix
    codec   = args.codec  or defaults[args.output].codec
    bitrate = args.bitrate or defaults[args.output].bitrate
    fmt     = args.format or defaults[args.output].format

    audioFiles = collectFiles(srcdir)

    jobs = makeJobs(audioFiles, srcdir, destdir, suffix, fmt, codec, bitrate, args.overwrite, args.empty)

    logger.info("Running %d conversions on %d processes", len(jobs), args.workers)

    completed = 0

    try:
        with Pool(args.workers) as pool:
            with Progress(TextColumn("{task.description}"),
                          SpinnerColumn(),
                          BarColumn(bar_width=100),
                          TaskProgressColumn(),
                          MofNCompleteColumn(),
                          TimeRemainingColumn(),
                          expand=False) as pbar:
                task = pbar.add_task("Converting", total=len(jobs), visible=args.progress)
                #pbar.start()
                for src, dest, error in pool.imap_unordered(convert, jobs):
                    pbar.advance(task)
                    logger.info(f"Completed {src.relative_to(args.srcdir)}\tto {dest.relative_to(destdir)}")
                    if error:
                        logger.error(error)
                    completed += 1
    except KeyboardInterrupt:
        logger.error("Interrupted...")
    finally:
        logger.info(f"Completed {completed} out of {len(jobs)} conversions")

    #if pbar:
    #    pbar.finish()

if __name__ == "__main__":
    main()
