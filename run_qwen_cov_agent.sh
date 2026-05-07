#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bash "${bundle_dir}/repair_ollama_links.sh" >/dev/null 2>&1 || true
chmod +x "${bundle_dir}/bin/ollama" 2>/dev/null || true

export OLLAMA_BIN="${OLLAMA_BIN:-${bundle_dir}/bin/ollama}"
export OLLAMA_MODELS="${OLLAMA_MODELS:-${bundle_dir}/models}"
export QWEN_COV_PYTHON="${QWEN_COV_PYTHON:-${bundle_dir}/runtime/python-3.3.3/bin/python}"
export PYTHON_FOR_QWEN_COV="${QWEN_COV_PYTHON}"

exec "${QWEN_COV_PYTHON}" "${bundle_dir}/bin/qwen_cov_agent.py" "$@"
