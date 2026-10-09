"""Claude plan limits (session, week, week per model) read live from Anthropic,
as Telegram HTML text."""
import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from html import escape

from .store import CLAUDE_DIR, to_local

URL = "https://api.anthropic.com/api/oauth/usage"
# A saved response of URL, read instead of asking Anthropic: for demos and screenshots.
SAVED = os.environ.get("TOKENDASH_LIMITS_JSON")
TTL = 60  # seconds a reading is reused: the page refreshes every minute
WINDOW = {"session": timedelta(hours=5)}  # the weekly limits last 7 days
NAMES = {"session": "Sessione (5 ore)", "weekly_all": "Settimana (tutti i modelli)"}


_cache = {"at": 0.0, "limits": None}
_cache_lock = threading.Lock()


def _ask():
    if SAVED:
        with open(SAVED) as f:
            return json.load(f)
    with open(os.path.join(CLAUDE_DIR, ".credentials.json")) as f:
        token = json.load(f)["claudeAiOauth"]["accessToken"]
    req = urllib.request.Request(URL, headers={"Authorization": "Bearer " + token,
                                               "anthropic-beta": "oauth-2025-04-20"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def cached():
    """fetch(), reused for TTL seconds; None when Anthropic or the token is unavailable,
    so the page keeps working without the limits."""
    with _cache_lock:
        if time.monotonic() - _cache["at"] > TTL:
            try:
                _cache["limits"] = fetch()
            except (OSError, ValueError, KeyError) as e:
                print("plan limits unavailable:", e)
                _cache["limits"] = None
            _cache["at"] = time.monotonic()
        return _cache["limits"]


def fetch():
    """Current limits from Anthropic, with the OAuth token Claude Code keeps fresh."""
    limits = _ask().get("limits", [])
    out = []
    for lim in limits:
        name = NAMES.get(lim["kind"])
        if lim["kind"] == "weekly_scoped":
            model = ((lim.get("scope") or {}).get("model") or {}).get("display_name") or "modello"
            name = "Settimana " + model
        if name:
            out.append({"kind": lim["kind"], "name": name, "percent": lim["percent"],
                        "resets_at": lim["resets_at"] or ""})
    return out


def reset_label(iso):
    return to_local(datetime.fromisoformat(iso)).strftime("%d/%m %H:%M") if iso else "?"


def forecast(lim, now=None):
    """Straight-line projection at the window's average pace: where the limit
    lands at reset, and when it would run out if that comes first."""
    if not lim["resets_at"] or lim["percent"] <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    reset = datetime.fromisoformat(lim["resets_at"])
    length = WINDOW.get(lim["kind"], timedelta(days=7))
    elapsed = now - (reset - length)
    if elapsed < length / 20:  # too early in the window for a fair pace
        return None
    at_reset = lim["percent"] * length / elapsed
    out = (reset - length) + elapsed * 100 / lim["percent"]
    return {"at_reset": at_reset, "runs_out": out if out < reset else None}


def forecast_label(lim):
    f = forecast(lim)
    if f is None:
        return ""
    if f["runs_out"]:
        return f"\n   🔴 a questo ritmo finisce il {to_local(f['runs_out']).strftime('%d/%m %H:%M')}, prima del reset"
    return f"\n   🟢 a questo ritmo arrivi al reset con circa {min(f['at_reset'], 100):.0f}%"


def text(limits, hit=()):
    """One line per limit; the ones in `hit` stand out."""
    rows = []
    for l in limits:
        row = f"{escape(l['name'])}: {l['percent']:.0f}% · reset {reset_label(l['resets_at'])}"
        rows.append((f"⚡ <b>{row}</b>" if l["kind"] in hit else f"• {row}") + forecast_label(l))
    return "<b>Claude · uso limiti</b>\n" + "\n".join(rows)
