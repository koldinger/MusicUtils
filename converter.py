#! /usr/bin/env python3

import pathlib
import argparse
import logging
import sys
import os
import time
from multiprocessing import Pool
from collections import namedtuple

import magic
import colorlog
import music_tag
import progressbar
from pydub import AudioSegment

Conversion = namedtuple("Conversion", ["source", "dest", "format", "codec", "bitrate", "logger"])
DefParams = namedtuple("DefParams", ["codec", "format", "bitrate", "suffix", "params"])

defaults = {
    "mp3":  DefParams("mp3", "mp3", "192k", ".mp3", None),
    "aac":  DefParams("aac", "ipod", "128k", ".mp4", None),
    "ogg":  DefParams("libvorbis", "ogg", None, ".ogg", None),
    "opus": DefParams("opus", "opus", None, ".opus", None),
    "alac": DefParams("alac", "ipod", None, ".alac", None)
}

formats = {
    "audio/flac" : "flac",
    "audio/mp3"  : "mp3",
    "audio/x-m4a": "mp4"
    }

suffixes = {"flac": ".flac",
            "ipod": ".m4a",
            "mp4" : ".mp4",
            "mp3" : ".mp3",
            "ogg" : ".ogg"}

bitrates = {
            "mp3": "320k",
            "ipod": "92k",
            "mp4": "128k"
           }

#create a reverse map
audiotypes = dict((v, k) for k, v in suffixes.items())

suffix_values = suffixes.values()

logger = None
args = None
pbar = None

def initLogging(verbosity):
    progressbar.streams.wrap_stderr()
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
    level = levels[min(len(levels)-1, verbosity)]        # capped to number of levels

    logger = colorlog.getLogger('reorg')
    logger.addHandler(handler)
    logger.setLevel(level)

    return logger

def collectFiles(src):
    dirs = []
    files = []

    logger.info("Processing directory {}".format(src))

    for i in sorted(src.iterdir()):
        if i.is_dir():
            dirs.append(i)
        elif i.suffix.lower() in suffix_values:
            #files.append(i)
            yield i

    for i in dirs:
        #files.extend(collectFiles(i))
        yield from collectFiles(i)

    #return files

def makeJobs(files: list[pathlib.Path], srcdir: pathlib.Path, destdir: pathlib.Path, suffix: str, fmt: str, codec: str, bitrate: str, overwrite=False):
    logger.info("Creating jobs specifications %s %s %s %s", suffix, fmt, codec, bitrate)
    jobs = []
    for src in files:
        dest = pathlib.Path(destdir, src.relative_to(srcdir).with_suffix(suffix))
        logger.debug("%s -> %s", src, dest)
        if not dest.exists() or overwrite:
            jobs.append(Conversion(src, dest, fmt, codec, bitrate, logger))
        else:
            logger.debug("Skipping %s.  Target %s exists", src, dest)
    return jobs

def convert(job):
    global pbar
    src = job.source
    dest = job.dest
    logger = job.logger

    #print(f"Running job {src} ({src.suffix}) to {dest} ({dest.suffix}, {job.format}") 

    try:
        times = src.stat()
        tags = music_tag.load_file(src)
        audio = AudioSegment.from_file(src, audiotypes[src.suffix])
        logger.debug("Loaded %s", src)
    except Exception as e:
        logger.error("Failed loading %s: %s", src, e)
        return f"{src} -> {dest} failed loading: {e}"

    logger.debug("Begining Conversion %s -> %s", src, dest)

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = audio.export(dest,
                           format=job.format,
                           bitrate=job.bitrate,
                           codec=job.codec)
        tmp.close()
    except Exception as e:
        logger.error("Failed writing %s: %s", dest, e)
        return f"{src} -> {dest} failed writing {e}"

    if args.copytags:
        try:
            dstTags = music_tag.load_file(dest)
            for tag in tags:
                if tags[tag] and not tag.startswith("#"):
                    logger.debug("Copying tag %s: %s", tag, tags[tag])
                    dstTags[tag] = tags[tag]
            dstTags.save()
        except Exception as e:
            logger.error("Caught exception copying tags for %s -> %s: %s", src.name, dest, e)

    if args.copytime:
        logger.debug("Setting times for %s to %s, %s", dest, time.ctime(times.st_atime), time.ctime(times.st_mtime))
        os.utime(dest, times=(times.st_atime, times.st_mtime))

    logger.debug("Completed conversion %s -> %s", src, dest)

def processArgs():
    _def = ' (default: %(default)s)'
    processors = len(os.sched_getaffinity(0))

    parser = argparse.ArgumentParser(description="Convert audio file formats", add_help=True)

    parser.add_argument('--format', '-f', dest='format', default=None,  help="Output Format" + _def)
    parser.add_argument('--bitrate', '-b', dest='bitrate', type=str, default=None, help='Output bitrate' + _def)
    parser.add_argument('--codec', '-c', dest='codec', type=str, default=None, help='Codec to use')
    parser.add_argument('--suffix', '-s', dest='suffix', type=str, default=None, help='Suffix to use')
    parser.add_argument('--copytags', '-t', dest='copytags', action=argparse.BooleanOptionalAction, default=True, help="Copy tags from the source to the destination" + _def)
    parser.add_argument('--copytime', '-T', dest='copytime', action=argparse.BooleanOptionalAction, default=False, help="Copy time from the source to the destination" + _def)
    parser.add_argument('--overwrite', '-o', dest='overwrite', action=argparse.BooleanOptionalAction, default=False, help="Overwrite files if they exist" + _def)
    parser.add_argument('--workers', '-w', dest='workers', type=int, default=int(processors/2), choices=range(1, processors+1), metavar=f"[1-{processors}]", help="Number of concurrent jobs to use" + _def)
    parser.add_argument('--progerss', '-p', dest='progress', action=argparse.BooleanOptionalAction, default=True, help="Show a progress bar" +  _def)
    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0, help='Increase the verbosity')

    parser.add_argument('srcdir',  type=pathlib.Path, help='Root input directory')
    parser.add_argument('destdir', type=pathlib.Path, help='Root output directory')
    parser.add_argument('output',  type=str, choices=defaults.keys(), help='List of files/directories to reorganize')

    args = parser.parse_args()
    return args

def main():
    global logger, args, pbar

    args = processArgs()
    logger = initLogging(args.verbose)

    srcdir  = args.srcdir
    destdir = args.destdir

    suffix  = args.suffix or defaults[args.output].suffix
    codec   = args.codec  or defaults[args.output].codec
    bitrate = args.bitrate or defaults[args.output].bitrate
    fmt     = args.format or defaults[args.output].format

    audioFiles = collectFiles(srcdir)

    jobs = makeJobs(audioFiles, srcdir, destdir, suffix, fmt, codec, bitrate, args.overwrite)

    logger.info("Running %d conversions on %d processes", len(jobs), args.workers)
    if args.progress:
        pbar = progressbar.ProgressBar(maxval=len(jobs))
        pbar.start()

    with Pool(args.workers) as pool:
        for _ in pool.imap_unordered(convert, jobs):
            if pbar:
                pbar += 1

    if pbar:
        pbar.finish()

if __name__ == "__main__":
    main()