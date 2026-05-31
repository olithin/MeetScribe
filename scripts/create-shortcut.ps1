# Creates a MeetScribe shortcut on the Desktop (Windows).
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$launcher = Join-Path $projectRoot "launch.vbs"
$iconPath = Join-Path $projectRoot "assets\meetscribe.ico"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "MeetScribe.lnk"

if (-not (Test-Path $launcher)) {
    Write-Error "launch.vbs not found at $launcher"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launcher
$shortcut.WorkingDirectory = $projectRoot
$shortcut.WindowStyle = 1
$shortcut.Description = "MeetScribe — meeting video to text"
if (Test-Path $iconPath) {
    $shortcut.IconLocation = "$iconPath,0"
}
$shortcut.Save()

Write-Host "Shortcut: $shortcutPath"
