"""Today's usage as a short Telegram message (HTML parse mode), for a bot button.

The dashboard owns the numbers and the wording; the bot only fetches /api/report/today and posts
the text as it is.
"""
from html import escape

from .fmt import change, count, tokens
from .query import bucket_keys, overview
from .store import now_local

TOP = 5


def today(db, public_url=""):
    now = now_local()
    day = bucket_keys("day", 1, now)[0]
    ctx = overview(db, "day", at=day, sort="new", pw="today")
    t = ctx["scope"]
    yday = next(h for h in ctx["headline"] if h["grain"] == "day")["prev"]
    txt, _ = change(t["new"], yday["new"])
    lines = [
        f"<b>📊 Token di oggi</b> (00:00–{now:%H:%M})",
        "",
        f"<b>{tokens(t['new'])}</b> token nuovi ({count(t['new'])})",
        f"input {tokens(t['inp'] + t['cw'])}, output {tokens(t['out'])}, {count(t['calls'])} chiamate",
        f"riletti dalla cache {tokens(t['cr'])}",
        f"ieri in tutto {tokens(yday['new'])} ({escape(txt)})" if yday["new"] else "ieri nessun uso",
    ]
    if ctx["projects"]:
        lines += ["", "<b>Progetti</b>"]
        lines += [f"• {escape(p['label'])}: {tokens(p['new'])}" for p in ctx["projects"][:TOP]]
        if len(ctx["projects"]) > TOP:
            rest = sum(p["new"] for p in ctx["projects"][TOP:])
            lines.append(f"• altri {len(ctx['projects']) - TOP}: {tokens(rest)}")
    if ctx["sessions"]:
        lines += ["", "<b>Conversazioni</b>"]
        lines += [f"• {escape(s['title'][:60])}: {tokens(s['new'])}" for s in ctx["sessions"][:TOP]]
    if not t["calls"]:
        lines = [lines[0], "", "Nessun uso da mezzanotte."]
    if public_url:
        lines += ["", f'<a href="{escape(public_url)}/?g=hour">Apri la dashboard</a>']
    return {"text": "\n".join(lines), "date": day, "new_tokens": t["new"]}
