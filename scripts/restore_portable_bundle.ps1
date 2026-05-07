param(
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)
$partsDir = Join-Path $RepoRoot 'dist_parts'
$outDir = Join-Path $RepoRoot 'dist'
$outTar = Join-Path $outDir 'qwen_cov_closure_linux_portable_20260507_224310.tar'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null
$parts = Get-ChildItem -Path $partsDir -Filter 'qwen_cov_closure_linux_portable_20260507_224310.tar.part-*' | Sort-Object Name
$out = [System.IO.File]::Create($outTar)
try {
  foreach ($part in $parts) {
    $in = [System.IO.File]::OpenRead($part.FullName)
    try { $in.CopyTo($out) } finally { $in.Dispose() }
  }
} finally { $out.Dispose() }
Write-Host "Restored: $outTar"
