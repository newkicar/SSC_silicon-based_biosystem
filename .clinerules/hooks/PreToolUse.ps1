# .clinerules/hooks/PreToolUse.ps1
# Production Grade - Dual Guardrail (Pre)
# Last updated: 2026-07-05 (P1: modularized rules into lib/PreRules.ps1)

. "$PSScriptRoot/lib/PreRules.ps1"
. "$PSScriptRoot/lib/HookParse.ps1"

$script:StrictMode = $false
$script:CheckDiffOnlyNew = $true
$script:DebugRuleMatch = $false
$script:ExecutionTimeoutSec = 10

# ==================== 核心引擎 ====================

function Add-FixSuggestion {
    param([string]$Message, [string]$Suggestion)
    if ([string]::IsNullOrWhiteSpace($Suggestion)) { return $Message }
    return "$Message`n⚠️ Fix: $Suggestion"
}

function Invoke-ClineGuardrail {
    [CmdletBinding()]
    param()

    [Console]::InputEncoding = [System.Text.Encoding]::UTF8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8

    try {
        $inputJson = [Console]::In.ReadToEnd()
        if ([string]::IsNullOrWhiteSpace($inputJson)) { exit 0 }

        $data = $inputJson | ConvertFrom-Json -ErrorAction Stop
        $hookEvent = $data.preToolUse
        $toolName = $hookEvent.toolName
        $parameters = $hookEvent.parameters
        $filePath = $parameters.path

        # -------- 内容提取 --------
        $contentToCheck = ''
        if ($toolName -eq 'replace_in_file') {
            $diff = $parameters.diff
            if ($script:CheckDiffOnlyNew) {
                try {
                    $m = [regex]::Match($diff, '(?s)=======(.*?)\+{7,}')
                    if ($m.Success) { $contentToCheck = $m.Groups[1].Value.Trim() }
                    else { $contentToCheck = $diff }
                }
                catch { $contentToCheck = $diff }
            }
        }
        elseif ($toolName -eq 'write_to_file') {
            $contentToCheck = $parameters.content
        }

        # -------- 规则执行（按 Action 分类） --------
        $blockReasons = [System.Collections.Generic.List[string]]::new()
        $alertMessages = [System.Collections.Generic.List[string]]::new()
        $warnMessages = [System.Collections.Generic.List[string]]::new()

        foreach ($rule in $script:RuleEngine) {
            if (-not $rule.Enabled) { continue }
            if ($rule.ApplicableTools -ne '*' -and $toolName -notin $rule.ApplicableTools) { continue }

            $ruleHit = $false

            # Path 匹配
            if ($rule.MatchTarget -eq 'Path' -and $filePath -match ($rule.Patterns -join '|')) {
                $ruleHit = $true
            }

            # Content 匹配 + Validation
            if ($rule.MatchTarget -eq 'Content') {
                if ($filePath -match ($rule.Patterns -join '|')) {
                    if ($rule.ValidationLogic) {
                        $errors = & $rule.ValidationLogic $contentToCheck $filePath
                        if ($errors.Count -gt 0) {
                            $ruleHit = $true
                            $errMsg = Add-FixSuggestion -Message "$($rule.ErrorMessage)`n$($errors -join "`n")" -Suggestion $rule.FixSuggestion
                        }
                    }
                    elseif ($contentToCheck -match ($rule.Patterns -join '|')) {
                        $ruleHit = $true
                        $errMsg = Add-FixSuggestion -Message $rule.ErrorMessage -Suggestion $rule.FixSuggestion
                    }
                }
            }

            # 按 Action 分类（Path 和 Content 匹配共用）
            if ($ruleHit) {
                if ($rule.MatchTarget -eq 'Content' -and $ruleHit -and $filePath -match ($rule.Patterns -join '|')) {
                    # Content 匹配：errMsg 已在上面设置
                    $tag = "[$($rule.RuleId)] $errMsg"
                }
                elseif ($rule.MatchTarget -eq 'Path') {
                    # Path 匹配：直接构造消息
                    $tag = "[$($rule.RuleId)] $($rule.ErrorMessage)"
                    if ($rule.FixSuggestion) {
                        $tag = Add-FixSuggestion -Message $tag -Suggestion $rule.FixSuggestion
                    }
                }
                else {
                    $tag = "[$($rule.RuleId)] $($rule.ErrorMessage)"
                }
                switch ($rule.Action) {
                    'BLOCK' { $blockReasons.Add($tag) }
                    'ALERT' { $alertMessages.Add($tag) }
                    'WARN' { $warnMessages.Add($tag) }
                    default { $warnMessages.Add($tag) }
                }
            }

        }

        # 有 BLOCK → 拦截
        if ($blockReasons.Count -gt 0) {
            $allMessages = $blockReasons + $alertMessages + $warnMessages
            Send-Result @{ cancel = $true; errorMessage = ($allMessages -join "`n`n") }
            return
        }

        # 有 ALERT/WARN → 放行但输出提示
        if ($alertMessages.Count -gt 0 -or $warnMessages.Count -gt 0) {
            $guidance = $alertMessages + $warnMessages
            Send-Result @{ cancel = $false; decisionGuidance = ($guidance -join "`n") }
            return
        }

        Send-Result @{ cancel = $false }
    }
    catch {
        if ($script:StrictMode) {
            Send-Result @{ cancel = $true; errorMessage = "PreToolUse Hook error: $_" }
        }
        else {
            Send-Result @{ cancel = $false }
        }
    }
}

function Send-Result { param([hashtable]$Result); Write-Output ($Result | ConvertTo-Json -Compress -Depth 10) }

Invoke-ClineGuardrail