#!/usr/bin/env bash
set -euo pipefail

cd /root/market-agent
set -a
source /root/market-agent/.env
source /etc/market-agent/runtime.env
export BG_JOB_ISOLATED_LOOPS="${BG_JOB_ISOLATED_LOOPS:-true}"
set +a

cd /root/market-agent/backend
exec /root/.local/bin/uv run langgraph dev --no-browser --allow-blocking --no-reload --host 127.0.0.1 --port 2024 --n-jobs-per-worker 4
