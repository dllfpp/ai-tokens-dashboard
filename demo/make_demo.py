"""Fills a database with invented usage, for screenshots and trying the dashboard out.

  python3 -m demo.make_demo data/demo.db
  TOKENDASH_DB=data/demo.db TOKENDASH_LIMITS_JSON=data/demo-limits.json CLAUDE_DIR=/nonexistent \
      python3 -m tokendash.server

Projects, conversation titles and numbers are made up. Times are relative to now, so the
hour/day/week/month readings and the chart are always filled. Deterministic (fixed seed).
"""
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

from tokendash import store

# (project folder, conversation titles, relative weight)
PROJECTS = [
    ("acme-api", ["Rate limiter for the public API", "Fix flaky checkout tests", "OpenAPI docs refresh"], 9),
    ("garden-planner", ["Watering schedule from weather forecast", "Plant cards redesign"], 7),
    ("homelab-notes", ["Backup rotation script", "Monitoring dashboard alerts"], 5),
    ("recipe-box", ["Import recipes from PDF", "Shopping list sharing"], 4),
    ("photo-sorter", ["Duplicate detection", "EXIF date repair"], 3),
    ("blog", ["New post layout", "RSS feed fixes"], 2),
    ("cli-tools", ["Changelog generator"], 2),
]
HOME_CHATS = ["Explain a regex", "Compare two SQL query plans", "Draft an email to the landlord"]
MODELS = [("claude-opus-5-5", 0.7), ("claude-sonnet-5-5", 0.2), ("claude-haiku-4-5", 0.1)]
SUBAGENTS = [("general-purpose", "Search the codebase for config loading"),
             ("Explore", "Map the test suite"), ("Plan", "Plan the migration steps")]


def call(db, rnd, sid, project, ts, agent=None):
    model = rnd.choices([m for m, _ in MODELS], [w for _, w in MODELS])[0]
    inp = rnd.randint(1, 40)
    out = int(rnd.lognormvariate(6.2, 0.9))
    w1h = int(rnd.lognormvariate(7.6, 1.1))
    read = int(rnd.uniform(40_000, 320_000))
    dt = datetime.fromtimestamp(ts, timezone.utc)
    h, day, wk, mo = store.buckets(store.to_local(dt))
    db.execute("INSERT INTO calls VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
               (uuid.uuid4().hex, uuid.uuid4().hex, ts, h, day, wk, mo, sid, agent, project, model,
                "standard", inp, out, 0, w1h, read, store.price(model, "standard", inp, out, 0, w1h, read)))


def main(path):
    if os.path.exists(path):
        os.remove(path)
    rnd = random.Random(7)
    db = store.connect(path)
    now = time.time()
    convs = [(p, t, w) for p, titles, w in PROJECTS for t in titles] + [("~", t, 1) for t in HOME_CHATS]
    for project, title, weight in convs:
        sid = str(uuid.uuid4())
        db.execute("INSERT INTO sessions(session_id, kind, entrypoint, job_name) VALUES (?, ?, 'cli', ?)",
                   (sid, rnd.choice(["chat", "job"]), title))
        # each conversation lives over one to four days somewhere in the last 30, a few are recent
        start = now - rnd.uniform(0, 30) * 86400 if rnd.random() > 0.3 else now - rnd.uniform(0, 1.5) * 86400
        for d in range(rnd.randint(1, 4)):
            for _ in range(int(rnd.uniform(8, 30) * weight / 3)):
                ts = min(now - 60, start + d * 86400 + rnd.uniform(0, 6 * 3600))
                call(db, rnd, sid, project if rnd.random() > 0.1 else "~", ts)
        if rnd.random() < 0.4:
            agent_type, desc = rnd.choice(SUBAGENTS)
            aid = uuid.uuid4().hex[:17]
            db.execute("INSERT INTO agents VALUES (?,?,?,?,?)", (aid, sid, agent_type, desc, "sonnet"))
            for _ in range(rnd.randint(4, 12)):
                call(db, rnd, sid, project, min(now - 60, start + rnd.uniform(0, 4 * 3600)), aid)
    store.assign_groups(db)
    db.commit()
    n = db.execute("SELECT count(*) FROM calls").fetchone()[0]
    print(f"{n} invented calls in {path}")
    limits(os.path.join(os.path.dirname(path), "demo-limits.json"))


def limits(path):
    """Invented plan limits, shaped like Anthropic's usage answer: the session is easy,
    the week runs out before its reset, the per-model week is fine."""
    now = datetime.now(timezone.utc)
    rows = [("session", 41, now + timedelta(hours=2, minutes=40), None),
            ("weekly_all", 71, now + timedelta(days=2, hours=6), None),
            ("weekly_scoped", 38, now + timedelta(days=2, hours=6), {"model": {"display_name": "Opus"}})]
    with open(path, "w") as f:
        json.dump({"limits": [{"kind": k, "percent": pc, "resets_at": r.isoformat(), "scope": sc}
                              for k, pc, r, sc in rows]}, f)
    print(f"invented plan limits in {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/demo.db")
