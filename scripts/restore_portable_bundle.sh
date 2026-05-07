#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
parts_dir="$repo_root/dist_parts"
out_dir="$repo_root/dist"
out_tar="$out_dir/qwen_cov_closure_linux_portable_20260507_224310.tar"
mkdir -p "$out_dir"
cat "$parts_dir"/qwen_cov_closure_linux_portable_20260507_224310.tar.part-* > "$out_tar"
if command -v sha256sum >/dev/null 2>&1 && [ -f "$parts_dir/qwen_cov_closure_linux_portable_20260507_224310.tar.sha256" ]; then
  (cd "$out_dir" && sha256sum -c "$parts_dir/qwen_cov_closure_linux_portable_20260507_224310.tar.sha256")
fi
echo "Restored: $out_tar"
echo "Unpack with: tar -xf $out_tar -C $out_dir"
