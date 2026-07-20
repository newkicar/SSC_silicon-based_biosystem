# PostToolUse Hook - Audit + Lint Integration
# Last updated: 2026-07-04

. "$PSScriptRoot/lib/HookParse.ps1"

trap {
    $err = "[PostToolUse] uncaught: $_"
    $err | Out-File -FilePath "$PSScriptRoot\hook_crash.log" -Encoding UTF8 -Append
    exit 0
}

$RuleEngine = @(
    @{
        RuleId        = 'AUDIT-SEC-001'
        Patterns      = @('sk-[a-z0-9]{32,}', 'ghp_[a-zA-Z0-9]{36}', 'AKIA[0-9A-Z]{16}')
        Action        = 'ALERT'
        FixSuggestion = 'Revoke credential, use env vars or a secret manager.'
    },
    @{
        RuleId        = 'AUDIT-CODE-001'
        Patterns      = @('debugger\s*;', 'console\.log\s*\(', '#\s*TODO:\s*remove', '#\s*FIXME:', 'pdb\.set_trace\(\)', 'breakpoint\(\)')
        Action        = 'WARN'
        FixSuggestion = 'Remove debug artifacts before commit.'
    },
    @{
        RuleId        = 'AUDIT-PY-002'
        Patterns      = @('path\s*=\s*["'']C:\\')
        Action        = 'WARN'
        FixSuggestion = 'Use pathlib: Path("data") / "file.csv"'
    }
)

foreach ($rule in $RuleEngine) {
    $compiled = @()
    foreach ($p in $rule.Patterns) {
        $compiled += [regex]::new($p, [System.Text.RegularExpressions.RegexOptions]::Compiled)
    }
    $rule['_CompiledPatterns'] = $compiled
}

function Add-FixSuggestion {
    param([string]$Message, [string]$Suggestion)
    if ([string]::IsNullOrWhiteSpace($Suggestion)) { return $Message }
    return "$Message`nFix: $Suggestion"
}

function Test-CommandAvailable {
    param([string]$CommandName)
    try { Get-Command $CommandName -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

function Invoke-Linter {
    param([string]$FilePath)
    $results = @()
    $ext = [System.IO.Path]::GetExtension($FilePath).ToLower()
    
    # Python: ruff
    if ($ext -eq '.py' -and (Test-CommandAvailable 'ruff')) {
        $out = ruff check "$FilePath" --output-format=text 2>&1
        if ($LASTEXITCODE -gt 0) {
            $results += @([PSCustomObject]@{Tool = 'ruff'; Status = 'FAIL'; Output = $out })
        }
    }
    
    # JS/TS: ESLint (via npx)
    if (($ext -eq '.js' -or $ext -eq '.ts' -or $ext -eq '.jsx' -or $ext -eq '.tsx') -and (Test-CommandAvailable 'npx')) {
        $out = npx eslint --format compact "$FilePath" 2>&1
        if ($LASTEXITCODE -gt 0) {
            $results += @([PSCustomObject]@{Tool = 'eslint'; Status = 'FAIL'; Output = $out })
        }
    }
    
    return $results
}

[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$inputJson = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($inputJson)) { exit 0 }

$ctx = Get-PostToolUseContext -InputJson $inputJson

if ($ctx.parseFallback) {
    $err = '[PostToolUse] JSON parse fallback used'
    $err | Out-File -FilePath "$PSScriptRoot\hook_parse_error.log" -Encoding UTF8 -Append
}

if ($ctx.toolName -notin @('write_to_file', 'edit_file', 'replace_in_file')) { exit 0 }
if (-not $ctx.path -or -not (Test-Path -LiteralPath $ctx.path)) { exit 0 }

$fileInfo = Get-Item -LiteralPath $ctx.path
if ($fileInfo.Length -gt 500KB) { exit 0 }

if ([string]::IsNullOrWhiteSpace($ctx.scanText)) {
    $ctx.scanText = Get-Content -LiteralPath $ctx.path -Raw -Encoding UTF8
}
if ([string]::IsNullOrWhiteSpace($ctx.scanText)) { exit 0 }

$messages = @()
if ($ctx.parseFallback) {
    $messages += 'WARN [AUDIT-SYS-001]: Hook JSON fallback; audited file on disk'
}

foreach ($rule in $RuleEngine) {
    foreach ($regex in $rule._CompiledPatterns) {
        if ($regex.IsMatch($ctx.scanText)) {
            $prefix = switch ($rule.Action) { 'ALERT' { 'ALERT' } default { 'WARN' } }
            $msg = "$prefix [$($rule.RuleId)]: suspicious pattern"
            if ($rule.FixSuggestion) {
                $msg = Add-FixSuggestion -Message $msg -Suggestion $rule.FixSuggestion
            }
            $messages += $msg
            break
        }
    }
}

$linterMessages = @()
if ($ctx.toolName -eq 'write_to_file') {
    $results = Invoke-Linter -FilePath $ctx.path
    foreach ($r in $results) {
        if ($r.Status -eq 'FAIL') {
            $linterMessages += "LINTER [$($r.Tool)]: $($r.Output)"
        }
    }
}

$allMessages = $messages + $linterMessages
if ($allMessages.Count -gt 0) {
    [Console]::Out.WriteLine((@{decisionGuidance = ($allMessages -join "`n")} | ConvertTo-Json -Compress))
}
exit 0
