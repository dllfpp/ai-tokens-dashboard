"""Caveman savings: what the caveman proxy and skill changed in token use.

Two separate measurements, never added together:
- Proxy: ~/.caveman/caveman.db (owned by the caveman proxy, opened read only). For every request it
  routed it records the request size in tokens before and after its rewrite; the difference is
  input it removed. Only rows with request_measurement_status = 'measured' carry both numbers.
- Skill: the caveman voice shortens what Claude writes. There is no counterfactual, so it is shown
  as output tokens per call before and after the switch-on (the proxy's first request), from the
  dashboard's own calls table. Different tasks write different amounts: a trend, not a proof.
"""
import os
import sqlite3
from datetime import datetime, timezone

from .query import project_label, session_title
from .store import to_local

CAVEMAN_DB = os.environ.get("CAVEMAN_DB", os.path.expanduser("~/.caveman/caveman.db"))
BEFORE_DAYS = 7          # baseline window for the skill comparison
NEW = "input + output + cache_w5m + cache_w1h"


def _open():
    if not os.path.exists(CAVEMAN_DB):
        return None
    db = sqlite3.connect(f"file:{CAVEMAN_DB}?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    return db


def _epoch(ts):
    """caveman.db stores UTC as 'YYYY-MM-DD HH:MM:SS.fff'."""
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).timestamp()


def _day(epoch):
    return to_local(datetime.fromtimestamp(epoch, timezone.utc)).strftime("%Y-%m-%d")


def proxy():
    db = _open()
    if db is None:
        return None
    try:
        rows = db.execute(
            "SELECT ts, session_id, request_measurement_status AS st, request_tokens_before AS rb, "
            "request_tokens_after AS ra, compression_tokens_before AS cb, compression_tokens_after AS ca, "
            "optimization_ids AS opt FROM requests ORDER BY id").fetchall()
    finally:
        db.close()
    if not rows:
        return None
    tot = {"requests": len(rows), "measured": 0, "before": 0, "after": 0, "compressed": 0,
           "cbefore": 0, "cafter": 0, "too_large": 0, "uncounted": 0}
    days, sessions = {}, {}
    for r in rows:
        if r["st"] != "measured" or not r["rb"]:
            tot["too_large" if r["st"] == "request_payload_too_large" else "uncounted"] += 1
            continue
        saved = r["rb"] - r["ra"]
        tot["measured"] += 1
        tot["before"] += r["rb"]
        tot["after"] += r["ra"]
        if "caveman-compression" in (r["opt"] or ""):
            tot["compressed"] += 1
            tot["cbefore"] += r["cb"] or 0
            tot["cafter"] += r["ca"] or 0
        for bucket, key in ((days, _day(_epoch(r["ts"]))), (sessions, (r["session_id"] or "").removeprefix("claude:"))):
            b = bucket.setdefault(key, {"requests": 0, "before": 0, "after": 0})
            b["requests"] += 1
            b["before"] += r["rb"]
            b["after"] += r["ra"]
    tot["saved"] = tot["before"] - tot["after"]
    for b in list(days.values()) + list(sessions.values()):
        b["saved"] = b["before"] - b["after"]
    return {"since": _epoch(rows[0]["ts"]), "total": tot,
            "days": [dict(day=k, **v) for k, v in sorted(days.items())],
            "sessions": sessions}


def skill(db, since):
    """Output and new tokens per call, BEFORE_DAYS before the switch-on against everything after.
    claude-mem notes are left out: a background note-taker, not a conversation with you."""
    start = since - BEFORE_DAYS * 86400
    q = (f"SELECT count(*) AS calls, sum(output) AS out, sum({NEW}) AS new FROM calls "
         f"WHERE project != 'claude-mem' AND ts >= ? AND ts < ?")
    out = {}
    for name, a, b in (("before", start, since), ("after", since, 1e12)):
        r = db.execute(q, (a, b)).fetchone()
        calls = r["calls"] or 0
        out[name] = {"calls": calls, "out": r["out"] or 0, "new": r["new"] or 0,
                     "out_per_call": (r["out"] or 0) / calls if calls else 0,
                     "new_per_call": (r["new"] or 0) / calls if calls else 0}
    b, a = out["before"]["out_per_call"], out["after"]["out_per_call"]
    out["change"] = (a - b) / b if b and out["after"]["calls"] else None
    # the switch-on day is split at the switch-on time, so no row mixes the two
    out["days"] = [{"day": r["day"], "after": bool(r["after"]), "calls": r["calls"],
                    "out_per_call": r["out"] / r["calls"]}
                   for r in db.execute(
                       "SELECT day, ts >= ? AS after, count(*) AS calls, sum(output) AS out FROM calls "
                       "WHERE project != 'claude-mem' AND ts >= ? GROUP BY 1, 2 ORDER BY 1, 2", (since, start))]
    return out


def summary(db):
    """Everything the caveman views need, or None when the proxy has never run here."""
    p = proxy()
    if p is None:
        return None
    s = skill(db, p["since"])
    titles = {}
    ids = [k for k in p["sessions"] if k]
    if ids:
        marks = ",".join("?" * len(ids))
        for r in db.execute(f"SELECT * FROM sessions WHERE session_id IN ({marks})", ids):
            titles[r["session_id"]] = session_title(r)
        proj = {r[0]: project_label(r[1]) for r in db.execute(
            f"SELECT session_id, project FROM calls WHERE session_id IN ({marks}) "
            f"GROUP BY session_id ORDER BY count(*)", ids)}
    else:
        proj = {}
    sess = sorted(({"session_id": k, "title": titles.get(k, "untracked requests" if not k else k[:8]),
                    "project": proj.get(k, ""), **v} for k, v in p["sessions"].items()),
                  key=lambda x: -x["saved"])
    return {"since": p["since"], "proxy": p["total"], "days": p["days"], "sessions": sess, "skill": s}
