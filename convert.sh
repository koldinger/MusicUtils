#! /usr/bin/bash

export base=/srv/music/FLAC
export output=$HOME/MP4/CD
export suffix=.flac

#for i in $(find $base -name \*.flac); do
#for i in $(find $base -name \*.flac); do

IFS=$'\n'

doConvert() {
    #echo "1  " $1
    i=$1
    name=$(basename -s $suffix "$i")
    reldir=$(abs2rel "$i" "$base")
    dir=$(dirname "$reldir")
    outdir="$output"/"$dir"
    outfile="$outdir"/"$name.m4a"

    if [ ! -f "$outdir"/"$name.m4a" ]; then
        echo "$name" "------" "$outfile"
        mkdir -p "$outdir"
        ffmpeg -i "$i" -n -loglevel 24 -c:a aac -b:a 128k -vcodec copy "$outfile"
    else
        echo "Skipping $i"
    fi
}

export -f doConvert

parallel -j 12 doConvert ::: $(find $base -name \*$suffix -and -not -name ._\* )
