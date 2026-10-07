"""Formatting and drawing helpers shared by every view."""
import html
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode, quote

from .store import to_local

esc = html.escape

# CloudCLI web address (e.g. https://cloudcli.example.com); empty = no "open in CloudCLI" links
CLOUDCLI_URL = os.environ.get("CLOUDCLI_URL", "").rstrip("/")

SIGNATURE = ('<a class="signature" href="https://buymeacoffee.com/dllfpp">'
             'Made with love ❤️ - DLLFPP</a>')

TOKEN_NOTE = ("New tokens are what each call adds: input (your messages, files read, command output, "
              "whether cached for later or not) and output (what Claude writes). Every call also sends "
              "the whole conversation again, read back from cache; those re-reads are shown apart because "
              "they repeat the same text and grow with the length of a chat, not with the work done. "
              "Counts come from the transcripts Claude Code writes, subagents included; side calls such "
              "as session titles never reach them.")


def money(x):
    x = x or 0
    if x >= 1000:
        return f"${x:,.0f}"
    if x >= 100:
        return f"${x:,.1f}"
    return f"${x:,.2f}"


def tokens(n):
    """Compact, three significant digits: 1.42B, 583M, 51.0M, 12.4k, 950."""
    n = n or 0
    for div, unit in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if n >= div:
            v = n / div
            return f"{v:.2f}{unit}" if v < 10 else f"{v:.1f}{unit}" if v < 100 else f"{v:.0f}{unit}"
    return str(int(n))


def count(n):
    """Exact, with thousands separators."""
    return f"{int(n or 0):,}"


def split(t):
    """What the new tokens of a row are made of, compact."""
    return f'{tokens(t["inp"] + t["cw"])} input, {tokens(t["out"])} output'


def reread(t):
    """The cache reads of a row: history sent again, not new work."""
    return f'{tokens(t["cr"])} re-read from cache'


def change(cur, prev):
    """(text, direction): '+40%', 'up' | '−12%', 'down' | ..., 'flat'."""
    if not prev:
        return ("nothing before" if cur else "no use", "flat")
    d = (cur - prev) / prev
    if abs(d) < 0.005:
        return ("unchanged", "flat")
    return (f"{'+' if d > 0 else '−'}{abs(d) * 100:.0f}%", "up" if d > 0 else "down")


def when(ts):
    if not ts:
        return ""
    age = time.time() - ts
    if age < 3600:
        return f"{max(1, int(age // 60))} min ago"
    if age < 86400:
        return f"{int(age // 3600)} h ago"
    return to_local(datetime.fromtimestamp(ts, timezone.utc)).strftime("%-d %b, %H:%M")


def clock(ts):
    return to_local(datetime.fromtimestamp(ts, timezone.utc)).strftime("%-d %b %Y, %H:%M") if ts else ""


KIND = {"job": "background job", "chat": "chat", "sdk": "SDK session", "notes": "claude-mem notes"}

GRAIN_NAMES = (("hour", "Hours"), ("day", "Days"), ("week", "Weeks"), ("month", "Months"))
SORTS = (("new", "New tokens"), ("output", "Output"), ("calls", "Calls"), ("recent", "Latest"))


class Links:
    """Links that keep the current filters. `base` is where the view is mounted."""

    def __init__(self, base, params, css_version="", asset_versions=None, public_url="", path="/"):
        self.base = base
        self.params = {k: v for k, v in params.items() if v}
        self.css = f"{base}style.css?v={css_version}"
        self.versions = asset_versions or {}
        self.public_url = public_url
        self.path = path

    def cloudcli(self, app_id):
        return esc(f"{CLOUDCLI_URL}/session/{quote(app_id)}")

    def asset(self, name, absolute=False):
        """A file from ui/static, versioned by content so it can be cached forever."""
        url = f"{self.base}static/{name}?v={self.versions.get(name, '')}"
        return esc(self.public_url + url if absolute else url)

    def canonical(self):
        return esc(self.public_url + self.path)

    def home(self, **change_):
        p = dict(self.params)
        for k, v in change_.items():
            if v is None:
                p.pop(k, None)
            else:
                p[k] = v
        if "g" in change_:
            p.pop("at", None)
        return esc(self.base + ("?" + urlencode(p) if p else ""))

    def session(self, sid):
        p = {k: v for k, v in self.params.items() if k == "g"}
        return esc(self.base + "s/" + quote(sid) + ("?" + urlencode(p) if p else ""))


def project_colors(top):
    """Stable colour slot per project: the top six get p0..p5, everything else p6."""
    return {p: f"p{i}" for i, p in enumerate(top)}


def bar_chart(ctx, u, height=220, gap=0.22, min_bar=1.5, label_every=None):
    """Bars stacked by project, one link per bucket (a click filters the tables to it).
    Markup: div.chart > svg (stretches to its box) + ol.axis (HTML labels placed in %).
    Classes: a.bar (.sel selected, .now current bucket), rect.hit, rect.seg.p0..p6, rect.empty."""
    series = ctx["series"]
    n = len(series)
    peak = ctx["peak"] or 1
    slots = project_colors(ctx["top_projects"])
    bw = 10 * (1 - gap)
    every = label_every or {"hour": 6, "day": 3, "week": 1, "month": 1}[ctx["grain"]]
    svg = [f'<svg viewBox="0 0 {n * 10} {height}" preserveAspectRatio="none" role="img" '
           f'aria-label="Tokens per {ctx["grain"]}, {esc(ctx["scope_label"])}">']
    axis = []
    for i, s in enumerate(series):
        x = i * 10 + (10 - bw) / 2
        cls = "bar" + (" sel" if s["key"] == ctx["at"] else "") + (" now" if s["current"] else "")
        href = u.home(at=None if s["key"] == ctx["at"] else s["key"])
        title = (f'{s["long"]}: {count(s["new"])} new tokens ({split(s)}), '
                 f'{count(s["cr"])} re-read from cache, {count(s["calls"])} calls')
        svg.append(f'<a class="{cls}" href="{href}"><title>{esc(title)}</title>'
                   f'<rect class="hit" x="{i * 10}" y="0" width="10" height="{height}"/>')
        if s["new"] <= 0:
            svg.append(f'<rect class="empty" x="{x:.2f}" y="{height - 1}" width="{bw:.2f}" height="1"/>')
        else:
            segs = sorted(s["by_project"].items(), key=lambda kv: slots.get(kv[0], "p9"))
            other = sum(c for p, c in segs if p not in slots)
            segs = [(slots[p], c) for p, c in segs if p in slots] + ([("p6", other)] if other else [])
            total_h = max(min_bar, s["new"] / peak * (height - 2))
            y = height
            for slot, c in segs:
                h = total_h * c / s["new"]
                if h > 0:
                    y -= h
                    svg.append(f'<rect class="seg {slot}" x="{x:.2f}" y="{y:.2f}" '
                               f'width="{bw:.2f}" height="{h:.2f}"/>')
        svg.append("</a>")
        if (i % every == 0 and n - 1 - i >= every / 2) or s["current"]:
            cur = ' class="now"' if s["current"] else ""
            axis.append(f'<li{cur} style="left:{(i + 0.5) / n * 100:.2f}%">{esc(s["short"])}</li>')
    svg.append("</svg>")
    return f'<div class="chart">{"".join(svg)}<ol class="axis" aria-hidden="true">{"".join(axis)}</ol></div>'


def legend(ctx):
    """<li> items, each with an <i class="sw pN"> swatch."""
    from .query import project_label
    slots = project_colors(ctx["top_projects"])
    items = [(slot, project_label(p)) for p, slot in slots.items()]
    if len(ctx["projects"]) > len(slots):
        items.append(("p6", "everything else"))
    return "".join(f'<li><i class="sw {s}"></i>{esc(label)}</li>' for s, label in items)


def share(part, whole):
    return 0 if not whole else max(0.0, min(100.0, part / whole * 100))
