# install.ps1 - wire fleet-config-lite into GitHub Copilot CLI (user scope).
#
# What it writes, and where:
# 1. Hook configs: renders hooks/session-state.template.json and
#    hooks/chief-guard.template.json with this checkout's absolute path and a
#    resolved Python executable, into %USERPROFILE%\.copilot\hooks\
#    fleet-config-lite-<name>.json, and makes sure hooks\state exists.
# 2. Instructions: links global-instructions.md to
#    %USERPROFILE%\.copilot\copilot-instructions.md (symlink, else a marked copy),
#    only when that path is free or already ours.
# 3. Skills: junctions skills\<name> into %USERPROFILE%\.copilot\skills\<name>,
#    only into a real folder and never over a skill this checkout does not own.
# 4. This checkout's .venv (stdlib only; app-launcher-lite runs the chief
#    helpers through .venv\Scripts\python.exe), unless -SkipVenv.
# 5. A fresh-machine checklist (Copilot CLI, glab and its sign-in, whether git
#    reaches GitLab with no prompt, the venv, app-launcher-lite's session-host),
#    unless -SkipChecklist.
#
# Shared machine: when ~/.copilot/skills or ~/.agents/skills is a link into
# another tree, this PC also runs the full fleet. Then nothing is written that
# would change other sessions: the skills and the instructions link are skipped
# with a message, and the session-state hook is rendered with
# --lite-sessions-only, so it records only sessions app-launcher-lite launched.
# The chief-guard hooks are installed as usual; they act only for lite's chief
# and its lanes and return at once for every other session.
# Any user-scope target that is itself a link into another tree (the Copilot
# home, its hooks folder, a hook config, the skills folder) is never written
# through: it is skipped with a message.
#
# Re-run after moving the checkout or changing the templates. Idempotent.
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
$stateDir = Join-Path $hooksDir 'state'
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

# --- render each hook config with absolute paths (forward slashes keep the
# --- JSON free of escaping headaches). session-state feeds the Board; chief-guard
# --- is the chief's handover, turn-end holds and ask_user deny.
$hooksLink = Get-ForeignLink $hooksDir
if ($hooksLink) {
    Write-Host "[skip] hooks folder is a link into another tree, no hook written -> $hooksDir ($hooksLink)"
} else {
    New-Item -ItemType Directory -Force -Path $hooksDir, $stateDir | Out-Null
    $scope = if ($shared) { ' --lite-sessions-only' } else { '' }
    $hookTemplates = [ordered]@{
        'session-state.template.json' = 'fleet-config-lite-session-state.json'
        'chief-guard.template.json'   = 'fleet-config-lite-chief-guard.json'
    }
    foreach ($name in $hookTemplates.Keys) {
        # Hyphens only in the filename: Copilot CLI 1.0.70 silently ignores hook
        # files with more than one dot in the name (verified live).
        $target = Join-Path $hooksDir $hookTemplates[$name]
        $targetLink = Get-ForeignLink $target
        if ($targetLink) {
            Write-Host "[skip] hook config is a link into another tree -> $target ($targetLink)"
            continue
        }
        $template = Get-Content (Join-Path $repo "hooks\$name") -Raw
        $rendered = $template.Replace('{{PYTHON}}', ($python -replace '\\', '/')).Replace('{{REPO}}', ($repo -replace '\\', '/')).Replace('{{SCOPE}}', $scope)
        # WriteAllText, not Set-Content: under Windows PowerShell 5.1 Set-Content's
        # utf8 writes a BOM, and Copilot CLI 1.0.70 silently ignores BOM'd hook
        # configs (verified live). WriteAllText emits BOM-less UTF-8 on every PS.
        [System.IO.File]::WriteAllText($target, $rendered)
        Write-Host "[ok] hook config -> $target"
    }
    if ($shared) {
        Write-Host '     session-state records only sessions app-launcher-lite launched (--lite-sessions-only);'
        Write-Host '     chief-guard acts only for lite''s chief and its lanes'
    }
}
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

# --- this checkout's venv: app-launcher-lite runs chief_managed.py and the owner
# --- check through .venv\Scripts\python.exe and skips them when it is missing.
# --- The helpers are stdlib only, so the venv holds nothing but the interpreter.
$venvPython = Join-Path $repo '.venv\Scripts\python.exe'
if ($SkipVenv) {
    Write-Host '[skip] venv (-SkipVenv)'
} elseif (Test-Path $venvPython) {
    Write-Host "[ok] venv exists -> $venvPython"
} else {
    & $python -m venv (Join-Path $repo '.venv')
    if (Test-Path $venvPython) { Write-Host "[ok] venv created -> $venvPython" } else { Write-Host '[missing] venv could not be created' }
}

# --- fresh-machine checklist: every line is ok, missing or unknown, never assumed
if (-not $SkipChecklist) {
    Write-Host ''
    Write-Host 'Fresh-machine checklist:'
    $copilot = Get-Command copilot -ErrorAction SilentlyContinue
    if ($copilot) {
        $version = (& $copilot.Source --version 2>$null | Select-Object -First 1)
        Write-Host "[ok] Copilot CLI -> $version"
    } else {
        Write-Host '[missing] Copilot CLI: install it (winget install GitHub.Copilot), then run copilot login'
    }
    $glab = Get-Command glab -ErrorAction SilentlyContinue
    if (-not $glab) {
        Write-Host '[missing] glab: install it (winget install GLab.GLab), then run glab auth login'
    } else {
        # glab prints its status on stderr; under 'Stop', Windows PowerShell 5.1 turns that
        # into a terminating NativeCommandError and the checklist dies here.
        $ErrorActionPreference = 'Continue'
        & $glab.Source auth status *> $null
        $ErrorActionPreference = 'Stop'
        if ($LASTEXITCODE -eq 0) { Write-Host '[ok] glab signed in' } else { Write-Host '[missing] glab is not signed in: run glab auth login' }
    }
    # glab signed in does not mean git can reach GitLab: git asks its own credential
    # helper, and a lane (prompts off) stops on its first fetch. Ask git itself. The
    # fix is printed for the owner to run; this installer never edits git config.
    $accessScript = Join-Path $repo 'skills\_lib\gitlab_git_access.py'
    $access = @{}
    $fixes = @()
    foreach ($line in @(& $python $accessScript check --repo $repo 2>$null)) {
        $key, $value = ([string]$line) -split '=', 2
        if ($key -eq 'FIX') { $fixes += $value } else { $access[$key] = $value }
    }
    switch ($access['GIT_ACCESS']) {
        'ok' { Write-Host "[ok] git reaches GitLab without a prompt -> $($access['HOST'])" }
        'missing' {
            Write-Host "[missing] git cannot reach GitLab without a prompt ($($access['HOST'])): $($access['REASON'])"
            Write-Host '          glab being signed in is not enough: git uses its own credential helper. Run this yourself (the installer never edits your git config):'
            foreach ($fix in $fixes) { Write-Host "            $fix" }
            Write-Host '          then re-run install.ps1; this line should read [ok]'
        }
        default {
            $why = if ($access['REASON']) { $access['REASON'] } else { 'the check did not run' }
            Write-Host "[unknown] git access to GitLab not confirmed: $why"
        }
    }
    if (Test-Path $venvPython) { Write-Host '[ok] venv' } else { Write-Host '[missing] venv: re-run without -SkipVenv' }
    try {
        Invoke-WebRequest -Uri 'http://127.0.0.1:8466/sessions' -UseBasicParsing -TimeoutSec 2 | Out-Null
        Write-Host '[ok] app-launcher-lite session-host answers on :8466'
    } catch {
        Write-Host '[unknown] app-launcher-lite session-host not reachable on :8466 (start its tray)'
    }
    Write-Host '[next] restart any running Copilot CLI session, then run: python scripts\copilot_probe.py run --live'
}

Write-Host ''
Write-Host 'Done. Restart any running Copilot CLI session to pick up the hooks.'
Write-Host "State file will appear at: $stateDir\sessions-state.json"
