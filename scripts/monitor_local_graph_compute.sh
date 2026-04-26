#!/usr/bin/env bash
set -euo pipefail

PORT="${LOCAL_GRAPH_MODEL_PORT:-8001}"
INTERVAL="${LOCAL_GRAPH_MONITOR_INTERVAL:-2}"

echo "[monitor] Watching local graph inference on port ${PORT}."
echo "[monitor] If GPU utilization stays near 0 while extraction is running, the extractor is not reaching vLLM."
echo

while true; do
  date +"[monitor] %Y-%m-%d %H:%M:%S"

  if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw --format=csv,noheader,nounits || true
  else
    echo "[monitor] nvidia-smi not found in this shell."
  fi

  if command -v curl >/dev/null 2>&1; then
    models_status="$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/v1/models" || true)"
    echo "[monitor] vLLM /v1/models HTTP ${models_status}"
  fi

  echo
  sleep "${INTERVAL}"
done
