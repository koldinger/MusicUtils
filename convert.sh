#! /usr/bin/bash

if [ $# -ne 3 ];
    then echo "Usage: $0 inputdir outputdir suffix";
    exit 0
fi

export base=$1
export output=$2
export suffix=$3

#for i in $(find $base -name \*.flac); do
#for i in $(find $base -name \*.flac); do

IFS=$'\n'

doConvert() {
    #echo "1  " $1
    i=$1
    indir=$(dirname "$i")
    cover="$indir"/cover.jpg

    name=$(basename -s $suffix "$i")

    reldir=$(abs2rel "$i" "$base")
    dir=$(dirname "$reldir")
    outdir="$output"/"$dir"
    outfile="$outdir"/"$name.m4a"

    if [ ! -f "$outfile" ]; then
        echo "$name" "------" "$outfile"
        mkdir -p "$outdir"
        ffmpeg -i "$i" -n -loglevel 24 -c:a aac -b:a 128k -vcodec copy "$outfile"
        if [ -e "$cover" ]; then
            temp=$(mktemp)
            echo "Adding cover art to $outfile $temp"
            convert "$cover" -resize "300x>" $temp
            mp4art -q --add "$temp" "$outfile"
            rm -f "$temp"
        fi
    #else
    #    echo "Skipping $i"
    fi
}

export -f doConvert

parallel -j 12 doConvert ::: $(find $base -name \*$suffix -and -not -name ._\* | sort)
