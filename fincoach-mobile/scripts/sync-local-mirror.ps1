param(
  [string]$MirrorPath = "C:\tmp\fincoach-mobile-deps"
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not (Test-Path $MirrorPath)) {
  New-Item -ItemType Directory -Force -Path $MirrorPath | Out-Null
}

robocopy $projectRoot $MirrorPath /MIR /XD node_modules .git .expo _node_modules_partial_delete_me /NFL /NDL /NJH /NJS
if ($LASTEXITCODE -gt 7) {
  throw "robocopy failed with exit code $LASTEXITCODE"
}

Write-Output "Synced source to $MirrorPath"
