#!/usr/bin/env bash
set -euo pipefail

cd /root/market-agent
set -a
source /root/market-agent/.env
source /etc/market-agent/runtime.env
source /root/market-agent/frontend/.env
set +a

cd /root/market-agent/frontend
exec /root/market-agent/frontend/node_modules/.bin/next dev --hostname 127.0.0.1 --port 3000 --turbopack
