"""The three plan-limit charts of the dashboard as one PNG, for the Telegram message.

Same drawing as the page: dashed line = the most you can use at an even pace (0% at the window's
start, 100% at the reset), solid line = used, dot = now, red when above the even pace.
Needs Pillow; fonts are looked up by name and fall back to Pillow's built-in one.
"""
import io
import os
from datetime import datetime, timezone

from PIL import Image, ImageDraw, ImageFont

from .limits import history, window
from .store import to_local

# Argilla tokens (tokendash/ui/style.css)
BG, CARD, WELL, INK, SOFT, LINE = "#e7e3f4", "#f5f2fc", "#dcd6ee", "#2a2346", "#5b5378", "#c9c1e2"
USED, OVER, OK = "#a993ee", "#b4304f", "#1f7a52"
FONTS = ["/usr/share/fonts/noto/NotoSans-{}.ttf", "/usr/share/fonts/dejavu/DejaVuSans-{}.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-{}.ttf"]
NAMES = {"session": "Session, 5 hours", "weekly_all": "Week, all models"}
S = 2  # drawn at twice the size, sharp on phones


def font(size, bold=False):
    for pattern in FONTS:
        path = pattern.format("Bold" if bold else "Regular").replace("DejaVuSans-Regular", "DejaVuSans")
        if os.path.exists(path):
            return ImageFont.truetype(path, size * S)
    return ImageFont.load_default()


def dashed(d, a, b, fill, width, dash=10, gap=8):
    (x1, y1), (x2, y2) = a, b
    length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** .5 or 1
    pos = 0.0
    while pos < length:
        e = min(pos + dash * S, length)
        d.line([(x1 + (x2 - x1) * pos / length, y1 + (y2 - y1) * pos / length),
                (x1 + (x2 - x1) * e / length, y1 + (y2 - y1) * e / length)], fill=fill, width=width)
        pos = e + gap * S


def card(d, box, lim, now):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=24 * S, fill=CARD)
    pad = 20 * S
    name = NAMES.get(lim["kind"]) or lim["name"].replace("Settimana", "Week,")
    d.text((x0 + pad, y0 + pad), name, font=font(15, True), fill=SOFT)
    pc = float(lim["percent"])
    d.text((x0 + pad, y0 + pad + 22 * S), f"{pc:.0f}%", font=font(34, True), fill=INK)
    w = window(lim)
    cx0, cy0, cx1, cy1 = x0 + pad, y0 + 92 * S, x1 - pad, y1 - 52 * S
    d.rounded_rectangle((cx0, cy0, cx1, cy1), radius=14 * S, fill=WELL)
    if not w:
        msg = "no active session" if lim["kind"] == "session" else "no reset known"
        f = font(14)
        d.text(((cx0 + cx1 - d.textlength(msg, font=f)) / 2, (cy0 + cy1) / 2 - 9 * S), msg, font=f, fill=SOFT)
        return
    start, reset = w
    span = (reset - start).total_seconds()

    def pt(at, p):
        x = cx0 + max(0.0, min((at - start).total_seconds() / span, 1.0)) * (cx1 - cx0)
        return x, cy1 - max(0.0, min(p, 100.0)) / 100 * (cy1 - cy0)

    d.line([(cx0, (cy0 + cy1) / 2), (cx1, (cy0 + cy1) / 2)], fill=LINE, width=S)
    dashed(d, (cx0, cy1), (cx1, cy0), SOFT, 2 * S)
    over = pc > (now - start).total_seconds() / span * 100
    col = OVER if over else USED
    pts = [pt(a, p) for a, p in history(lim)] + [pt(now, pc)]
    nx, ny = pts[-1]
    d.line([(nx, cy0), (nx, cy1)], fill=LINE, width=S)
    if len(pts) > 1:
        d.line(pts, fill=col, width=4 * S, joint="curve")
    r = 6 * S
    d.ellipse((nx - r, ny - r, nx + r, ny + r), fill=col)
    small = font(12)
    d.text((cx0, cy1 + 8 * S), to_local(start).strftime("%a %-d %b, %H:%M"), font=small, fill=SOFT)
    end = to_local(reset).strftime("%a %-d %b, %H:%M")
    d.text((cx1 - d.textlength(end, font=small), cy1 + 8 * S), end, font=small, fill=SOFT)
    d.text((cx0, cy1 + 28 * S), "above the even pace" if over else "within the even pace",
           font=font(13, True), fill=OVER if over else OK)


def render(limits):
    """PNG bytes with one card per limit, side by side."""
    now = datetime.now(timezone.utc)
    n = max(len(limits), 1)
    cw, ch, gap, margin = 330 * S, 330 * S, 16 * S, 20 * S
    img = Image.new("RGB", (margin * 2 + n * cw + (n - 1) * gap, margin * 2 + ch), BG)
    d = ImageDraw.Draw(img)
    for i, lim in enumerate(limits):
        x = margin + i * (cw + gap)
        card(d, (x, margin, x + cw, margin + ch), lim, now)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
