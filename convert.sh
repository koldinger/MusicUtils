#! /usr/bin/bash

if [ $# -ne 3 ];
    then echo "Usage: $0 inputdir outputdir suffix";
    exit 0
fi

export base=$1
export output=$2
export suffix=$3

#export hasArt="$HOME/dev/MusicUtils/hasArt.py"

#for i in $(find $base -name \*.flac); do
#for i in $(find $base -name \*.flac); do

IFS=$'\n'

doConvert() {
    i=$1
    indir=$(dirname "$i")

    covers=(cover.jpg Folder.jpg folder.jpg AlbumArtSmall.jpg)

    for j in "${covers[@]}"; do
        x="$indir"/"$j"
        if [ -e "$x" ]; then
            cover=$x
            break
        fi
    done

    name=$(basename -s $suffix "$i")

    reldir=$(abs2rel "$i" "$base")
    dir=$(dirname "$reldir")
    outdir="$output"/"$dir"
    outfile="$outdir"/"$name.m4a"

    if [ ! -f "$outfile" ]; then
        echo "$name" "------" "$outfile"
        mkdir -p "$outdir"
        ffmpeg -i "$i" -n -loglevel 24 -c:a aac -b:a 128k -vcodec copy "$outfile"
        copyTags --replace "$i" "$outfile"
        touch -r "$i" "$outfile"
    #else
        #echo "Skipping $i"
    fi

    if [ -e "$cover" ]; then
        #art=`/srv/home/kolding/dev/MusicUtils/hasArt.py "$outfile"`
        art=`mediainfo "$outfile" | grep -i -c "cover.*yes"`
        if [ $art == "0" ]; then
            temp=$(mktemp)
            echo "Adding cover art to $outfile $cover"
            convert "$cover" -resize "300x>" $temp
            touch -r "$outfile" "$temp"
            mp4art -q --add "$temp" "$outfile"
            touch -r "$temp" "$outfile"
            rm -f "$temp"
        fi
    fi
}

export -f doConvert

parallel -j 12 doConvert ::: $(find $base -name \*$suffix -and -not -name ._\* | sort)
