"""Collector: reads Claude Code transcripts incrementally into SQLite.

Every assistant message in ~/.claude/projects/**/*.jsonl carries the API usage of
one call. Claude Code writes the same message several times while streaming, so a
call is identified by (message.id, requestId) and inserted once. Claude Code prunes
old transcripts; the database keeps the history.
"""
import functools
import glob
import json
import os
import sqlite3
import time
from datetime import datetime, timedelta, timezone

CLAUDE_DIR = os.environ.get("CLAUDE_DIR", os.path.expanduser("~/.claude"))
HOME = os.path.expanduser("~")

# USD per million tokens, Anthropic first-party list prices (claude-api skill, 2026-09-25).
# Cache writes: 5-minute TTL = 1.25x input, 1-hour TTL = 2x input. Fast mode = 2x.
PRICES = {
    "claude-fable-5-1": {"in": 10.0, "out": 50.0, "read": 0.25},
    "claude-fable-5": {"in": 10.0, "out": 50.0, "read": 1.0},
    "claude-mythos-5-1": {"in": 10.0, "out": 50.0, "read": 0.25},
    "claude-opus-5-5": {"in": 4.0, "out": 20.0, "read": 0.20},
    "claude-opus-5": {"in": 5.0, "out": 25.0, "read": 0.50},
    "claude-opus-4-8": {"in": 5.0, "out": 25.0, "read": 0.50},
    "claude-opus-4-7": {"in": 5.0, "out": 25.0, "read": 0.50},
    "claude-opus-4-6": {"in": 5.0, "out": 25.0, "read": 0.50},
    "claude-sonnet-5-5": {"in": 2.0, "out": 10.0, "read": 0.20},
    "claude-sonnet-5": {"in": 2.0, "out": 10.0, "read": 0.20},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0, "read": 0.30},
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0, "read": 0.10},
}

MODEL_NAMES = {
    "claude-fable-5-1": "Fable 5.1", "claude-fable-5": "Fable 5",
    "claude-mythos-5-1": "Mythos 5.1", "claude-opus-5-5": "Opus 5.5",
    "claude-opus-5": "Opus 5", "claude-opus-4-8": "Opus 4.8", "claude-opus-4-7": "Opus 4.7",
    "claude-opus-4-6": "Opus 4.6", "claude-sonnet-5-5": "Sonnet 5.5",
    "claude-sonnet-5": "Sonnet 5", "claude-sonnet-4-6": "Sonnet 4.6",
    "claude-haiku-4-5": "Haiku 4.5",
}


def model_key(model):
    m = (model or "").split("[")[0]
    for k in sorted(PRICES, key=len, reverse=True):
        if m == k or m.startswith(k + "-"):
            return k
    return m


def model_name(model):
    return MODEL_NAMES.get(model_key(model), model or "?")


def price(model, speed, inp, out, w5, w1h, read):
    p = PRICES.get(model_key(model))
    if not p:
        return 0.0
    f = 2.0 if speed == "fast" else 1.0
    return f * (inp * p["in"] + out * p["out"] + w5 * p["in"] * 1.25
                + w1h * p["in"] * 2.0 + read * p["read"]) / 1e6


# ---- Central European Time without tzdata: CEST from the last Sunday of March 01:00 UTC
# to the last Sunday of October 01:00 UTC (EU rule), CET otherwise.
def _last_sunday(year, month):
    d = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def to_local(dt_utc):
    y = dt_utc.year
    start = _last_sunday(y, 3).replace(hour=1)
    end = _last_sunday(y, 10).replace(hour=1)
    off = 2 if start <= dt_utc < end else 1
    return (dt_utc + timedelta(hours=off)).replace(tzinfo=None)


def now_local():
    return to_local(datetime.now(timezone.utc))


def buckets(dt_local):
    iso = dt_local.isocalendar()
    return (dt_local.strftime("%Y-%m-%d %H"), dt_local.strftime("%Y-%m-%d"),
            f"{iso[0]}-W{iso[1]:02d}", dt_local.strftime("%Y-%m"))


@functools.lru_cache(maxsize=4096)
def project_of(cwd):
    """Repository a call belongs to: worktrees fold into their repo, a repo cloned
    into a job's tmp folder keeps its name, scratch folders and anything else
    under ~/.claude count as the home."""
    if not cwd:
        return "~"
    p = cwd.rstrip("/")
    if "/.claude/worktrees/" in p:
        p = p.split("/.claude/worktrees/")[0]
    jobs = os.path.join(CLAUDE_DIR, "jobs") + "/"
    if p.startswith(jobs):
        parts = p[len(jobs):].split("/")
        if len(parts) >= 3 and parts[1] == "tmp" and \
                os.path.exists(os.path.join(jobs, *parts[:3], ".git")):
            return parts[2]
        return "~"
    if p.startswith(os.path.join(HOME, ".claude-mem")):
        return "claude-mem"
    if p == HOME or p.startswith(CLAUDE_DIR):
        return "~"
    if p.startswith(HOME + "/"):
        return p[len(HOME) + 1:].split("/")[0]
    return p


SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
  msg_id TEXT, request_id TEXT, ts REAL, hour TEXT, day TEXT, week TEXT, month TEXT,
  session_id TEXT, agent_id TEXT, project TEXT, model TEXT, speed TEXT,
  input INTEGER, output INTEGER, cache_w5m INTEGER, cache_w1h INTEGER, cache_read INTEGER,
  cost REAL, PRIMARY KEY (msg_id, request_id));
CREATE INDEX IF NOT EXISTS calls_ts ON calls(ts);
CREATE INDEX IF NOT EXISTS calls_session ON calls(session_id);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY, kind TEXT, entrypoint TEXT,
  custom_title TEXT, agent_name TEXT, ai_title TEXT, job_name TEXT, first_prompt TEXT);
CREATE TABLE IF NOT EXISTS agents (agent_id TEXT PRIMARY KEY, session_id TEXT,
  agent_type TEXT, description TEXT, model TEXT);
CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, inode INTEGER, offset INTEGER);
"""


def connect(path):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    db = sqlite3.connect(path, timeout=30, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    if "grp" not in [r[1] for r in db.execute("PRAGMA table_info(calls)")]:
        db.execute("ALTER TABLE calls ADD COLUMN grp TEXT")
        db.execute("CREATE INDEX IF NOT EXISTS calls_grp ON calls(grp)")
    cols = [r[1] for r in db.execute("PRAGMA table_info(sessions)")]
    for c in ("cc_id", "cc_name"):
        if c not in cols:
            db.execute(f"ALTER TABLE sessions ADD COLUMN {c} TEXT")
    return db


# CloudCLI database (its data/auth.db); empty = CloudCLI names are not imported
CLOUDCLI_DB = os.environ.get("CLOUDCLI_DB", "")


def sync_cloudcli(db):
    """CloudCLI names conversations itself and opens them by its own id (/session/<id>), which
    maps to Claude Code's session id. Copied here so titles and links match what CloudCLI shows.
    Read only; if CloudCLI is not installed or its database is busy, nothing changes."""
    if not CLOUDCLI_DB or not os.path.exists(CLOUDCLI_DB):
        return
    try:
        src = sqlite3.connect(f"file:{CLOUDCLI_DB}?mode=ro", uri=True, timeout=5)
        rows = src.execute("SELECT coalesce(provider_session_id, session_id), session_id, custom_name "
                           "FROM sessions WHERE provider = 'claude' AND NOT isArchived").fetchall()
        src.close()
    except sqlite3.Error:
        return
    db.execute("UPDATE sessions SET cc_id = NULL, cc_name = NULL WHERE cc_id IS NOT NULL")
    db.executemany("UPDATE sessions SET cc_id = ?, cc_name = nullif(trim(?), '') WHERE session_id = ?",
                   [(app, name, sid) for sid, app, name in rows])


def assign_groups(db):
    """One group per conversation, so a conversation is never split across projects.
    - it worked in a repo: the repo where it made most calls (home and claude-mem not counted);
    - it never left home: its own name (job name, /rename title, AI title, first prompt);
    - claude-mem note-taking sessions stay together as 'claude-mem'.
    calls.project keeps the per-call folder; calls.grp is what the dashboard groups by."""
    db.execute("""
        WITH per AS (
          SELECT session_id, project, count(*) AS n FROM calls
          WHERE project NOT IN ('~', 'claude-mem') GROUP BY 1, 2),
        best AS (
          SELECT session_id, project FROM (
            SELECT session_id, project, row_number() OVER (PARTITION BY session_id ORDER BY n DESC, project) AS r
            FROM per) WHERE r = 1),
        grp AS (
          SELECT s.session_id,
                 CASE WHEN b.project IS NOT NULL THEN b.project
                      WHEN s.kind = 'notes' THEN 'claude-mem'
                      ELSE substr(coalesce(s.cc_name, s.job_name, s.custom_title, s.agent_name, s.ai_title, s.first_prompt,
                                           substr(s.session_id, 1, 8)), 1, 60) END AS g
          FROM sessions s LEFT JOIN best b USING (session_id))
        UPDATE calls SET grp = (SELECT g FROM grp WHERE grp.session_id = calls.session_id)
        WHERE grp IS NOT (SELECT g FROM grp WHERE grp.session_id = calls.session_id)""")


def _session(db, sid, **fields):
    db.execute("INSERT OR IGNORE INTO sessions(session_id) VALUES (?)", (sid,))
    for k, v in fields.items():
        if k == "first_prompt":
            db.execute("UPDATE sessions SET first_prompt=? WHERE session_id=? AND first_prompt IS NULL", (v, sid))
        else:
            db.execute(f"UPDATE sessions SET {k}=? WHERE session_id=?", (v, sid))


def _prompt_text(content):
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content
                           if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return None
    t = " ".join(content.split())
    if not t or t.startswith("<") or t.startswith("[Request interrupted"):
        return None
    return t[:160]


def _ingest_line(db, d, agent_id):
    t = d.get("type")
    sid = d.get("sessionId")
    if not sid:
        return 0
    if t == "custom-title" and d.get("customTitle"):
        _session(db, sid, custom_title=d["customTitle"])
    elif t == "agent-name" and d.get("agentName"):
        _session(db, sid, agent_name=d["agentName"])
    elif t == "ai-title" and d.get("aiTitle"):
        _session(db, sid, ai_title=d["aiTitle"])
    elif t == "user" and not d.get("isSidechain") and not agent_id:
        txt = _prompt_text((d.get("message") or {}).get("content"))
        if txt:
            _session(db, sid, first_prompt=txt)
    elif t == "assistant":
        m = d.get("message") or {}
        u = m.get("usage")
        model = m.get("model")
        if not u or not model or model.startswith("<"):
            return 0
        cc = u.get("cache_creation") or {}
        w1h = cc.get("ephemeral_1h_input_tokens")
        w5 = cc.get("ephemeral_5m_input_tokens")
        if w1h is None and w5 is None:
            w5, w1h = u.get("cache_creation_input_tokens", 0), 0
        w5, w1h = w5 or 0, w1h or 0
        inp, out = u.get("input_tokens", 0), u.get("output_tokens", 0)
        read = u.get("cache_read_input_tokens", 0)
        speed = u.get("speed") or "standard"
        try:
            dt = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00"))
        except (KeyError, ValueError):
            return 0
        h, day, wk, mo = buckets(to_local(dt))
        cwd = d.get("cwd") or ""
        db.execute("INSERT OR IGNORE INTO sessions(session_id) VALUES (?)", (sid,))
        if not agent_id:
            ep = d.get("entrypoint") or ""
            kind = "notes" if project_of(cwd) == "claude-mem" else ("sdk" if ep.startswith("sdk") else "chat")
            db.execute("UPDATE sessions SET entrypoint=coalesce(entrypoint,?), kind=coalesce(kind,?) "
                       "WHERE session_id=?", (ep, kind, sid))
        cur = db.execute(
            "INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL) "
            "ON CONFLICT(msg_id, request_id) DO UPDATE SET output=excluded.output, cost=excluded.cost "
            "WHERE excluded.output > output",
            (m.get("id"), d.get("requestId") or "", dt.timestamp(), h, day, wk, mo, sid, agent_id,
             project_of(cwd), model_key(model), speed, inp, out, w5, w1h, read,
             price(model, speed, inp, out, w5, w1h, read)))
        return cur.rowcount
    return 0


def _job_names(db):
    for f in glob.glob(os.path.join(CLAUDE_DIR, "jobs", "*", "state.json")):
        try:
            s = json.load(open(f))
        except (OSError, ValueError):
            continue
        for sid in {s.get("sessionId"), s.get("resumeSessionId")} - {None}:
            _session(db, sid, kind="job")
            if s.get("name"):
                _session(db, sid, job_name=s["name"])


def ingest(db):
    """Read whatever was appended since the last run. Returns the rows touched."""
    added = 0
    files = glob.glob(os.path.join(CLAUDE_DIR, "projects", "**", "*.jsonl"), recursive=True)
    known = {r["path"]: (r["inode"], r["offset"]) for r in db.execute("SELECT * FROM files")}
    for path in files:
        try:
            st = os.stat(path)
        except OSError:
            continue
        inode, offset = known.get(path, (st.st_ino, 0))
        if inode != st.st_ino or st.st_size < offset:
            offset = 0
        if st.st_size == offset:
            continue
        agent_id = None
        if "/subagents/" in path:
            agent_id = os.path.basename(path)[:-6].removeprefix("agent-")
            try:
                mj = json.load(open(path[:-6] + ".meta.json"))
                db.execute("INSERT OR REPLACE INTO agents VALUES (?,?,?,?,?)",
                           (agent_id, os.path.basename(os.path.dirname(os.path.dirname(path))),
                            mj.get("agentType"), mj.get("description"), mj.get("model")))
            except (OSError, ValueError):
                pass
        with open(path, "rb") as fh:
            fh.seek(offset)
            chunk = fh.read()
        end = chunk.rfind(b"\n") + 1
        for line in chunk[:end].splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                added += max(_ingest_line(db, d, agent_id), 0)
        db.execute("INSERT OR REPLACE INTO files VALUES (?,?,?)", (path, st.st_ino, offset + end))
    _job_names(db)
    sync_cloudcli(db)
    assign_groups(db)
    db.commit()
    return added


if __name__ == "__main__":
    t = time.time()
    db = connect(os.environ.get("TOKENDASH_DB", "data/usage.db"))
    n = ingest(db)
    print(f"{n} calls added in {time.time() - t:.1f}s")
