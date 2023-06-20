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
import shutil
import fnmatch
import re

import pathlib
from termcolor import cprint

def processArgs():
    parser = argparse.ArgumentParser(description='Remove empty directories', add_help=True)
    parser.add_argument('--delete', '-d', dest='delete',   action='append', default=[], help="Files, or regular expressions, to delete")
    parser.add_argument('--mac', '-m',    dest='macFiles', action=argparse.BooleanOptionalAction, default=False, help='Delete Mac files that start with ._.')
    parser.add_argument('--hidden', '-a', dest='hidden',   action=argparse.BooleanOptionalAction, default=False, help='Delete hidden directories as well')
    parser.add_argument('--dry-run', '-n', dest='dryRun',  action=argparse.BooleanOptionalAction, default=False, help='Only show which files can be deleted')
    parser.add_argument('--verbose', '-v', dest='verbose', action='count', default=0, help='Increase verbosity')
    parser.add_argument(nargs='*', dest='dirs', type=pathlib.Path, default=[pathlib.Path('.')], help='Directories to prune')

    return parser.parse_args()

def prune(d, delPat, verbose, hidden, noDelete):
    if not d.is_dir():
        return 1

    if verbose:
        cprint(f"Pruning {d}", "green")

    files = list(d.iterdir())
    numFiles = len(files)

    if numFiles == 0:
        return 0

    if not hidden:
        files = [f for f in files if not f.name.startswith('.')]

    for f in files:
        if f.is_dir():
            if prune(f, delPat, verbose, hidden, noDelete) == 0:
                cprint(f"Deleting directory: {f}", "blue", attrs=['bold'])
                if not noDelete:
                    shutil.rmtree(f)
                numFiles -= 1
        elif delPat and delPat.match(f.name):
            if verbose:
                cprint(f"Can delete {f}", "cyan")
            numFiles -= 1

    return numFiles

def makeDeletions(args):
    macPats = ["._.*", ".DS_Store"]
    patterns = args.delete.copy()
    if args.macFiles:
        patterns.extend(macPats)
    regexs = [fnmatch.translate(i) for i in patterns]
    if regexs:
        return re.compile("|".join(regexs))
    return None         #re.compile('$^')

def main():
    args = processArgs()

    delPat = makeDeletions(args)

    for i in args.dirs:
        if i.is_dir():
            dirSize = prune(i, delPat, args.verbose, args.hidden, args.dryRun)
            if dirSize == 0 and not i == pathlib.Path('.'):
                cprint(f"Deleting directory: {i}", "blue", attrs=['bold'])
                if not args.dryRun:
                    shutil.rmtree(i)
        else:
            cprint(f"{i} is not a directory", "red")
    return 0

if __name__ == '__main__':
    main()
