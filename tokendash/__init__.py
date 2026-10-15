"""Settings come from the environment, or from a KEY=VALUE file written by the setup wizard
(`python3 -m tokendash.setup`): TOKENDASH_CONFIG if set, else `tokendash.env` next to this
package. Variables already in the environment win over the file."""
import os

CONFIG = os.environ.get("TOKENDASH_CONFIG") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "tokendash.env")


def _load(path):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.removeprefix("export ").split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    except OSError:
        pass


_load(CONFIG)
