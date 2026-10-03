# Install the current Node.js 24 LTS Windows x64 build inside this project.
# No administrator access or permanent PATH changes are required.
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$agrisenseRoot = Split-Path -Parent $PSScriptRoot
$agrisenseTools = Join-Path $agrisenseRoot '.tools'
$agrisenseNode = Join-Path $agrisenseTools 'node'
$agrisenseExe = Join-Path $agrisenseNode 'node.exe'
if (Test-Path -LiteralPath $agrisenseExe) {
    $agrisenseInstalled = & $agrisenseExe --version
    if ($LASTEXITCODE -eq 0 -and $agrisenseInstalled -match '^v24\.') {
        Write-Host "Already installed: $agrisenseInstalled ($agrisenseNode)"
        Write-Host 'Next: . .\scripts\use-node.ps1'
        return
    }
    throw "A different Node installation already exists in $agrisenseNode. Inspect it before replacing it."
}
New-Item -ItemType Directory -Force -Path $agrisenseTools | Out-Null
$agrisenseReleases = Invoke-RestMethod -Uri 'https://nodejs.org/dist/index.json'
$agrisenseRelease = $agrisenseReleases | Where-Object {
    $_.version -like 'v24.*' -and $_.lts -ne $false
} | Select-Object -First 1
if (-not $agrisenseRelease) { throw 'Could not find a Node.js 24 LTS release.' }
$agrisenseVersion = $agrisenseRelease.version
$agrisenseArchiveName = "node-$agrisenseVersion-win-x64.zip"
$agrisenseArchive = Join-Path $agrisenseTools $agrisenseArchiveName
$agrisenseBaseUrl = "https://nodejs.org/dist/$agrisenseVersion"
Write-Host "Downloading Node.js $agrisenseVersion from nodejs.org..."
Invoke-WebRequest -UseBasicParsing -Uri "$agrisenseBaseUrl/$agrisenseArchiveName" -OutFile $agrisenseArchive
$agrisenseChecksums = (Invoke-WebRequest -UseBasicParsing -Uri "$agrisenseBaseUrl/SHASUMS256.txt").Content
$agrisenseChecksumLine = $agrisenseChecksums -split "`n" | Where-Object {
    $_.Trim().EndsWith("  $agrisenseArchiveName")
} | Select-Object -First 1
if (-not $agrisenseChecksumLine) { throw 'The release checksum was not found.' }
$agrisenseExpectedHash = ($agrisenseChecksumLine.Trim() -split '\s+')[0]
$agrisenseActualHash = (Get-FileHash -LiteralPath $agrisenseArchive -Algorithm SHA256).Hash
if ($agrisenseActualHash -ne $agrisenseExpectedHash) {
    throw 'Node.js archive checksum mismatch. Installation stopped.'
}
Expand-Archive -LiteralPath $agrisenseArchive -DestinationPath $agrisenseTools -Force
$agrisenseExtracted = Join-Path $agrisenseTools "node-$agrisenseVersion-win-x64"
# Rename only this known extracted directory inside the project; never move recursively.
Rename-Item -LiteralPath $agrisenseExtracted -NewName 'node'
& $agrisenseExe --version
if ($LASTEXITCODE -ne 0) { throw 'The downloaded Node.js executable could not run.' }
Write-Host 'Installed. In this terminal run: . .\scripts\use-node.ps1'
