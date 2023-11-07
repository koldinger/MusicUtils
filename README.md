# MusicUtils
A set of useful utilities for manipulating music/audio files.

* reorg - Reorganize your music files based on filetype, artist, and album.
* tagit - Command line tag editor.   Only works with the tags available in the music_tag module, but works on most common music types
* tagedit - A command line based tag editor.   Generates a YAML file and brings it up in your favorite editor and then sets the tags appropriately.
* copyTags - Copy tags from one file, or directory, to another.   Useful if you maintain multiple versions of a file (say, FLAC for a home system, mp4 for portables)
* aconvert - Convert audio files from one format to another.   Inspired by the AudioConverter project, but works better.
  
These generally rely on the music_tag library for multi-format manipulation, which is built on Mutagen.   My current fork of music_tag is required (https://github.com/koldinger/music-tag)
Not currently specified in the requirements.txt file, but soon will once I get that cleaned up, and hopefully integrated into base.
