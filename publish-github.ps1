# Publish MeetScribe to GitHub (run once after: gh auth login)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) {
    Write-Host "GitHub CLI not found. Install: winget install GitHub.cli"
    exit 1
}

gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Log in first: gh auth login"
    exit 1
}

$exists = gh repo view olithin/MeetScribe 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Remote repo exists. Pushing..."
    git push -u origin main
} else {
    gh repo create MeetScribe `
        --public `
        --source=. `
        --remote=origin `
        --push `
        --description "Local meeting MP4 transcription with OpenAI Whisper, synced video player, and trim tools."

    gh repo edit olithin/MeetScribe `
        --add-topic python `
        --add-topic whisper `
        --add-topic ffmpeg `
        --add-topic desktop-app `
        --add-topic transcription
}

Write-Host ""
Write-Host "Done: https://github.com/olithin/MeetScribe"
