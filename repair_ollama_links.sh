#!/usr/bin/env bash
set -euo pipefail

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
lib_root="${bundle_dir}/lib/ollama"

make_link() {
  local link_path="$1"
  local target="$2"
  local dir_path
  dir_path="$(dirname "$link_path")"
  mkdir -p "$dir_path"
  if [ -L "$link_path" ]; then
    return 0
  fi
  if [ -e "$link_path" ]; then
    return 0
  fi
  ln -s "$target" "$link_path" 2>/dev/null || true
}

chmod +x "${bundle_dir}/bin/ollama" 2>/dev/null || true
chmod +x "${bundle_dir}/bin/ollama.real" 2>/dev/null || true
chmod +x "${bundle_dir}/run_qwen_cov_agent.sh" 2>/dev/null || true

[ -d "$lib_root" ] || exit 0

make_link "${lib_root}/cuda_v12/libcublas.so.12" "libcublas.so.12.8.5.5"
make_link "${lib_root}/cuda_v12/libcublasLt.so.12" "libcublasLt.so.12.8.5.5"
make_link "${lib_root}/cuda_v12/libcudart.so.12" "libcudart.so.12.8.90"
make_link "${lib_root}/cuda_v13/libcublasLt.so.13" "libcublasLt.so.13.1.1.3"
make_link "${lib_root}/cuda_v13/libcublas.so.13" "libcublas.so.13.1.1.3"
make_link "${lib_root}/cuda_v13/libcudart.so.13" "libcudart.so.13.0.96"
make_link "${lib_root}/include" "mlx_cuda_v13/include"
make_link "${lib_root}/libggml-base.so" "libggml-base.so.0"
make_link "${lib_root}/libggml-base.so.0" "libggml-base.so.0.0.0"
make_link "${lib_root}/mlx_cuda_v13/libcublasLt.so.13.1.1.3" "../cuda_v13/libcublasLt.so.13.1.1.3"
make_link "${lib_root}/mlx_cuda_v13/libcudnn_engines_runtime_compiled.so.9" "libcudnn_engines_runtime_compiled.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libopenblas.so.0" "libopenblas-r0.3.15.so"
make_link "${lib_root}/mlx_cuda_v13/libcudart.so.13.0.96" "../cuda_v13/libcudart.so.13.0.96"
make_link "${lib_root}/mlx_cuda_v13/libcufft.so.12" "libcufft.so.12.0.0.61"
make_link "${lib_root}/mlx_cuda_v13/libcudnn_ops.so.9" "libcudnn_ops.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libnvrtc.so.13" "libnvrtc.so.13.0.88"
make_link "${lib_root}/mlx_cuda_v13/libcudnn_engines_precompiled.so.9" "libcudnn_engines_precompiled.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libnvrtc-builtins.so" "libnvrtc-builtins.so.13.0"
make_link "${lib_root}/mlx_cuda_v13/libcudart.so" "libcudart.so.13"
make_link "${lib_root}/mlx_cuda_v13/libcudnn_graph.so.9" "libcudnn_graph.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libcufft.so" "libcufft.so.12"
make_link "${lib_root}/mlx_cuda_v13/libnccl.so.2" "libnccl.so.2.30.4"
make_link "${lib_root}/mlx_cuda_v13/libcublasLt.so.13" "./libcublasLt.so.13.1.1.3"
make_link "${lib_root}/mlx_cuda_v13/libgfortran.so.5" "libgfortran.so.5.0.0"
make_link "${lib_root}/mlx_cuda_v13/libcublas.so.13" "./libcublas.so.13.1.1.3"
make_link "${lib_root}/mlx_cuda_v13/libcudnn_adv.so.9" "libcudnn_adv.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libcudnn.so.9" "libcudnn.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libnvrtc-builtins.so.13.0" "libnvrtc-builtins.so.13.0.88"
make_link "${lib_root}/mlx_cuda_v13/libcudart.so.13" "libcudart.so.13.0.96"
make_link "${lib_root}/mlx_cuda_v13/libcublas.so.13.1.1.3" "../cuda_v13/libcublas.so.13.1.1.3"
make_link "${lib_root}/mlx_cuda_v13/libnvrtc.so" "libnvrtc.so.13"
make_link "${lib_root}/mlx_cuda_v13/libcublasLt.so" "libcublasLt.so.13"
make_link "${lib_root}/mlx_cuda_v13/libcudnn_heuristic.so.9" "libcudnn_heuristic.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libcudnn_cnn.so.9" "libcudnn_cnn.so.9.21.1"
make_link "${lib_root}/mlx_cuda_v13/libcublas.so" "libcublas.so.13"
make_link "${lib_root}/vulkan/libvulkan.so.1" "libvulkan.so.1.4.321"
