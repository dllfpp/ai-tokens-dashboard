"""Argilla: claymorphism. New tokens as clay pebbles that grow from the hour to the month.
Main figure everywhere: new tokens (input + cache write + output). Cache reads, the history sent
again on every call, are shown beside it as re-reads."""
from tokendash.caveman import BEFORE_DAYS
from tokendash.query import PROJECT_WINDOWS
from tokendash.fmt import (CLOUDCLI_URL, GRAIN_NAMES, KIND, SIGNATURE, SORTS, TOKEN_NOTE, bar_chart, change, clock, count,
                           esc, legend, project_colors, reread, share, split, tokens, when)

FONTS = ("https://fonts.googleapis.com/css2?family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700"
         "&family=Nunito:wght@700;800;900&display=swap")

NAME = "DASHBOARD: AI TOKENS"
DESCRIPTION = "Claude Code tokens per project and conversation, by hour, day, week and month."


def shell(title, u, body, description=DESCRIPTION):
    full = NAME if title == NAME else f"{title} - {NAME}"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60"><title>{esc(full)}</title>
<meta name="description" content="{esc(description)}">
<link rel="canonical" href="{u.canonical()}">
<link rel="icon" href="{u.asset("favicon.svg")}" type="image/svg+xml">
<link rel="icon" href="{u.asset("favicon.ico")}" sizes="16x16 32x32 48x48">
<link rel="icon" href="{u.asset("favicon-32.png")}" type="image/png" sizes="32x32">
<link rel="apple-touch-icon" href="{u.asset("apple-touch-icon.png")}" sizes="180x180">
<link rel="manifest" href="{u.asset("site.webmanifest")}">
<meta name="theme-color" content="#e7e3f4" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#231e36" media="(prefers-color-scheme: dark)">
<meta name="application-name" content="{NAME}"><meta name="apple-mobile-web-app-title" content="AI TOKENS">
<meta property="og:type" content="website"><meta property="og:site_name" content="{NAME}">
<meta property="og:title" content="{esc(full)}"><meta property="og:description" content="{esc(description)}">
<meta property="og:url" content="{u.canonical()}">
<meta property="og:image" content="{u.asset("og.png", absolute=True)}">
<meta property="og:image:type" content="image/png"><meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{NAME}: {esc(DESCRIPTION)}">
<meta name="twitter:card" content="summary_large_image"><meta name="twitter:title" content="{esc(full)}">
<meta name="twitter:description" content="{esc(description)}">
<meta name="twitter:image" content="{u.asset("og.png", absolute=True)}">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link rel="stylesheet" href="{FONTS}">
<link rel="stylesheet" href="{u.css}"></head><body><div class="page">{body}
<footer><p>{esc(TOKEN_NOTE)}</p>{SIGNATURE}</footer></div></body></html>"""


def brand(u, tag="h1"):
    """The mark (64x64 source, shown at 44px) next to the name, linking home."""
    return (f'<{tag} class="brand"><a href="{esc(u.base)}"><img src="{u.asset("favicon.svg")}" width="44" height="44" alt="">'
            f'<span>{NAME}</span></a></{tag}>')


def pebbles(ctx):
    out = []
    for i, h in enumerate(ctx["headline"]):
        cur, prev = h["cur"], h["prev"]
        txt, d = change(cur["new"], prev["new"])
        out.append(f'<li class="pebble s{i}"><span class="ttl">{h["title"]}</span>'
                   f'<strong title="{count(cur["new"])} new tokens">{tokens(cur["new"])}</strong>'
                   f'<span class="tok">{count(cur["new"])} new tokens<br>{split(cur)}, {count(cur["calls"])} calls'
                   f'<br><span class="rr">{reread(cur)}</span></span>'
                   f'<span class="chg {d}">{txt} <small>{h["prev_title"]} {tokens(prev["new"])}</small></span></li>')
    return '<ol class="pebbles">' + "".join(out) + "</ol>"


def grain_switch(ctx, u):
    return '<nav class="grains" aria-label="Group by">' + "".join(
        f'<a href="{u.home(g=g)}"{" aria-current=page" if g == ctx["grain"] else ""}>{name}</a>'
        for g, name in GRAIN_NAMES) + "</nav>"


def cc_link(s, u, text="CloudCLI"):
    """Link that opens the conversation in CloudCLI, where it can be continued."""
    if not s.get("cc_id") or not CLOUDCLI_URL:
        return ""
    return f'<a class="cc" href="{u.cloudcli(s["cc_id"])}" title="Open in CloudCLI">{esc(text)}</a> '


def latest_line(p, u):
    """Under a project: its most recent conversation, by its CloudCLI name, linked to CloudCLI."""
    x = p.get("latest")
    if not x:
        return ""
    name = esc(x["title"])
    if x["cc_id"] and CLOUDCLI_URL:
        name = f'<a class="cc" href="{u.cloudcli(x["cc_id"])}" title="Open in CloudCLI">{name}</a>'
    return f'<span class="latest">Latest: {name}</span>'


def window_switch(ctx, u):
    """Project list window. "Chart" follows the chart period (and a clicked bar)."""
    names = {"today": "Today so far", "24h": "24h", "48h": "48h", "7d": "7 days", "30d": "30 days"}
    opts = [(None, "Chart")] + [(k, names[k]) for k, _ in PROJECT_WINDOWS]
    return '<nav class="sorts" aria-label="Project window">' + "".join(
        f'<a href="{u.home(pw=k)}#projects"{" aria-current=page" if k == ctx["pw"] else ""} '
        f'title="{esc(dict(PROJECT_WINDOWS).get(k, "Same period as the chart"))}">{name}</a>'
        for k, name in opts) + "</nav>"


def sort_switch(ctx, u):
    return '<nav class="sorts" aria-label="Sort by">' + "".join(
        f'<a href="{u.home(sort=s)}#conversations"{" aria-current=page" if s == ctx["sort"] else ""}>{name}</a>'
        for s, name in SORTS) + "</nav>"


def pct(part, whole):
    return f"{part / whole * 100:.1f}%" if whole else "0%"


def caveman_pebbles(c):
    """Four readings: proxy saving, its share, output per call before, output per call after."""
    p, s = c["proxy"], c["skill"]
    b, a = s["before"], s["after"]
    if s["change"] is None:
        chg, d = "no calls since the switch-on yet", "flat"
    else:
        chg, d = change(a["out_per_call"], b["out_per_call"])
    return f"""<ol class="pebbles cave">
<li class="pebble s3"><span class="ttl">Proxy removed</span><strong title="{count(p["saved"])} tokens">{tokens(p["saved"])}</strong>
<span class="tok">{count(p["saved"])} input tokens<br>{pct(p["saved"], p["before"])} of {tokens(p["before"])} sent</span></li>
<li class="pebble s2"><span class="ttl">Requests measured</span><strong>{count(p["measured"])}</strong>
<span class="tok">{count(p["compressed"])} compressed, {count(p["too_large"] + p["uncounted"])} not counted</span></li>
<li class="pebble s1"><span class="ttl">Output per call, before</span><strong>{count(round(b["out_per_call"]))}</strong>
<span class="tok">{count(b["calls"])} calls in the {BEFORE_DAYS} days before</span></li>
<li class="pebble s0"><span class="ttl">Output per call, after</span><strong>{count(round(a["out_per_call"]))}</strong>
<span class="tok">{count(a["calls"])} calls since the switch-on</span><span class="chg {d}">{chg}</span></li></ol>"""


def caveman_block(c, u):
    """Overview summary, links to the full page."""
    if c is None:
        return ""
    return f"""<section class="tray cave-tray"><div class="tray-head"><h2>Caveman savings <small>since {clock(c["since"])}</small></h2>
<p>The proxy trims what is sent to Claude, the skill makes Claude write less. <a href="{esc(u.base)}caveman">See how</a></p></div>
{caveman_pebbles(c)}</section>"""


def overview(ctx, u, cav=None):
    slots = project_colors(ctx["top_projects"])
    scope = ctx["scope"]
    filt = ""
    if ctx["project"]:
        filt = (f'<p class="filter">Only <b>{esc(ctx["project_label"])}</b>. '
                f'<a href="{u.home(p=None)}">Show every project</a></p>')
    if ctx["at"]:
        filt += (f'<p class="filter">Tables show <b>{esc(ctx["scope_label"])}</b>. '
                 f'<a href="{u.home(at=None)}">Back to the whole range</a></p>')

    projects = "".join(
        f'<li><a href="{u.home(p=None if ctx["project"] else p["project"])}">'
        f'<i class="sw {slots.get(p["project"], "p6")}"></i><span class="name">{esc(p["label"])}</span>'
        f'<span class="fill"><span class="{slots.get(p["project"], "p6")}" style="width:{share(p["new"], ctx["projects_total"]):.1f}%"></span></span>'
        f'<span class="num" title="{count(p["new"])} new tokens">{tokens(p["new"])}</span>'
        f'<span class="sub">{p["sessions"]} conv., {split(p)}, {reread(p)}</span></a>{latest_line(p, u)}</li>'
        for p in ctx["projects"]) or '<li class="none">Nothing used in this period.</li>'

    rows = "".join(
        f'<tr><td class="t"><a href="{u.session(s["session_id"])}">{esc(s["title"])}</a>'
        f'<span>{cc_link(s, u)}{esc(", ".join(s["projects"]))}, {KIND.get(s["kind"], s["kind"])}'
        f'{", " + str(s["agents"]) + " subagents" if s["agents"] else ""}</span></td>'
        f'<td class="n">{tokens(s["out"])}</td><td class="n rr">{tokens(s["cr"])}</td>'
        f'<td class="n when">{when(s["last_ts"])}</td>'
        f'<td class="n big" title="{count(s["new"])} new tokens">{tokens(s["new"])}</td></tr>'
        for s in ctx["sessions"])
    more = ctx["n_sessions"] - len(ctx["sessions"])

    models = "".join(
        f'<li><b>{esc(m["name"])}</b><span title="{count(m["new"])} new tokens">{tokens(m["new"])}</span>'
        f'<small>{split(m)}, {reread(m)}, {count(m["calls"])} calls</small></li>'
        for m in ctx["models"])

    g = ctx["grain"]
    body = f"""
<header class="top">{brand(u)}{grain_switch(ctx, u)}</header>
{pebbles(ctx)}
<section class="tray chart-tray">
  <div class="tray-head"><h2>{esc(ctx["scope_label"] if not ctx["at"] else ctx["window_label"])}</h2>
  <p>{tokens(ctx["total"])} new tokens in total, busiest {g} {tokens(ctx["peak"])}, active {g}s average {tokens(ctx["avg"])}. Tap a bar to see just that {g}.</p></div>
  {bar_chart(ctx, u, height=200, gap=0.28)}
  <ul class="legend">{legend(ctx)}</ul>
</section>
{caveman_block(cav, u)}
{filt}
<div class="split">
<section class="slab" id="projects"><div class="slab-head"><h2>Projects <small>{esc(ctx["projects_label"] or ctx["scope_label"])}</small></h2>{window_switch(ctx, u)}</div><ul class="projects">{projects}</ul></section>
<section class="slab models"><h2>Models</h2><ul>{models}</ul>
<p class="tot"><b>{count(scope["new"])}</b> new tokens over {count(scope["calls"])} calls<br>{split(scope)}<br>
plus {count(scope["cr"])} re-read from cache</p></section>
</div>
<section class="tray convs" id="conversations"><div class="tray-head"><h2>Conversations <small>{ctx["n_sessions"]} in {esc(ctx["scope_label"].lower() if not ctx["at"] else ctx["scope_label"])}</small></h2>{sort_switch(ctx, u)}</div>
<div class="scroll conv-list"><table><thead><tr><th>Conversation</th><th class="n">Output</th><th class="n">Re-read</th><th class="n">Last active</th><th class="n">New tokens</th></tr></thead>
<tbody>{rows or '<tr><td colspan=5 class="none">No conversations in this period.</td></tr>'}</tbody></table></div>
</section>"""
    return shell(NAME, u, body)


def session(s, u):
    t = s["total"]
    hourly = len(s["days"]) <= 2
    rows_src = s["hours"] if hourly else s["days"]
    peak = max((d["new"] for d in rows_src), default=0) or 1
    timeline = "".join(
        f'<li><span class="d">{esc(d["long"])}</span><span class="fill"><span class="p3" style="width:{d["new"] / peak * 100:.1f}%"></span></span>'
        f'<span class="num" title="{count(d["new"])} new tokens, {count(d["cr"])} re-read">{tokens(d["new"])}</span></li>'
        for d in rows_src)
    agents = "".join(
        f'<tr><td class="t">{esc(a["label"])}<span>{"main thread" if a["main"] else esc(a["agent_type"] or "subagent")}</span></td>'
        f'<td class="n">{count(a["calls"])}</td><td class="n">{tokens(a["out"])}</td><td class="n rr">{tokens(a["cr"])}</td>'
        f'<td class="n big" title="{count(a["new"])} new tokens">{tokens(a["new"])}</td></tr>'
        for a in s["agents"])
    chips = "".join(f'<li><b>{esc(p["label"])}</b> {tokens(p["new"])}</li>' for p in s["projects"])
    models = "".join(f'<li><b>{esc(m["name"])}</b> {tokens(m["new"])}</li>' for m in s["models"])
    body = f"""
<header class="top">{brand(u, "div")}</header>
<section class="slab hero-s"><h1>{esc(s["title"])}</h1>
<p>{KIND.get(s["kind"], s["kind"])}, {clock(s["first_ts"])} to {clock(s["last_ts"])}, {count(t["calls"])} calls</p>
{f'<p class="cc-open">{cc_link(s, u, "Open this conversation in CloudCLI")}</p>' if s.get("cc_id") and CLOUDCLI_URL else ""}
<ol class="pebbles mini"><li class="pebble s3"><span class="ttl">New tokens</span><strong title="{count(t["new"])} new tokens">{tokens(t["new"])}</strong><span class="tok">{count(t["new"])}</span></li>
<li class="pebble s2"><span class="ttl">Output</span><strong>{tokens(t["out"])}</strong><span class="tok">{count(t["out"])} written by Claude</span></li>
<li class="pebble s1"><span class="ttl">Input</span><strong>{tokens(t["inp"] + t["cw"])}</strong><span class="tok">{count(t["inp"] + t["cw"])} added to the chat</span></li>
<li class="pebble s0 rr"><span class="ttl">Re-read</span><strong>{tokens(t["cr"])}</strong><span class="tok">from cache: history sent again on each call</span></li></ol>
<div class="chips"><ul>{chips}</ul><ul>{models}</ul></div></section>
<section class="tray"><div class="tray-head"><h2>{"Hour by hour" if hourly else "Day by day"} <small>new tokens</small></h2></div><ul class="days">{timeline}</ul></section>
<section class="tray agents"><div class="tray-head"><h2>Main thread and subagents</h2></div><div class="scroll"><table>
<thead><tr><th>Who</th><th class="n">Calls</th><th class="n">Output</th><th class="n">Re-read</th><th class="n">New tokens</th></tr></thead><tbody>{agents}</tbody></table></div></section>"""
    return shell(s["title"], u, body)


def caveman_page(c, u):
    if c is None:
        body = f"""<header class="top">{brand(u, "div")}</header>
<section class="slab hero-s"><h1>Caveman savings</h1><p>No caveman proxy data on this machine
(~/.caveman/caveman.db is missing or empty). Turn the proxy on, then this page fills itself.</p></section>"""
        return shell("Caveman savings", u, body)
    p, s = c["proxy"], c["skill"]
    b, a = s["before"], s["after"]
    peak = max((d["out_per_call"] for d in s["days"]), default=0) or 1
    days = "".join(
        f'<li><span class="d">{esc(d["day"])} {"after" if d["after"] else "before"}<small>{count(d["calls"])} calls</small></span>'
        f'<span class="fill"><span class="{"p2" if d["after"] else "p6"}" style="width:{d["out_per_call"] / peak * 100:.1f}%"></span></span>'
        f'<span class="num">{count(round(d["out_per_call"]))}</span></li>' for d in s["days"])
    pdays = "".join(
        f'<li><span class="d">{esc(d["day"])}<small>{count(d["requests"])} requests</small></span>'
        f'<span class="fill"><span class="p3" style="width:{share(d["saved"], d["before"]):.1f}%"></span></span>'
        f'<span class="num" title="{count(d["before"])} before, {count(d["after"])} after">{tokens(d["saved"])}</span></li>'
        for d in c["days"])
    rows = "".join(
        f'<tr><td class="t">{f"""<a href="{u.session(x["session_id"])}">{esc(x["title"])}</a>""" if x["session_id"] else esc(x["title"])}'
        f'<span>{esc(x["project"])}</span></td><td class="n">{count(x["requests"])}</td>'
        f'<td class="n rr">{tokens(x["before"])}</td><td class="n">{pct(x["saved"], x["before"])}</td>'
        f'<td class="n big" title="{count(x["saved"])} tokens">{tokens(x["saved"])}</td></tr>'
        for x in c["sessions"])
    compress = (f'{count(p["compressed"])} requests had a block compressed: {count(p["cbefore"])} tokens became '
                f'{count(p["cafter"])}.' if p["compressed"] else "No request has had a block compressed yet.")
    body = f"""<header class="top">{brand(u, "div")}</header>
<section class="slab hero-s"><h1>Caveman savings</h1>
<p>On since {clock(c["since"])}. Two separate effects, measured in two different ways.</p>
{caveman_pebbles(c)}</section>
<div class="split cave-split">
<section class="slab"><h2>Proxy: what is sent to Claude</h2>
<p class="tot">Every request goes through the caveman proxy on 127.0.0.1:8787. It counts the request in tokens,
rewrites it (long tool output compressed, recoverable on demand), and counts it again. Measured, not estimated.</p>
<p class="cave-big"><b>{count(p["before"])}</b> tokens arrived, <b>{count(p["after"])}</b> went out,
<b>{count(p["saved"])}</b> removed ({pct(p["saved"], p["before"])}).</p>
<p class="tot">{compress} Not counted: {count(p["too_large"])} of {count(p["requests"])} requests were too big for the
proxy to measure and went through unchanged{f', {count(p["uncounted"])} {"was" if p["uncounted"] == 1 else "were"} rewritten but the count failed, so that saving is missing here' if p["uncounted"] else ""}.
Most of a request is history Claude has already cached, so a small
share here still means whole blocks of tool output that were never sent.</p>
<h3>Day by day <small>tokens removed, bar = share of what arrived</small></h3><ul class="days">{pdays}</ul></section>
<section class="slab"><h2>Skill: what Claude writes</h2>
<p class="tot">The caveman voice makes answers shorter. Nothing can show what the same answer would have been
without it, so this compares output tokens per call before and after the switch-on. Different work writes
different amounts: read it as a trend, and trust it more as calls pile up. claude-mem notes are left out.</p>
<p class="cave-big"><b>{count(round(b["out_per_call"]))}</b> output tokens per call before,
<b>{count(round(a["out_per_call"]))}</b> after.</p>
<p class="tot">Before: {count(b["calls"])} calls in the {BEFORE_DAYS} days up to the switch-on. After: {count(a["calls"])} calls.
New tokens per call {count(round(b["new_per_call"]))} before, {count(round(a["new_per_call"]))} after: that also counts
files and command output read, which depends on the task more than on caveman.</p>
<h3>Output per call <small>grey before, green after</small></h3><ul class="days">{days}</ul></section>
</div>
<section class="tray convs"><div class="tray-head"><h2>Proxy savings by conversation</h2></div>
<div class="scroll"><table><thead><tr><th>Conversation</th><th class="n">Requests</th><th class="n">Arrived</th><th class="n">Share</th><th class="n">Removed</th></tr></thead>
<tbody>{rows}</tbody></table></div></section>"""
    return shell("Caveman savings", u, body)
