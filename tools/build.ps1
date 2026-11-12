# Builds the portable "Lead Scraper" desktop app, installs it, and makes a zip to share.
#
#   Run from the project folder:   powershell -ExecutionPolicy Bypass -File tools\build.ps1
#
# The app folder contains "Lead Scraper.exe" plus its own Python runtime and packages, so it runs
# on any 64-bit Windows 10/11 PC without installing Python. "Lead Scraper.exe" is Python's signed
# pythonw.exe (Python Software Foundation) under a new name - Windows Smart App Control blocks
# unsigned .exe files (e.g. PyInstaller builds) but allows this one. tools\launcher.py
# (installed as app\sitecustomize.py) starts the app when the .exe is opened.
#
# Result:
#   %LOCALAPPDATA%\Programs\Lead Scraper\Lead Scraper.exe     installed app
#   Desktop + Start Menu shortcut "Lead Scraper"
#   dist\Lead Scraper Setup.exe                               one-file installer to share (needs Inno Setup 6)
#   dist\Lead Scraper.zip                                     the same app as a zip (no installer)
# Re-run after changing the code to update the installed app.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$AppName = "Lead Scraper"
$InstallDir = Join-Path $env:LOCALAPPDATA "Programs\$AppName"
$Stage = Join-Path $Root "build\$AppName"
$Zip = Join-Path $Root "dist\$AppName.zip"
Set-Location $Root
$Quiet = @("/NFL", "/NDL", "/NJH", "/NJS", "/NP")

function Copy-Tree($From, $To, [string[]]$ExcludeDirs = @()) {
    $RoboArgs = @($From, $To, "/E") + $Quiet
    if ($ExcludeDirs) { $RoboArgs += @("/XD") + $ExcludeDirs }
    robocopy @RoboArgs | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "copying $From failed (robocopy $LASTEXITCODE)" }
}

if (Get-Process -Name $AppName -ErrorAction SilentlyContinue) {
    throw "$AppName is running. Close it first, then run this script again."
}

Write-Host "1/6  Checking requirements..." -ForegroundColor Cyan
python -m pip install --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Chromium download failed" }
$Py = (python -c "import sys; print(sys.base_prefix)").Trim()
$Version = (python -c "import sys; print(f'{sys.version_info[0]}{sys.version_info[1]}')").Trim()

Write-Host "2/6  Building the app folder..." -ForegroundColor Cyan
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null
# Python runtime (from the Python that is installed here)
foreach ($File in @("python$Version.dll", "python3.dll", "vcruntime140.dll", "vcruntime140_1.dll")) {
    if (Test-Path "$Py\$File") { Copy-Item "$Py\$File" $Stage }
}
Copy-Item "$Py\pythonw.exe" "$Stage\$AppName.exe"
Copy-Tree "$Py\DLLs" "$Stage\DLLs"
Copy-Tree "$Py\Lib" "$Stage\Lib" @("site-packages", "test", "idlelib", "ensurepip", "turtledemo", "__pycache__")
Copy-Tree "$Py\tcl" "$Stage\tcl"
# Only the packages the app uses (and their dependencies)
python tools\copy_deps.py "$Stage\Lib\site-packages"
if ($LASTEXITCODE -ne 0) { throw "copying packages failed" }
# The app itself
foreach ($Dir in @("core", "gui", "scrapers", "assets")) { Copy-Tree "$Root\$Dir" "$Stage\app\$Dir" @("__pycache__") }
Copy-Item "$Root\main.py" "$Stage\app\"
Copy-Item "$Root\tools\launcher.py" "$Stage\app\sitecustomize.py"
Copy-Item "$Root\tools\uninstall.ps1" "$Stage\uninstall.ps1"
# Isolated module search path: only this folder, never another Python on the PC.
Set-Content "$Stage\python$Version._pth" -Encoding ascii -Value @("Lib", "DLLs", "Lib\site-packages", "app", "import site")
python -m compileall -q -j 0 "$Stage\Lib" "$Stage\app" | Out-Null   # faster first start

Write-Host "3/6  Installing to $InstallDir ..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
robocopy $Stage $InstallDir /MIR @Quiet | Out-Null
if ($LASTEXITCODE -ge 8) { throw "installing failed (robocopy $LASTEXITCODE)" }
# Bring over lead history + browser profile from the old project-folder layout (copy only).
python -c "import sys; sys.path.insert(0, r'$Root'); from pathlib import Path; from core import paths; [print('   migrated', x) for x in paths.migrate_legacy(Path(r'$Root'))]"

Write-Host "4/6  Creating shortcuts..." -ForegroundColor Cyan
$Exe = Join-Path $InstallDir "$AppName.exe"
$Shell = New-Object -ComObject WScript.Shell
foreach ($Folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $Link = $Shell.CreateShortcut((Join-Path $Folder "$AppName.lnk"))
    $Link.TargetPath = $Exe
    $Link.Arguments = ""
    $Link.WorkingDirectory = $InstallDir
    $Link.IconLocation = "$InstallDir\app\assets\app.ico,0"
    $Link.Description = "Collect business leads from Google Maps"
    $Link.Save()
}

Write-Host "5/6  Making $Zip (to copy the app to another PC)..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path (Split-Path $Zip) | Out-Null
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path $Stage -DestinationPath $Zip -CompressionLevel Optimal

Write-Host "6/6  Making the one-file installer dist\$AppName Setup.exe ..." -ForegroundColor Cyan
$Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$Setup = Join-Path $Root "dist\$AppName Setup.exe"
if ($Iscc) {
    $Now = Get-Date   # version parts must be <= 65535: 1.<year>.<month><day>, e.g. 1.26.1111
    $Version = "1.$($Now.ToString('yy')).$([int]$Now.ToString('MMdd'))"
    & $Iscc /Q "/DAppVersion=$Version" "/DSourceDir=$Stage" (Join-Path $Root "tools\installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
} else {
    $Setup = $null
    Write-Host "     Inno Setup 6 not found - skipped. Install it with:  winget install JRSoftware.InnoSetup" -ForegroundColor Yellow
}
Remove-Item (Split-Path $Stage) -Recurse -Force   # build\ is only a staging area

$Size = (Get-ChildItem $InstallDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ""
Write-Host ("Done. '$AppName' is installed ({0:N0} MB). Start it from the Desktop or the Start Menu." -f $Size) -ForegroundColor Green
Write-Host "App:  $Exe"
if ($Setup) { Write-Host ("Setup: $Setup  ({0:N0} MB, one file to share)" -f ((Get-Item $Setup).Length / 1MB)) }
Write-Host "Zip:  $Zip   (unzip anywhere on another PC and run '$AppName.exe')"
