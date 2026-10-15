"""Step-by-step setup, for Claude Code used from the command line on Linux (not the desktop apps): checks what the dashboard needs, asks for the settings, writes them to
tokendash.env and, if you want, installs a service that starts it with the machine.

  python3 -m tokendash.setup            ask every question
  python3 -m tokendash.setup --yes      take every proposed answer (unattended installs)

Only the standard library. Safe to run again: it proposes the values already saved.
"""
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.environ.get("TOKENDASH_CONFIG") or os.path.join(ROOT, "tokendash.env")
AUTO = "--yes" in sys.argv
# under sudo, files belong to the user who ran it, not to root
USER = os.environ.get("SUDO_USER") or getpass.getuser()
try:
    import pwd
    HOME = pwd.getpwnam(USER).pw_dir
except (ImportError, KeyError):
    HOME = os.path.expanduser("~")
GOOD, BAD, NOTE = "  ✓ ", "  ✗ ", "  · "


def say(text=""):
    print(text, flush=True)


def ask(question, default="", help_text=""):
    if help_text:
        say(f"\n{help_text}")
    if AUTO:
        say(f"{question} [{default}] → {default}")
        return default
    answer = input(f"{question} [{default}]: ").strip()
    return answer or default


def yes(question, default=True):
    d = "Y/n" if default else "y/N"
    if AUTO:
        say(f"{question} [{d}] → {'yes' if default else 'no'}")
        return default
    a = input(f"{question} [{d}]: ").strip().lower()
    return default if not a else a.startswith(("y", "s"))


def saved():
    out = {}
    try:
        with open(CONFIG) as f:
            for line in f:
                if "=" in line and not line.lstrip().startswith("#"):
                    k, v = line.strip().removeprefix("export ").split("=", 1)
                    out[k] = v.strip('"')
    except OSError:
        pass
    return out


def system_zone():
    if os.environ.get("TZ", "").strip(":"):
        return os.environ["TZ"].strip(":")
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return os.environ.get("TZ", "")


def give(path):
    """Under sudo, hand a created file or folder back to the user the service will run as."""
    if os.geteuid() == 0 and USER != "root":
        try:
            import pwd
            pw = pwd.getpwnam(USER)
            for root, dirs, files in os.walk(path) if os.path.isdir(path) else [(os.path.dirname(path), [], [os.path.basename(path)])]:
                if os.path.isdir(path):
                    os.chown(root, pw.pw_uid, pw.pw_gid)
                for name in files:
                    os.chown(os.path.join(root, name), pw.pw_uid, pw.pw_gid)
        except (ImportError, KeyError, OSError):
            pass


def port_free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", int(port))) != 0


REQUIREMENTS = """What the dashboard needs. Prepare these before you start.

  Required
    - Linux, with Claude Code used from the command line (`claude`). The desktop apps for
      Windows and macOS are not supported.
    - Python 3.12 or newer (no Python packages to install)
    - Claude Code used on this machine by the user the dashboard will run as:
      it reads the conversations Claude Code writes in ~/.claude/projects
    - a free TCP port (3020 by default)

  Optional, each one adds a feature
    - Claude Code login on this machine (`claude`, then `/login`) and access to
      api.anthropic.com: the Claude plan limits box and its charts
    - Pillow (python3-pil / py3-pillow / pip install pillow): the limits as a PNG image,
      to attach to a chat message
    - tzdata (time zone database), when the system has no /usr/share/zoneinfo:
      needed to count hours in a zone other than the system one
    - root or sudo, with systemd or OpenRC: a service that starts with the machine
    - CloudCLI: conversation names from CloudCLI and links to open them there
    - the caveman proxy: the /caveman savings page
    - a reverse proxy with a login, if the dashboard must be reachable from other machines
"""


def check(cfg):
    """Every required and optional dependency, with what to do when one is missing.
    Returns False if something required is missing."""
    say("\n1. Checking what is needed")
    ok = True
    say("\n  Required")
    if sys.version_info >= (3, 12):
        say(f"{GOOD}Python {sys.version.split()[0]}")
    else:
        say(f"{BAD}Python {sys.version.split()[0]}: 3.12 or newer is needed")
        ok = False
    claude = cfg.get("CLAUDE_DIR") or os.path.join(HOME, ".claude")
    found = 0
    for _, _, files in os.walk(os.path.join(claude, "projects")):
        found += sum(f.endswith(".jsonl") for f in files)
    if found:
        say(f"{GOOD}Claude Code conversations: {found} files in {claude}/projects")
    else:
        say(f"{BAD}no Claude Code conversations in {claude}/projects. Use Claude Code once as this user"
            f" ({USER}), or give the right folder in the next step.")
        ok = False
    port = cfg.get("TOKENDASH_PORT", "3020")
    say(f"{GOOD}port {port} free" if port_free(port) else
        f"{NOTE}port {port} is in use (fine if it is this dashboard; else choose another one next)")

    say("\n  Optional")
    try:
        from tokendash import limits
        limits.access_token()
        say(f"{GOOD}Claude Code login found: plan limits box on")
    except Exception:
        say(f"{NOTE}no Claude Code login readable: plan limits box off."
            " Log in with `claude` then `/login`, as this user.")
    try:
        import PIL  # noqa: F401
        say(f"{GOOD}Pillow present: limits image on")
    except ImportError:
        say(f"{NOTE}Pillow missing: limits image off"
            " (Debian/Ubuntu: apt install python3-pil, Alpine: apk add py3-pillow, else pip install pillow)")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("America/New_York")
        say(f"{GOOD}time zone database present: any time zone can be used")
    except Exception:
        say(f"{NOTE}no time zone database: only the system zone works"
            " (Debian/Ubuntu: apt install tzdata, Alpine: apk add tzdata, else pip install tzdata)")
    manager = ("systemd" if os.path.isdir("/run/systemd/system")
               else "OpenRC" if shutil.which("openrc-run") or os.path.exists("/sbin/openrc-run") else None)
    if not manager:
        say(f"{NOTE}no systemd or OpenRC: start the dashboard by hand or with your own tool")
    elif os.geteuid() != 0:
        say(f"{NOTE}{manager} found, but not running as root: run again with sudo to install the service")
    else:
        say(f"{GOOD}{manager} found: the dashboard can start with the machine")
    cloudcli = cfg.get("CLOUDCLI_DB") or next((p for p in ("/opt/claudecodeui/data/auth.db",
                                                          os.path.join(HOME, ".cloudcli", "auth.db")) if os.path.exists(p)), "")
    say(f"{GOOD}CloudCLI found ({cloudcli})" if cloudcli else f"{NOTE}CloudCLI not found: names and links from CloudCLI off")
    cave = os.path.join(HOME, ".caveman", "caveman.db")
    say(f"{GOOD}caveman proxy data found: /caveman page on" if os.path.exists(cave)
        else f"{NOTE}caveman proxy not found: /caveman page off")
    return ok


def settings(cfg):
    say("\n2. Settings (Enter keeps the proposal)")
    out = dict(cfg)
    out["TOKENDASH_TZ"] = ask("Time zone", cfg.get("TOKENDASH_TZ") or system_zone() or "UTC",
                              "Hours, days and weeks are counted in this zone (IANA name, e.g. Europe/Rome, America/New_York).")
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(out["TOKENDASH_TZ"])
    except Exception:
        say(f"{NOTE}'{out['TOKENDASH_TZ']}' cannot be loaded here (unknown name or tzdata not installed): Central European Time will be used.")
    port = ask("Port", cfg.get("TOKENDASH_PORT", "3020"), "The dashboard listens on all interfaces on this port.")
    if not port_free(port) and port != cfg.get("TOKENDASH_PORT"):
        say(f"{NOTE}port {port} is already in use here: choose another one if the service does not start.")
    out["TOKENDASH_PORT"] = port
    data = ask("Data folder", os.path.dirname(cfg.get("TOKENDASH_DB", "")) or os.path.join(ROOT, "data"),
               "The dashboard keeps its own database here (usage history, limits cache).")
    os.makedirs(data, exist_ok=True)
    give(data)
    out["TOKENDASH_DB"] = os.path.join(os.path.abspath(data), "usage.db")
    out["CLAUDE_DIR"] = ask("Claude Code folder", cfg.get("CLAUDE_DIR") or os.path.join(HOME, ".claude"))
    out["TOKENDASH_PUBLIC_URL"] = ask("Public address (optional)", cfg.get("TOKENDASH_PUBLIC_URL", ""),
                                      "Only for link previews in chats: the address people open, e.g. https://tokens.example.com."
                                      " Leave empty if unsure.")
    cloudcli = cfg.get("CLOUDCLI_DB") or next((p for p in ("/opt/claudecodeui/data/auth.db",
                                                          os.path.join(HOME, ".cloudcli", "auth.db")) if os.path.exists(p)), "")
    if yes("Do you use CloudCLI (web UI for Claude Code)?", bool(cloudcli)):
        out["CLOUDCLI_DB"] = ask("CloudCLI database (its data/auth.db)", cloudcli)
        out["CLOUDCLI_URL"] = ask("CloudCLI address, for 'open in CloudCLI' links", cfg.get("CLOUDCLI_URL", ""))
    else:
        out.pop("CLOUDCLI_DB", None)
        out.pop("CLOUDCLI_URL", None)
    return out


def write(cfg):
    keys = ["TOKENDASH_TZ", "TOKENDASH_PORT", "TOKENDASH_DB", "CLAUDE_DIR", "TOKENDASH_PUBLIC_URL",
            "CLOUDCLI_DB", "CLOUDCLI_URL"]
    lines = [f"# Written by python3 -m tokendash.setup on {datetime.now():%Y-%m-%d %H:%M}. Run it again to change."]
    lines += [f'{k}="{cfg[k]}"' for k in keys if cfg.get(k)]
    lines += [f'{k}="{v}"' for k, v in cfg.items() if k not in keys and v]
    with open(CONFIG, "w") as f:
        f.write("\n".join(lines) + "\n")
    give(CONFIG)
    say(f"\n3. Settings saved in {CONFIG}")


def service(cfg):
    py, user = sys.executable, getpass.getuser()
    say("\n4. Start with the machine")
    if os.path.isdir("/run/systemd/system"):
        kind = "systemd"
    elif shutil.which("openrc-run") or os.path.exists("/sbin/openrc-run"):
        kind = "openrc"
    else:
        kind = None
    if not kind or not yes(f"Install a {kind} service" if kind else "", True):
        say(f"{NOTE}no service installed. Start it by hand with:\n    cd {ROOT} && {py} -m tokendash.server")
        return None
    if os.geteuid() != 0:
        say(f"{NOTE}installing a {kind} service needs root: run this again with sudo, or start it by hand with\n"
            f"    cd {ROOT} && {py} -m tokendash.server")
        return None
    if kind == "systemd":
        unit = f"""[Unit]
Description=DASHBOARD: AI TOKENS (Claude Code token usage)
After=network.target

[Service]
User={USER}
WorkingDirectory={ROOT}
Environment=TOKENDASH_CONFIG={CONFIG}
ExecStart={py} -m tokendash.server
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
        with open("/etc/systemd/system/tokendash.service", "w") as f:
            f.write(unit)
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "--now", "tokendash"], check=True)
        subprocess.run(["systemctl", "restart", "tokendash"], check=True)
    elif kind == "openrc":
        script = f"""#!/sbin/openrc-run
description="DASHBOARD: AI TOKENS (Claude Code token usage)"
supervisor="supervise-daemon"
command="{py}"
command_args="-m tokendash.server"
command_user="{USER}"
directory="{ROOT}"
output_log="/var/log/tokendash.log"
error_log="/var/log/tokendash.log"
export TOKENDASH_CONFIG="{CONFIG}"
depend() {{ need net; }}
"""
        with open("/etc/init.d/tokendash", "w") as f:
            f.write(script)
        os.chmod("/etc/init.d/tokendash", 0o755)
        subprocess.run(["rc-update", "add", "tokendash", "default"], check=False)
        subprocess.run(["rc-service", "tokendash", "restart"], check=True)
    say(f"{GOOD}{kind} service installed and started")
    return kind


def verify(cfg, started):
    say("\n5. Checking it answers")
    url = f"http://127.0.0.1:{cfg['TOKENDASH_PORT']}"
    proc = None
    if not started:
        env = dict(os.environ, TOKENDASH_CONFIG=CONFIG)
        proc = subprocess.Popen([sys.executable, "-m", "tokendash.server"], cwd=ROOT, env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(60):  # the first start imports every transcript before it listens
        try:
            data = json.load(urllib.request.urlopen(url + "/api/overview?g=month", timeout=5))
            say(f"{GOOD}dashboard up: {data['scope']['calls']} calls in the last 12 months")
            break
        except Exception:
            time.sleep(1)
    else:
        say(f"{BAD}no answer on {url}. Run `{sys.executable} -m tokendash.server` in {ROOT} to see the error.")
    if proc:
        proc.terminate()
        say(f"{NOTE}test run stopped. Start it with: cd {ROOT} && {sys.executable} -m tokendash.server")
    say(f"\nOpen {cfg.get('TOKENDASH_PUBLIC_URL') or url} in a browser.")


def main():
    if not sys.platform.startswith("linux"):
        say("This setup is for Linux, with Claude Code used from the command line. "
            "The Windows and macOS desktop apps are not supported.")
        sys.exit(1)
    say("DASHBOARD: AI TOKENS, setup\n")
    say(REQUIREMENTS)
    cfg = saved()
    if not check(cfg) and not yes("Something required is missing. Continue anyway?", False):
        sys.exit(1)
    cfg = settings(cfg)
    write(cfg)
    verify(cfg, service(cfg))


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        say("\nSetup stopped, nothing more was changed.")
