# install.ps1 - wire fleet-config-lite into GitHub Copilot CLI (user scope).
#
# 1. Renders hook-config/session-state.template.json with this checkout's
#    absolute path and a resolved Python executable, into
#    %USERPROFILE%\.copilot\hooks\fleet-config-lite-session-state.json
#    (user-level hooks are the reliable location: repo-level .github/hooks
#    did not fire in non-interactive mode on Copilot CLI 1.0.70).
# 2. Ensures the state directory %USERPROFILE%\.copilot\hooks\state exists.
# 3. Links global-instructions.md into %USERPROFILE%\.copilot\copilot-instructions.md
#    (symlink, falls back to copy) so Copilot CLI picks it up every session.
#    Skipped if that path is already owned by something else (e.g. the
#    private fleet-config linking its own global-CLAUDE.md there).
# 4. Junctions skills/ into %USERPROFILE%\.copilot\skills\<skill> so Copilot
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

# --- global instructions
# Never overwrite an instructions file this repo does not own. Ownership needs
# a positive signal:
#   - a SYMLINK is ours only if it points at this checkout's source (the
#     private fleet-config links its own global-CLAUDE.md there; that wins and
#     this step no-ops);
#   - a plain file is ours only if its first line is the marker the copy
#     fallback below writes, or its content is byte-identical to the source
#     (a copy from before the marker existed). A user's own hand-written
#     copilot-instructions.md has neither, so it is left alone with a [skip].
# Copies are refreshed on every run, so a machine that cannot create file
# symlinks (they need admin or Developer Mode; the junctions used for skills/
# below don't) still tracks global-instructions.md.
$instructionsSource = Join-Path $repo 'global-instructions.md'
$instructionsTarget = Join-Path $copilotHome 'copilot-instructions.md'
$instructionsMarker = '<!-- fleet-config-lite: managed copy of global-instructions.md; install.ps1 overwrites this file -->'
$skipInstructions = $false
if (Test-Path $instructionsTarget) {
    $item = Get-Item $instructionsTarget -Force
    if ($item.LinkType -eq 'SymbolicLink') {
        $ours = $item.Target -like "*$instructionsSource*"
        if ($ours) {
            Write-Host "[ok] copilot-instructions.md already linked -> $instructionsTarget"
        } else {
            Write-Host "[skip] copilot-instructions.md exists and is not ours -> $instructionsTarget"
        }
        $skipInstructions = $true
    } else {
        $existing = [System.IO.File]::ReadAllText($instructionsTarget)
        $sourceText = [System.IO.File]::ReadAllText($instructionsSource)
        $firstLine = ($existing -split "`r?`n", 2)[0]
        if (($firstLine -eq $instructionsMarker) -or ($existing -ceq $sourceText)) {
            Remove-Item $instructionsTarget -Force
        } else {
            Write-Host "[skip] copilot-instructions.md exists and is not ours (no marker, differs from global-instructions.md) -> $instructionsTarget"
            Write-Host "       move or delete it and re-run to let the installer manage it"
            $skipInstructions = $true
        }
    }
}
if (-not $skipInstructions) {
    try {
        New-Item -ItemType SymbolicLink -Path $instructionsTarget -Target $instructionsSource | Out-Null
        Write-Host "[ok] instructions symlink -> $instructionsTarget"
    } catch {
        # Marker first line = the ownership signal the next run looks for.
        # BOM-less UTF-8, same reasoning as the hook config above.
        $body = [System.IO.File]::ReadAllText($instructionsSource)
        [System.IO.File]::WriteAllText($instructionsTarget, $instructionsMarker + "`r`n`r`n" + $body)
        Write-Host "[ok] instructions copied  -> $instructionsTarget (symlink unavailable)"
    }
}

# --- skills
# Never overwrite a skill this repo does not own: on a machine where another
# setup already provides issue-* skills (e.g. one running the full
# fleet-config), an existing directory that is not a junction into THIS repo
# is skipped.
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
