"""Packs PNG files into one .ico (PNG-compressed entries, supported by every current browser).
  python3 make_ico.py favicon.ico favicon-16.png favicon-32.png favicon-48.png"""
import struct
import sys


def png_size(data):
    return struct.unpack(">II", data[16:24])


def main(out, *pngs):
    blobs = [open(p, "rb").read() for p in pngs]
    head = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries = b""
    for b in blobs:
        w, h = png_size(b)
        entries += struct.pack("<BBBBHHII", w % 256, h % 256, 0, 0, 1, 32, len(b), offset)
        offset += len(b)
    open(out, "wb").write(head + entries + b"".join(blobs))


if __name__ == "__main__":
    main(*sys.argv[1:])
