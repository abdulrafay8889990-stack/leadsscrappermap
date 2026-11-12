# Uninstaller for Lead Scraper, installed next to the app and run from Settings > Apps.
# It runs with Windows' own (signed) PowerShell, so Smart App Control allows it - unlike an
# unsigned uninstall.exe. Removes the app, its shortcuts and its Apps entry; keeps your data
# (lead history in %LOCALAPPDATA%\Lead Scraper, files in Documents\Lead Scraper).
param([switch]$Silent)

$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$Name = "Lead Scraper"
Add-Type -AssemblyName PresentationFramework

if (-not $Silent) {
    $answer = [System.Windows.MessageBox]::Show(
        "Remove $Name from this PC?`n`nYour leads, Excel files and lead history are kept.",
        "Uninstall $Name", "YesNo", "Question")
    if ($answer -ne "Yes") { exit 1 }
}

Get-Process -Name $Name -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

# Shortcuts that point into this app folder
$Shell = New-Object -ComObject WScript.Shell
foreach ($Folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $Link = Join-Path $Folder "$Name.lnk"
    if ((Test-Path $Link) -and $Shell.CreateShortcut($Link).TargetPath -like "$App\*") {
        Remove-Item $Link -Force
    }
}

Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\LeadScraper" -Recurse -ErrorAction SilentlyContinue
Remove-Item $App -Recurse -Force -ErrorAction SilentlyContinue

if (-not $Silent) {
    [System.Windows.MessageBox]::Show("$Name was removed.", "Uninstall $Name") | Out-Null
}
