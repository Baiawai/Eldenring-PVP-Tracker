param(
    [string]$Identity,
    [string]$Publisher,
    [string]$PublisherDisplay,
    [string]$Version = '1.0.2.0',
    [string]$TesseractDir = 'C:\Program Files\Tesseract-OCR',
    [string]$MakeAppx = '',
    [switch]$ExecutableOnly
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (!(Test-Path $python)) { throw 'Python environment missing: see README.md.' }
if (!(Test-Path (Join-Path $TesseractDir 'tesseract.exe'))) { throw 'Tesseract executable not found.' }
if (!(Test-Path (Join-Path $TesseractDir 'doc\LICENSE'))) { throw 'Tesseract license not found.' }
if (-not $ExecutableOnly -and (!$Identity -or !$Publisher -or !$PublisherDisplay)) {
    throw 'Supply the exact Identity, Publisher and PublisherDisplay values from Partner Center.'
}
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Python dependencies are inconsistent.' }
$env:TRACKER_BUILD_CONSOLE = '0'
& $python -m PyInstaller --noconfirm --clean --distpath (Join-Path $root 'dist\store') --workpath (Join-Path $root 'build\store') (Join-Path $PSScriptRoot 'tracker.spec')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
$packageDir = Join-Path $root 'dist\store\EldenRingTracker'
$tessDest = Join-Path $packageDir 'tesseract'
New-Item -ItemType Directory -Force $tessDest | Out-Null
Copy-Item (Join-Path $TesseractDir 'tesseract.exe') $tessDest
Get-ChildItem $TesseractDir -Filter '*.dll' -File | Copy-Item -Destination $tessDest
Copy-Item (Join-Path $TesseractDir 'doc') (Join-Path $tessDest 'doc') -Recurse -Force
if ($ExecutableOnly) { Write-Host "Executable prepared in $packageDir"; return }
& $python (Join-Path $PSScriptRoot 'create_manifest.py') --package-dir $packageDir --identity $Identity --publisher $Publisher --publisher-display $PublisherDisplay --version $Version --icon (Join-Path $root 'static\tracker-eye.ico')
if ($LASTEXITCODE -ne 0) { throw 'Manifest creation failed.' }
if (!$MakeAppx) {
    $localKit = Join-Path $root 'build\windows-sdk-buildtools\bin\10.0.26100.0\x64\makeappx.exe'
    if (Test-Path $localKit) { $MakeAppx = $localKit }
}
if (!$MakeAppx) {
    $kitBin = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
    $candidate = Get-ChildItem $kitBin -Filter MakeAppx.exe -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Directory.Name -eq 'x64' } | Sort-Object FullName -Descending | Select-Object -First 1
    if ($candidate) { $MakeAppx = $candidate.FullName }
}
if (!$MakeAppx -or !(Test-Path $MakeAppx)) { throw 'MakeAppx.exe not found. Install the Windows SDK or specify -MakeAppx.' }
$output = Join-Path $root "dist\store\EldenRingTracker_${Version}_x64.msix"
& $MakeAppx pack /d $packageDir /p $output /o
if ($LASTEXITCODE -ne 0) { throw 'MakeAppx failed.' }
Write-Host "MSIX generated: $output"
