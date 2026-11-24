# install.ps1 - wire fleet-config-lite's own skills and instructions into GitHub Copilot CLI (user scope).
#
# The Copilot hooks, the chief and the issue-workflow skills belong to app-launcher-lite's
# copilot\ folder and are installed by its copilot\install.ps1; this installer writes none of them.
#
# What it writes, and where:
# 1. Instructions: links global-instructions.md to
#    %USERPROFILE%\.copilot\copilot-instructions.md (symlink, else a marked copy),
#    only when that path is free or already ours.
# 2. Skills: junctions skills\<name> into %USERPROFILE%\.copilot\skills\<name>,
#    only into a real folder and never over a skill this checkout does not own.
# 3. This checkout's .venv (stdlib only; the audit and learning-log helpers run
#    through .venv\Scripts\python.exe), unless -SkipVenv.
# 4. A short checklist (Copilot CLI, glab, the venv) unless -SkipChecklist.
# It also warns about what an older install of this repo left behind: hook configs and
# skill links that app-launcher-lite's copilot\install.ps1 -Migrate removes.
#
# Shared machine: when ~/.copilot/skills or ~/.agents/skills is a link into
# another tree, this PC also runs the full fleet. Then nothing is written that
# would change other sessions: the skills and the instructions link are skipped
# with a message.
# Any user-scope target that is itself a link into another tree (the Copilot
# home, the skills folder) is never written through: it is skipped with a message.
#
# Re-run after moving the checkout. Idempotent.
#
# NOTE for agents and future edits: ASCII only in this file - it can run
# under Windows PowerShell 5.1, which chokes on BOM-less non-ASCII.

param(
    [switch]$SkipVenv,
    [switch]$SkipChecklist
)

$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$copilotHome = if ($env:COPILOT_HOME) { $env:COPILOT_HOME } else { Join-Path $env:USERPROFILE '.copilot' }
$hooksDir = Join-Path $copilotHome 'hooks'
$skillsDir = Join-Path $copilotHome 'skills'
$agentsSkillsDir = Join-Path (Join-Path $env:USERPROFILE '.agents') 'skills'

# The link target when $path is a reparse point that does not point into this
# checkout, else $null: writing through it would land in another tree.
function Get-ForeignLink([string]$path) {
    $item = Get-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue
    if (-not $item -or -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { return $null }
    $target = [string]($item.Target | Select-Object -First 1)
    if ($target -and $target.StartsWith($repo, [StringComparison]::OrdinalIgnoreCase)) { return $null }
    if (-not $target) { return '(unresolved link)' }
    return $target
}

$copilotHomeLink = Get-ForeignLink $copilotHome
if ($copilotHomeLink) {
    Write-Host "[skip] Copilot home is a link into another tree, nothing written -> $copilotHome ($copilotHomeLink)"
    exit 0
}

$sharedWhy = $null
foreach ($candidate in @($skillsDir, $agentsSkillsDir)) {
    $link = Get-ForeignLink $candidate
    if ($link) { $sharedWhy = "$candidate -> $link"; break }
}
$shared = [bool]$sharedWhy
if ($shared) {
    Write-Host "[note] shared machine (the full fleet runs here too): $sharedWhy"
}

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

# --- leftovers of the older install: this repo no longer ships hooks, but its old hook
# --- configs still run this checkout's deleted files, and two session-state hooks would
# --- race on one state file. Reported, never deleted: app-launcher-lite's installer owns the move.
$oldHooks = @(Get-ChildItem -LiteralPath $hooksDir -Filter 'fleet-config-lite-*.json' -ErrorAction SilentlyContinue)
if ($oldHooks.Count -gt 0) {
    Write-Host "[warn] $($oldHooks.Count) hook config(s) from the older install of this repo remain in $hooksDir"
    Write-Host '       run app-launcher-lite''s copilot\install.ps1 -Migrate to replace them with its own'
}

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
if ($shared) {
    # A global instructions file changes every Copilot session on the PC, not only lite's.
    Write-Host "[skip] instructions not linked on a shared machine -> $instructionsTarget"
    $skipInstructions = $true
} elseif (Test-Path $instructionsTarget) {
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
#
# The skills dir itself must be a real folder. On a full-fleet machine
# ~/.copilot/skills is a junction into the full fleet-config's skills/, so a
# link created "in" it lands inside that other repo and every agent on the
# machine loads the lite copy beside the full one. A reparse-point skills dir
# is therefore never written into.
$skillsItem = Get-Item -LiteralPath $skillsDir -Force -ErrorAction SilentlyContinue
if ($shared) {
    # Junctioned skills appear in every Copilot session, next to the full fleet's own.
    Write-Host "[skip] skills not installed on a shared machine -> $skillsDir"
    $skillSources = @()
} elseif ($skillsItem -and ($skillsItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    Write-Host "[skip] skills dir is a link into another tree, not touched -> $skillsDir ($($skillsItem.Target))"
    $skillSources = @()
} else {
    New-Item -ItemType Directory -Force -Path $skillsDir | Out-Null
    $skillSources = Get-ChildItem -Path (Join-Path $repo 'skills') -Directory
}
$skillSources | ForEach-Object {
    $link = Join-Path $skillsDir $_.Name
    if (Test-Path $link) {
        $item = Get-Item $link -Force
        $ours = ($item.LinkType -eq 'Junction') -and ($item.Target -like "$repo*")
        if (-not $ours) {
            Write-Host "[skip] skill exists and is not ours -> $link"
            return
        }
        # Delete the link only; Remove-Item -Recurse on a junction can walk into its target.
        $item.Delete()
    }
    try {
        New-Item -ItemType Junction -Path $link -Target $_.FullName | Out-Null
        Write-Host "[ok] skill junction -> $link"
    } catch {
        Copy-Item $_.FullName $link -Recurse
        Write-Host "[ok] skill copied   -> $link (junction unavailable)"
    }
}

# --- links a previous install made into this checkout's skills\ that no longer exist here
# --- (the chief and issue-workflow skills moved to app-launcher-lite): reported, never deleted.
if (-not $shared -and (Test-Path -LiteralPath $skillsDir)) {
    foreach ($item in @(Get-ChildItem -LiteralPath $skillsDir -Force -ErrorAction SilentlyContinue)) {
        $target = [string]($item.Target | Select-Object -First 1)
        if ($item.LinkType -eq 'Junction' -and $target -and $target.StartsWith($repo, [StringComparison]::OrdinalIgnoreCase) -and -not (Test-Path -LiteralPath $target)) {
            Write-Host "[warn] skill link points at a folder this repo no longer has -> $($item.FullName)"
            Write-Host '       app-launcher-lite''s copilot\install.ps1 -Migrate replaces it with its own copy'
        }
    }
}

# --- this checkout's venv: the audit and learning-log helpers are stdlib only, so the
# --- venv holds nothing but the interpreter.
$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
if ($SkipVenv) {
    Write-Host '[skip] venv (-SkipVenv)'
} elseif (Test-Path $venvPython) {
    Write-Host "[ok] venv exists -> $venvPython"
} else {
    & $python -m venv (Join-Path $repo '.venv')
    if (Test-Path $venvPython) { Write-Host "[ok] venv created -> $venvPython" } else { Write-Host '[missing] venv could not be created' }
}

# --- checklist: every line is ok or missing, never assumed. Git access to GitLab, the
# --- session-host and the hooks are app-launcher-lite's checklist, not this one.
if (-not $SkipChecklist) {
    Write-Host ''
    Write-Host 'Checklist:'
    $copilot = Get-Command copilot -ErrorAction SilentlyContinue
    if ($copilot) {
        $version = (& $copilot.Source --version 2>$null | Select-Object -First 1)
        Write-Host "[ok] Copilot CLI -> $version"
    } else {
        Write-Host '[missing] Copilot CLI: install it (winget install GitHub.Copilot), then run copilot login'
    }
    if (Get-Command glab -ErrorAction SilentlyContinue) {
        Write-Host '[ok] glab on PATH (sign-in: glab auth status --hostname <your GitLab host>)'
    } else {
        Write-Host '[missing] glab: install it (winget install GLab.GLab), then run glab auth login'
    }
    if (Test-Path $venvPython) { Write-Host '[ok] venv' } else { Write-Host '[missing] venv: re-run without -SkipVenv' }
}

Write-Host ''
Write-Host 'Done. For the chief, the session hooks and the issue skills, install app-launcher-lite''s copilot\ folder.'
