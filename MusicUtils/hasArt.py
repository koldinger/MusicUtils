#! /usr/bin/env python

import sys
from pymediainfo import MediaInfo
import pprint

sys.argv.pop(0)

multiple = len(sys.argv) > 1

for i in sys.argv:
    try:
        info = MediaInfo.parse(i)
        art = info.general_tracks[0].to_data().get('cover', 'No')
        art = art.split('/')[0].strip()
        if multiple:
            print(f"{art:4} : {i}")
        else:
            print(art)
    except Exception as e:
        print(f"Exception: {e}")


