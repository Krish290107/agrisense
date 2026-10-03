# Dot-source this script: . .\scripts\use-node.ps1
$agrisenseRoot = Split-Path -Parent $PSScriptRoot
$agrisenseNode = Join-Path $agrisenseRoot '.tools\node'
if (Test-Path -LiteralPath (Join-Path $agrisenseNode 'node.exe')) {
    $env:Path = "$agrisenseNode;$env:Path"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw 'Node.js is missing. Run .\scripts\setup-node.ps1 first.'
}
$agrisenseNodeVersion = & node --version
if ($LASTEXITCODE -ne 0 -or $agrisenseNodeVersion -notmatch '^v24\.') {
    throw "AgriSense uses Node.js 24 LTS; found $agrisenseNodeVersion. Run .\scripts\setup-node.ps1, then dot-source this script again."
}
Write-Host "AgriSense Node.js: $agrisenseNodeVersion"
