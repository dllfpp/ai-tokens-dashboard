#!/bin/sh
# Copies the dashboard to /opt/token-dashboard and (re)starts the OpenRC service.
# The database in /opt/token-dashboard/data is kept between deploys.
set -eu
SRC=$(cd "$(dirname "$0")/.." && pwd)
DEST=/opt/token-dashboard

mkdir -p "$DEST/data"
rm -rf "$DEST/tokendash"
cp -r "$SRC/tokendash" "$DEST/"
find "$DEST/tokendash" -name __pycache__ -type d -exec rm -rf {} +
install -m 755 "$SRC/deploy/tokendash.initd" /etc/init.d/tokendash
rc-update add tokendash default >/dev/null 2>&1 || true
rc-service tokendash restart
# the first start imports every transcript before it listens
for _ in $(seq 20); do
    if wget -qO- "http://127.0.0.1:${TOKENDASH_PORT:-3020}/api/overview?g=day" >/dev/null 2>&1; then
        echo "tokendash up on :${TOKENDASH_PORT:-3020}"
        exit 0
    fi
    sleep 1
done
echo "tokendash did not answer, see /var/log/tokendash.log" >&2
exit 1
