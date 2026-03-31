#!/usr/bin/env bash
set -euo pipefail

cd /root/market-agent
set -a
source /root/market-agent/.env
source /etc/market-agent/runtime.env
set +a

cd /root/market-agent/backend
exec /root/.local/bin/uv run uvicorn app.gateway.app:app --host 127.0.0.1 --port 8001
