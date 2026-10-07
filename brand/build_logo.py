"""Builds the logo files from mark.svg and the wordmark "DASHBOARD: AI TOKENS" in Nunito Black, turned into
outlines so the logo needs no font. Needs fontTools; run in a throwaway container:

  python3 build_logo.py Nunito-Variable.ttf mark.svg out/
writes out/logo.svg (dark ink, for light backgrounds), out/logo-light.svg (for dark backgrounds),
out/wordmark-path.txt (path data + width, used by the social image).
"""
import re
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

TEXT = "DASHBOARD: AI TOKENS"
INK_DARK = "#2a2346"   # --ink (light scheme)
INK_LIGHT = "#f1edff"  # --ink (dark scheme)


def wordmark(font_path, size):
    font = TTFont(font_path)
    if "fvar" in font:
        font = instantiateVariableFont(font, {"wght": 900})
    upm = font["head"].unitsPerEm
    scale = size / upm
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]
    asc = font["hhea"].ascent * scale
    pen = SVGPathPen(glyphs)
    x = 0.0
    for ch in TEXT:
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, asc)))
        x += hmtx[name][0] * scale
    return pen.getCommands(), x, asc, font["hhea"].descent * scale


def main(font_path, mark_path, out):
    mark = open(mark_path).read()
    inner = re.search(r"<svg[^>]*>(.*)</svg>", mark, re.S).group(1)
    inner = re.sub(r"<title>.*?</title>", "", inner, flags=re.S)
    size = 44                       # cap height lines up with the 64px mark
    d, width, asc, desc = wordmark(font_path, size)
    text_h = asc - desc
    gap = 14
    W = round(64 + gap + width + 2)
    H = 64
    ty = (H - text_h) / 2
    for name, ink in (("logo.svg", INK_DARK), ("logo-light.svg", INK_LIGHT)):
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
               f'role="img" aria-label="DASHBOARD: AI TOKENS">\n  <title>DASHBOARD: AI TOKENS</title>\n'
               f'  <g>{inner}</g>\n'
               f'  <path transform="translate({64 + gap} {ty:.2f})" fill="{ink}" d="{d}"/>\n</svg>\n')
        open(f"{out}/{name}", "w").write(svg)
    open(f"{out}/wordmark-path.txt", "w").write(f"{width:.2f} {text_h:.2f}\n{d}\n")
    print("logo", W, "x", H, "wordmark width", round(width, 1))


if __name__ == "__main__":
    main(*sys.argv[1:4])
