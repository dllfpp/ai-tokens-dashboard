"""Aggregations the pages are rendered from. Everything is in Central European Time."""
import time
from datetime import timedelta

from .store import buckets, model_name, now_local

GRAINS = {
    # column, how many buckets the chart shows, step back one bucket
    "hour": ("hour", 48),
    "day": ("day", 31),
    "week": ("week", 12),
    "month": ("month", 12),
}

TOK = ("sum(input) AS inp, sum(output) AS out, sum(cache_w5m + cache_w1h) AS cw, "
       "sum(cache_read) AS cr, sum(cost) AS cost, count(*) AS calls")

PROJECT_LABELS = {"~": "home (~)", "claude-mem": "claude-mem notes"}


def project_label(p):
    return PROJECT_LABELS.get(p, p)


def _tok(r):
    d = {k: (r[k] or 0) for k in ("inp", "out", "cw", "cr", "cost", "calls")}
    d["tokens"] = d["inp"] + d["out"] + d["cw"] + d["cr"]
    d["new"] = d["inp"] + d["out"] + d["cw"]  # what was actually added; cache reads are re-reads
    return d


def bucket_keys(grain, n, now):
    keys = []
    if grain == "hour":
        for i in range(n):
            keys.append(buckets(now - timedelta(hours=i))[0])
    elif grain == "day":
        for i in range(n):
            keys.append(buckets(now - timedelta(days=i))[1])
    elif grain == "week":
        for i in range(n):
            keys.append(buckets(now - timedelta(weeks=i))[2])
    else:
        y, m = now.year, now.month
        for _ in range(n):
            keys.append(f"{y}-{m:02d}")
            y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return keys[::-1]


MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
DAYS = "Mon Tue Wed Thu Fri Sat Sun".split()


def bucket_label(grain, key):
    """(short label for an axis, long label for a heading)"""
    from datetime import date
    if grain == "hour":
        d = date.fromisoformat(key[:10])
        return key[11:] + ":00", f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}, {key[11:]}:00–{key[11:]}:59"
    if grain == "day":
        d = date.fromisoformat(key)
        return f"{d.day}", f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"
    if grain == "week":
        y, w = int(key[:4]), int(key[6:])
        mon = date.fromisocalendar(y, w, 1)
        sun = mon + timedelta(days=6)
        return f"W{w}", f"Week {w}, {mon.day} {MONTHS[mon.month - 1]} to {sun.day} {MONTHS[sun.month - 1]}"
    y, m = int(key[:4]), int(key[5:])
    return MONTHS[m - 1], f"{MONTHS[m - 1]} {y}"


def window_label(grain, keys):
    """Short span of the chart, e.g. '20 Jul to 11 Oct 2026'."""
    from datetime import date
    if grain == "hour":
        a, b = date.fromisoformat(keys[0][:10]), date.fromisoformat(keys[-1][:10])
        return f"{a.day} {MONTHS[a.month - 1]} {keys[0][11:]}:00 to {b.day} {MONTHS[b.month - 1]} {keys[-1][11:]}:59"
    if grain == "month":
        return f"{bucket_label(grain, keys[0])[1]} to {bucket_label(grain, keys[-1])[1]}"
    if grain == "week":
        a = date.fromisocalendar(int(keys[0][:4]), int(keys[0][6:]), 1)
        b = date.fromisocalendar(int(keys[-1][:4]), int(keys[-1][6:]), 7)
    else:
        a, b = date.fromisoformat(keys[0]), date.fromisoformat(keys[-1])
    return f"{a.day} {MONTHS[a.month - 1]} to {b.day} {MONTHS[b.month - 1]} {b.year}"


def session_title(r):
    for k in ("cc_name", "job_name", "custom_title", "agent_name", "ai_title", "first_prompt"):
        if r[k]:
            return r[k]
    return r["session_id"][:8]


def _where(project=None, grain=None, key=None, keys=None, session=None):
    w, a = [], []
    if project:
        w.append("grp = ?"); a.append(project)
    if session:
        w.append("session_id = ?"); a.append(session)
    if grain and key:
        w.append(f"{GRAINS[grain][0]} = ?"); a.append(key)
    elif grain and keys:
        w.append(f"{GRAINS[grain][0]} BETWEEN ? AND ?"); a += [keys[0], keys[-1]]
    return (" WHERE " + " AND ".join(w)) if w else "", a


def headline(db, project=None):
    """Fixed totals: this hour, today, this week, this month, with the previous one."""
    now = now_local()
    out = []
    for grain, title, prev_title in (("hour", "This hour", "previous hour"), ("day", "Today", "yesterday"),
                                     ("week", "This week", "last week"), ("month", "This month", "last month")):
        prev, cur = bucket_keys(grain, 2, now)
        rows = {}
        for k in (cur, prev):
            w, a = _where(project, grain, k)
            rows[k] = _tok(db.execute(f"SELECT {TOK} FROM calls{w}", a).fetchone())
        out.append({"grain": grain, "title": title, "prev_title": prev_title, "key": cur,
                    "cur": rows[cur], "prev": rows[prev]})
    return out


NEW = "input + output + cache_w5m + cache_w1h"
SORT_SQL = {"new": "inp+out+cw", "output": "out", "calls": "calls", "recent": "last_ts"}


PROJECT_WINDOWS = (("today", "Today so far"), ("24h", "Last 24 hours"), ("48h", "Last 48 hours"),
                   ("7d", "Last 7 days"), ("30d", "Last 30 days"))


def window_start(pw):
    """Epoch where a project window starts; today = local midnight."""
    now = now_local()
    if pw == "today":
        return time.time() - (now.hour * 3600 + now.minute * 60 + now.second)
    return time.time() - {"24h": 1, "48h": 2, "7d": 7, "30d": 30}[pw] * 86400


def overview(db, grain="day", at=None, project=None, sort="new", pw=None):
    grain = grain if grain in GRAINS else "day"
    col, n = GRAINS[grain]
    now = now_local()
    keys = bucket_keys(grain, n, now)
    if at not in keys:
        at = None

    w, a = _where(project, grain, keys=keys)
    by_key = {r[col]: _tok(r) for r in db.execute(f"SELECT {col}, {TOK} FROM calls{w} GROUP BY {col}", a)}
    split = {}
    for r in db.execute(f"SELECT {col} AS k, grp AS project, sum({NEW}) AS new FROM calls{w} GROUP BY 1, 2", a):
        split.setdefault(r["k"], {})[r["project"]] = r["new"]
    empty = _tok({k: 0 for k in ("inp", "out", "cw", "cr", "cost", "calls")})
    series = []
    for k in keys:
        short, long_ = bucket_label(grain, k)
        series.append({"key": k, "short": short, "long": long_, "current": k == keys[-1],
                       **by_key.get(k, empty), "by_project": split.get(k, {})})

    sw, sa = _where(project, grain, key=at) if at else (w, a)
    scope = _tok(db.execute(f"SELECT {TOK} FROM calls{sw}", sa).fetchone())
    sort = {"tokens": "new"}.get(sort, sort)
    sort = sort if sort in SORT_SQL else "new"
    order = SORT_SQL[sort]

    # the project list can look at its own window instead of the chart's
    pw = pw if pw in dict(PROJECT_WINDOWS) else None
    if pw:
        pww, pwa = _where(project)
        pww = (pww + " AND " if pww else " WHERE ") + "ts >= ?"
        pwa = pwa + [window_start(pw)]
    else:
        pww, pwa = sw, sa
    projects = [dict(project=r["project"], label=project_label(r["project"]), sessions=r["sessions"],
                     last_ts=r["last_ts"], **_tok(r))
                for r in db.execute(
                    f"SELECT grp AS project, count(DISTINCT session_id) AS sessions, max(ts) AS last_ts, {TOK} "
                    f"FROM calls{pww} GROUP BY grp ORDER BY {order} DESC", pwa)]
    projects_total = sum(p["new"] for p in projects)
    # each project's most recent conversation, to name it and open it in CloudCLI
    latest = {}
    for r in db.execute(
            "SELECT c.grp, s.*, max(c.ts) FROM calls c JOIN sessions s USING(session_id) "
            f"{pww} GROUP BY c.grp", pwa):
        latest[r["grp"]] = {"session_id": r["session_id"], "title": session_title(r), "cc_id": r["cc_id"]}
    for p in projects:
        p["latest"] = latest.get(p["project"])

    sessions = []
    for r in db.execute(
            f"SELECT c.session_id, s.kind, s.cc_name, s.cc_id, s.job_name, s.custom_title, s.agent_name, s.ai_title, s.first_prompt, "
            f"min(c.ts) AS first_ts, max(c.ts) AS last_ts, group_concat(DISTINCT c.grp) AS projects, "
            f"count(DISTINCT c.agent_id) AS agents, {TOK} "
            f"FROM calls c LEFT JOIN sessions s USING(session_id){sw} "
            f"GROUP BY c.session_id ORDER BY {order} DESC", sa):
        sessions.append(dict(session_id=r["session_id"], title=session_title(r), cc_id=r["cc_id"], kind=r["kind"] or "chat",
                             projects=[project_label(p) for p in (r["projects"] or "").split(",")],
                             first_ts=r["first_ts"], last_ts=r["last_ts"], agents=r["agents"], **_tok(r)))
    n_sessions = db.execute(f"SELECT count(DISTINCT session_id) FROM calls{sw}", sa).fetchone()[0]

    models = [dict(model=r["model"], name=model_name(r["model"]), **_tok(r))
              for r in db.execute(f"SELECT model, {TOK} FROM calls{sw} GROUP BY model ORDER BY inp+out+cw DESC", sa)]

    window = {}
    for per in split.values():
        for p, c in per.items():
            window[p] = window.get(p, 0) + c
    top = sorted(window, key=lambda p: -window[p])[:6]
    active = [s for s in series if s["calls"]]
    return {
        "grain": grain, "at": at, "project": project, "project_label": project_label(project) if project else None,
        "sort": sort, "now": now, "keys": keys, "series": series,
        "peak": max((s["new"] for s in series), default=0),
        "avg": (sum(s["new"] for s in series) / len(active)) if active else 0,
        "total": sum(s["new"] for s in series),
        "window_label": window_label(grain, keys),
        "scope_label": bucket_label(grain, at)[1] if at else
        {"hour": "Last 48 hours", "day": "Last 31 days", "week": "Last 12 weeks", "month": "Last 12 months"}[grain],
        "scope": scope, "projects": projects, "pw": pw, "projects_total": projects_total,
        "projects_label": dict(PROJECT_WINDOWS)[pw] if pw else None, "sessions": sessions, "n_sessions": n_sessions,
        "models": models, "top_projects": top, "headline": headline(db, project),
        "all_projects": [r[0] for r in db.execute(f"SELECT grp FROM calls GROUP BY 1 ORDER BY sum({NEW}) DESC")],
        "since": db.execute("SELECT min(day) FROM calls").fetchone()[0],
    }


def session(db, sid):
    r = db.execute("SELECT * FROM sessions WHERE session_id = ?", (sid,)).fetchone()
    if not r:
        return None
    tot = _tok(db.execute(f"SELECT {TOK} FROM calls WHERE session_id = ?", (sid,)).fetchone())
    span = db.execute("SELECT min(ts), max(ts) FROM calls WHERE session_id = ?", (sid,)).fetchone()
    days = [dict(key=x["day"], short=bucket_label("day", x["day"])[0], long=bucket_label("day", x["day"])[1], **_tok(x))
            for x in db.execute(f"SELECT day, {TOK} FROM calls WHERE session_id = ? GROUP BY day ORDER BY day", (sid,))]
    hours = [dict(key=x["hour"], short=bucket_label("hour", x["hour"])[0], long=bucket_label("hour", x["hour"])[1], **_tok(x))
             for x in db.execute(f"SELECT hour, {TOK} FROM calls WHERE session_id = ? GROUP BY hour ORDER BY hour", (sid,))]
    projects = [dict(project=x["project"], label=project_label(x["project"]), **_tok(x))
                for x in db.execute(f"SELECT project, {TOK} FROM calls WHERE session_id = ? GROUP BY 1 ORDER BY inp+out+cw DESC", (sid,))]
    models = [dict(model=x["model"], name=model_name(x["model"]), **_tok(x))
              for x in db.execute(f"SELECT model, {TOK} FROM calls WHERE session_id = ? GROUP BY 1 ORDER BY inp+out+cw DESC", (sid,))]
    agents = [dict(agent_id=x["agent_id"], label=x["description"] or ("main conversation" if not x["agent_id"] else x["agent_id"]),
                   main=not x["agent_id"], agent_type=x["agent_type"], **_tok(x))
              for x in db.execute(
                  f"SELECT c.agent_id, a.description, a.agent_type, {TOK} FROM calls c LEFT JOIN agents a USING(agent_id) "
                  f"WHERE c.session_id = ? GROUP BY c.agent_id ORDER BY inp+out+cw DESC", (sid,))]
    return {"session_id": sid, "title": session_title(r), "cc_id": r["cc_id"], "kind": r["kind"] or "chat", "first_ts": span[0],
            "last_ts": span[1], "total": tot, "days": days, "hours": hours, "projects": projects,
            "models": models, "agents": agents,
            "peak": max((d["new"] for d in days), default=0)}
