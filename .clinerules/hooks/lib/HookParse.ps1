# Shared JSON/diff parsing for Pre/Post ToolUse hooks (testable)

function Get-ScanTextFromDiff {
    param([string]$Diff)
    if ([string]::IsNullOrWhiteSpace($Diff)) { return '' }
    $m = [regex]::Match($Diff, '(?s)=======\s*\r?\n(.*?)\r?\n\s*\+{7,}\s*REPLACE')
    if ($m.Success) { return $m.Groups[1].Value.Trim() }
    $m2 = [regex]::Match($Diff, '(?s)=======\s*\r?\n(.*)')
    if ($m2.Success) { return $m2.Groups[1].Value.Trim() }
    return $Diff
}

function Repair-HookJson {
    param([string]$Raw)
    return [regex]::Replace($Raw, '(?s)("result"\s*:\s*").*?(",\s*"success")', '${1}${2}')
}

function Get-RegexField {
    param([string]$Raw, [string]$FieldName)
    $pattern = """$FieldName""\s*:\s*""((?:\\.|[^""\\])*)"""
    $m = [regex]::Match($Raw, $pattern)
    if (-not $m.Success) { return $null }
    return ($m.Groups[1].Value -replace '\\/', '/' -replace '\\"', '"' -replace '\\n', "`n" -replace '\\r', "`r" -replace '\\t', "`t")
}

function Get-PostToolUseContext {
    param([string]$InputJson)

    $ctx = @{
        toolName      = $null
        path          = $null
        scanText      = $null
        parseFallback = $false
    }

    $data = $null
    try {
        $data = $InputJson | ConvertFrom-Json -ErrorAction Stop
    }
    catch {
        try {
            $repaired = Repair-HookJson -Raw $InputJson
            $data = $repaired | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            $ctx.parseFallback = $true
            $ctx.toolName = Get-RegexField -Raw $InputJson -FieldName 'toolName'
            $ctx.path = Get-RegexField -Raw $InputJson -FieldName 'path'
            $diff = Get-RegexField -Raw $InputJson -FieldName 'diff'
            if ($diff) { $ctx.scanText = Get-ScanTextFromDiff -Diff $diff }
            $content = Get-RegexField -Raw $InputJson -FieldName 'content'
            if ($content -and [string]::IsNullOrWhiteSpace($ctx.scanText)) { $ctx.scanText = $content }
            return $ctx
        }
    }

    $hookEvent = $data.postToolUse
    if (-not $hookEvent) { return $ctx }

    $ctx.toolName = $hookEvent.toolName
    $ctx.path = $hookEvent.parameters.path

    if ($ctx.toolName -eq 'replace_in_file') {
        $ctx.scanText = Get-ScanTextFromDiff -Diff $hookEvent.parameters.diff
    }
    elseif ($ctx.toolName -eq 'write_to_file') {
        $ctx.scanText = $hookEvent.parameters.content
    }

    return $ctx
}
