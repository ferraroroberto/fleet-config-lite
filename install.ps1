# install.ps1 - wire fleet-config-lite into GitHub Copilot CLI (user scope).
#
# 1. Renders hook-config/session-state.template.json with this checkout's
#    absolute path and a resolved Python executable, into
#    %USERPROFILE%\.copilot\hooks\fleet-config-lite.session-state.json
#    (user-level hooks are the reliable location: repo-level .github/hooks
#    did not fire in non-interactive mode on Copilot CLI 1.0.70).
# 2. Ensures the state directory %USERPROFILE%\.copilot\hooks\state exists.
# 3. Junctions skills/ into %USERPROFILE%\.copilot\skills\<skill> so Copilot
#    discovers the lite issue skills in every session (falls back to copy if
#    the junction fails, e.g. on a filesystem without junction support).
#
# Re-run after moving the checkout or changing the templates. Idempotent.
#
# NOTE for agents and future edits: ASCII only in this file - it can run
# under Windows PowerShell 5.1, which chokes on BOM-less non-ASCII.

$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$copilotHome = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { Join-Path $env:USERPROFILE '.copilot' }
$hooksDir = Join-Path $copilotHome 'hooks'
$stateDir = Join-Path $hooksDir 'state'
$skillsDir = Join-Path $copilotHome 'skills'

# --- resolve a real python.exe (avoid the WindowsApps alias, which can hang
# --- when spawned non-interactively from a hook)
$python = $null
$candidates = @()
if ($env:LOCALAPPDATA) {
    $candidates += Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Programs\Python') -Filter python.exe -Recurse -Depth 1 -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
}
$fromPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if ($fromPath) { $candidates += $fromPath }
foreach ($candidate in $candidates) {
    if ($candidate -and ($candidate -notmatch '\\WindowsApps\\')) { $python = $candidate; break }
}
if (-not $python) {
    Write-Error 'No usable python.exe found (only the WindowsApps alias). Install Python and re-run.'
}

New-Item -ItemType Directory -Force -Path $hooksDir, $stateDir | Out-Null

# --- render the hook config with absolute paths (forward slashes keep the
# --- JSON free of escaping headaches)
$template = Get-Content (Join-Path $repo 'hook-config\session-state.template.json') -Raw
$rendered = $template.Replace('{{PYTHON}}', ($python -replace '\\', '/')).Replace('{{REPO}}', ($repo -replace '\\', '/'))
# Hyphens only in the filename: Copilot CLI 1.0.70 silently ignores hook
# files with more than one dot in the name (verified live).
$target = Join-Path $hooksDir 'fleet-config-lite-session-state.json'
# WriteAllText, not Set-Content: under Windows PowerShell 5.1 Set-Content's
# utf8 writes a BOM, and Copilot CLI 1.0.70 silently ignores BOM'd hook
# configs (verified live). WriteAllText emits BOM-less UTF-8 on every PS.
[System.IO.File]::WriteAllText($target, $rendered)
Write-Host "[ok] hook config -> $target"
Write-Host "     python      -> $python"

# --- skills
# Never overwrite a skill this repo does not own: on a machine where another
# setup already provides issue-* skills (e.g. the full fleet-config at home),
# an existing directory that is not a junction into THIS repo is skipped.
New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null
Get-ChildItem -Path (Join-Path $repo 'skills') -Directory | ForEach-Object {
    $link = Join-Path $skillsDir $_.Name
    if (Test-Path $link) {
        $item = Get-Item $link -Force
        $ours = ($item.LinkType -eq 'Junction') -and ($item.Target -like "$repo*")
        if (-not $ours) {
            Write-Host "[skip] skill exists and is not ours -> $link"
            return
        }
        Remove-Item $link -Recurse -Force
    }
    try {
        New-Item -ItemType Junction -Path $link -Target $_.FullName | Out-Null
        Write-Host "[ok] skill junction -> $link"
    } catch {
        Copy-Item $_.FullName $link -Recurse
        Write-Host "[ok] skill copied   -> $link (junction unavailable)"
    }
}

Write-Host ''
Write-Host 'Done. Restart any running Copilot CLI session to pick up the hooks.'
Write-Host "State file will appear at: $stateDir\sessions-state.json"
