#! /usr/bin/env python

import argparse
import math

parser = argparse.ArgumentParser("Generate numbers")
parser.add_argument("--hex", "-x", dest="hex", default=False, action='store_true', help="Generate number is hex")
parser.add_argument("--digits", "-d", dest="digits", type=int, default=1, help="Generate number of digits")
parser.add_argument("--format", "-f", dest='fmt', default=None, help='Use this format for printing digits')
parser.add_argument("lower", type=lambda x: int(x, 0), help="Lower bound")
parser.add_argument("upper", type=lambda x: int(x, 0), help="Upper bound")
parser.add_argument("increment", type=int, nargs='?', default=1, help="Upper bound")
args = parser.parse_args()

fmt='d'
if args.hex:
    fmt='X'
if args.digits:
    fmt=f"0{args.digits}{fmt}"
if args.fmt:
    fmt = args.fmt

for i in range(args.lower, args.upper + int(math.copysign(1, args.increment)), args.increment):
    print(f"{i:{fmt}}")
