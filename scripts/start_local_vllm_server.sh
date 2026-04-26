#!/usr/bin/env bash
set -euo pipefail

# Starts an OpenAI-compatible vLLM server for bulk graph extraction.
# Keep this outside docker-compose so it can be tuned independently of the data plane.

MODEL="${LOCAL_GRAPH_MODEL:-NousResearch/Hermes-3-Llama-3.1-8B}"
PORT="${LOCAL_GRAPH_MODEL_PORT:-8001}"
GPU_MEMORY_UTILIZATION="${LOCAL_GRAPH_GPU_MEMORY_UTILIZATION:-0.85}"
MAX_MODEL_LEN="${LOCAL_GRAPH_MAX_MODEL_LEN:-4096}"
MAX_NUM_SEQS="${LOCAL_GRAPH_MAX_NUM_SEQS:-512}"
IMAGE="${LOCAL_GRAPH_VLLM_IMAGE:-vllm/vllm-openai:latest}"
CONTAINER_NAME="${LOCAL_GRAPH_VLLM_CONTAINER:-market_local_vllm_graph}"

echo "[vllm] model=${MODEL}"
echo "[vllm] port=${PORT}"
echo "[vllm] gpu_memory_utilization=${GPU_MEMORY_UTILIZATION}"
echo "[vllm] max_model_len=${MAX_MODEL_LEN}"
echo "[vllm] max_num_seqs=${MAX_NUM_SEQS}"

if docker ps --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  echo "[vllm] ${CONTAINER_NAME} is already running."
  exit 0
fi

if docker ps -a --format '{{.Names}}' | grep -qx "${CONTAINER_NAME}"; then
  docker rm "${CONTAINER_NAME}" >/dev/null
fi

docker run \
  --name "${CONTAINER_NAME}" \
  --gpus all \
  --ipc=host \
  --ulimit memlock=-1 \
  --ulimit stack=67108864 \
  -p "${PORT}:8000" \
  -v "${HOME}/.cache/huggingface:/root/.cache/huggingface" \
  "${IMAGE}" \
  --host 0.0.0.0 \
  --port 8000 \
  --model "${MODEL}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION}" \
  --max-model-len "${MAX_MODEL_LEN}" \
  --max-num-seqs "${MAX_NUM_SEQS}" \
  --enable-chunked-prefill
