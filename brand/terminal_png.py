"""Renders a captured terminal session as a PNG, for the README.

  python3 brand/terminal_png.py session.txt out.png "$ command shown on top"

Monospace text on a dark terminal background with a window bar; ✓ green, ✗ red, · grey,
numbered step titles bold. Needs Pillow and a monospace TrueType font (Noto Sans Mono or DejaVu).
"""
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = {False: ["/usr/share/fonts/noto/NotoSansMono-Regular.ttf", "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
         True: ["/usr/share/fonts/noto/NotoSansMono-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSansMono-Bold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"]}
BG, BAR, TEXT, DIM, GREEN, RED, STEP, PROMPT = "#1f1b2e", "#2c2742", "#e8e4f6", "#9a93b8", "#7fd3a4", "#ff8fa6", "#c9b8ff", "#f2c96a"
S, SIZE, LINE, PAD = 2, 14, 22, 24
# ✓ and ✗ are missing from most monospace fonts: drawn with a symbol font
SYMBOLS = ["/usr/share/fonts/noto/NotoSansSymbols2-Regular.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
           "/usr/share/fonts/dejavu/DejaVuSans.ttf"]


def font(bold):
    for path in FONTS[bold]:
        try:
            return ImageFont.truetype(path, SIZE * S)
        except OSError:
            continue
    return ImageFont.load_default()


def colour(line):
    t = line.strip()
    if t.startswith("✓"):
        return GREEN, False
    if t.startswith("✗"):
        return RED, False
    if t.startswith("·"):
        return DIM, False
    if t[:2] in {f"{i}." for i in range(1, 10)} or t.startswith("DASHBOARD:"):
        return STEP, True
    if t.startswith("$ "):
        return PROMPT, True
    return TEXT, False


def render(lines, out):
    regular, bold = font(False), font(True)
    symbol = next((ImageFont.truetype(p, SIZE * S) for p in SYMBOLS if __import__("os").path.exists(p)), regular)
    width = max(regular.getlength(l) for l in lines) + 2 * PAD * S
    height = (len(lines) * LINE + 2 * PAD + 30) * S
    img = Image.new("RGB", (int(width), height), BG)
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, width, 30 * S), fill=BAR)
    for i, c in enumerate(("#ff6b6b", "#f2c96a", "#7fd3a4")):
        x = (16 + i * 20) * S
        d.ellipse((x, 10 * S, x + 11 * S, 21 * S), fill=c)
    y = (30 + PAD) * S
    for line in lines:
        col, b = colour(line)
        f = bold if b else regular
        x = PAD * S
        for ch in line:
            use = symbol if ch in "✓✗" else f
            d.text((x, y), ch, font=use, fill=col)
            x += f.getlength(ch if ch not in "✓✗" else " ")
        y += LINE * S
    img.save(out, optimize=True)
    print(out, img.size)


if __name__ == "__main__":
    src, out = sys.argv[1], sys.argv[2]
    lines = [l.rstrip("\n") for l in open(src, encoding="utf-8")]
    if len(sys.argv) > 3:
        lines = [sys.argv[3], ""] + lines
    render(lines, out)
