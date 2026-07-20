# Pre-compile regex patterns for performance (compiled once, reused every write)
function New-CompiledPatterns {
    param([string[]]$Patterns)
    return @($Patterns | ForEach-Object { [regex]::New($_, [System.Text.RegularExpressions.RegexOptions]::Compiled -bor [System.Text.RegularExpressions.RegexOptions]::IgnoreCase) })
}

$script:RuleEngine = @(
    # ==================== 安全规则 ====================

    # SEC-READ-001: 禁止直接读取敏感配置文件
    # 修改：.env 从 BLOCK 降级为 WARN（开发环境需要读取 .env 调试配置）
    # 保留生产环境配置 (.env.production/.env.staging) 和正式凭据文件为 BLOCK
    @{
        RuleId            = 'SEC-READ-001'
        Name              = 'BlockSensitiveFileRead'
        Description       = 'Block reading production env, credentials, .pem, .key files; WARN on .env'
        Severity          = 'HIGH'
        Scope             = 'FileAccess'
        ApplicableTools   = @('read_file')
        MatchTarget       = 'Path'
        Patterns          = @(
            '(?i)\.env\.production$',
            '(?i)\.env\.staging$',
            '(?i)\.env\.prod$',
            '(?i)credentials?\.json$',
            '(?i)secrets?\.json$',
            '(?i)\.pem$',
            '(?i)\.key$'
        )
        _CompiledPatterns = @()  # filled below
        Action            = 'BLOCK'
        Enabled           = $true
        ErrorMessage      = 'Block reading production env/config, credentials, .pem, .key files. Use env vars or secret manager.'
        FixSuggestion     = 'Use environment variables: os.getenv("DB_PASSWORD") or a secret manager (Azure Key Vault, AWS Secrets Manager).'
    },

    # SEC-READ-WARN-001: 读取 .env 文件时发出警告（允许但提醒）
    @{
        RuleId            = 'SEC-READ-WARN-001'
        Name              = 'WarnDotEnvRead'
        Description       = 'Warn when reading .env files (development env config is OK but remind user)'
        Severity          = 'LOW'
        Scope             = 'FileAccess'
        ApplicableTools   = @('read_file')
        MatchTarget       = 'Path'
        Patterns          = @(
            '(?i)^[./]*\.env$'
        )
        _CompiledPatterns = @()
        Action            = 'WARN'
        Enabled           = $true
        ErrorMessage      = 'Reading .env file detected. This file may contain secrets — ensure it is not committed to version control.'
        FixSuggestion     = 'Verify .env is in .gitignore. Use .env.example as template instead.'
    },

    # ==================== 安全规则 ====================

    # SEC-SQL-001: 禁止 SQL 注入（字符串拼接查询）
    # 对应 00-core §2 安全红线：SQL 必须参数化查询或 ORM
    @{
        RuleId          = 'SEC-SQL-001'
        Name            = 'NoSqlInjectionViaStringConcat'
        Description     = 'Block SQL queries built via string concatenation/formatting'
        Severity        = 'CRITICAL'
        Scope           = 'Security'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.cs$', '\.rb$', '\.php$'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $fileName = [System.IO.Path]::GetFileName($filePath)

            # 跳过测试文件
            if ($fileName -match '(?i)^test_|_test\.|_spec\.') { return @() }

            # 第1层：关键词白名单豁免（变量名以 SAMPLE_/DEMO_/TEST_ 开头）
            if ($content -match '(?i)(sample|demo|test|example|fake|mock)_\w*\s*=.*(?:SELECT|INSERT|UPDATE|DELETE)') {
                return @()
            }

            # 第2层：SQL 注入模式检测
            $sqlInjectionPatterns = @(
                # Python: f"SELECT ... {var}"
                @{ Pattern = '(?i)f["\x27].*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|VALUES).*\{'; Hint = 'Python f-string SQL 拼接' },
                # Python: "...".format(var)
                @{ Pattern = '(?i)["\x27].*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|VALUES).*["\x27]\.format\s*\('; Hint = 'Python .format() SQL 拼接' },
                # Python: "... %s ..." % var
                @{ Pattern = '(?i)["\x27].*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|VALUES).*%\s*s.*["\x27]\s*%\s*'; Hint = 'Python % 格式化 SQL 拼接' },
                # JS/TS: `SELECT ... ${var}`
                @{ Pattern = '(?i)`.*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|VALUES).*\$\{'; Hint = 'JS/TS template literal SQL 拼接' },
                # JS/TS: "SELECT " + var
                @{ Pattern = '(?i)["\x27].*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|VALUES).*["\x27]\s*\+\s*\w+'; Hint = 'JS/TS 字符串拼接 SQL' },
                # Java/C#: "SELECT " + var
                @{ Pattern = '(?i)["\x27].*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE|VALUES).*["\x27]\s*\+\s*\w+'; Hint = 'Java/C# 字符串拼接 SQL' }
            )

            foreach ($pat in $sqlInjectionPatterns) {
                if ($content -match $pat.Pattern) {
                    $errors += "检测到 SQL 注入风险：$($pat.Hint)。必须使用参数化查询或 ORM。"
                }
            }

            return $errors
        }
        ErrorMessage    = '检测到 SQL 字符串拼接模式。00-core §2 安全红线：SQL 必须参数化查询或 ORM。'
        FixSuggestion   = '使用参数化查询：cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,)) 或 ORM：User.objects.filter(id=user_id)'
    },

    # ==================== 格式规则 ====================

    # OPS-FMT-001: Python 文件编码声明建议
    @{
        RuleId          = 'OPS-FMT-001'
        Name            = 'RequireEncodingDeclaration'
        Description     = 'Suggest UTF-8 encoding declaration for Python files'
        Severity        = 'LOW'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$'
        )
        Action          = 'WARN'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $contentLines = $content -split "`n"
            $firstLine = $contentLines[0].Trim()
            if ($firstLine -notmatch '# -\*- coding: utf-8 -\*-' -and
                $firstLine -notmatch '# --\* coding: utf-8 --\*-' -and
                $firstLine -notmatch '^#!' -and
                $firstLine -notmatch '^"""' -and
                $firstLine -notmatch "^'''" -and
                $firstLine -notmatch '^import' -and
                $firstLine -notmatch '^from' -and
                $firstLine -notmatch '^#') {
                $errors += 'Consider adding # -*- coding: utf-8 -*- as first line'
            }
            return $errors
        }
        ErrorMessage    = 'Python encoding check complete, see warning above.'
        FixSuggestion   = 'Add "# -*- coding: utf-8 -*-" as the first line, or use alternative header (shebang, docstring) to declare encoding.'
    },

    # ==================== 代码质量规则 ====================

    # CODE-PY-001: 禁止空的 except — BLOCK（空 except 捕获所有异常包括 KeyboardInterrupt，永远不允许）
    @{
        RuleId          = 'CODE-PY-001'
        Name            = 'NoEmptyExcept'
        Description     = 'Block empty except clauses that silently swallow all exceptions including system-level ones'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            'except\s*:\s*$'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ErrorMessage    = 'Empty except clause detected. This catches ALL exceptions including KeyboardInterrupt and SystemExit. Specify exception type or re-raise.'
        FixSuggestion   = "Replace 'except:' with 'except (ValueError, ConnectionError) as e: logger.error(e); raise'"
    },

    # CODE-PY-002: 宽泛的 Exception 捕获 — WARN（合法但不推荐，应指定具体异常）
    @{
        RuleId          = 'CODE-PY-002'
        Name            = 'BroadExceptWarning'
        Description     = 'Warn on overly broad except Exception: clauses — valid but not recommended'
        Severity        = 'MEDIUM'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            'except\s+Exception\s*(\s+as\s+\w+)?\s*:'
        )
        Action          = 'WARN'
        Enabled         = $true
        ErrorMessage    = 'Broad "except Exception:" detected. While valid, prefer catching specific exception types.'
        FixSuggestion   = "Replace with specific types: 'except (ValueError, KeyError, ConnectionError) as e:'"
    },

    # CODE-JS-001: 禁止 debugger 语句（升级为 BLOCK）
    @{
        RuleId          = 'CODE-JS-001'
        Name            = 'NoDebuggerStatement'
        Description     = 'Block debugger statements left in code'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '^\s*debugger\s*;'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ErrorMessage    = 'Debugger statement detected. Remove before committing.'
        FixSuggestion   = 'Remove the "debugger;" line — it halts execution in DevTools. Use logging or IDE breakpoints instead.'
    },

    # CODE-JS-002: 禁止残留 console.log（测试文件除外）
    @{
        RuleId          = 'CODE-JS-002'
        Name            = 'NoConsoleLogLeftover'
        Description     = 'Warn on console.log statements in non-test files'
        Severity        = 'MEDIUM'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.js$', '\.ts$', '\.jsx$', '\.tsx$'
        )
        Action          = 'WARN'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            # Skip test files
            $fileName = [System.IO.Path]::GetFileName($filePath)
            if ($fileName -match '^test[_\.]') { return @() }
            if ($content -match 'console\.\s*log\s*\(') {
                $errors += 'console.log() detected in non-test file. Use a logging module or remove before committing.'
            }
            return $errors
        }
        ErrorMessage    = 'console.log() detected. Use structured logging for production code.'
        FixSuggestion   = 'Replace with logging module: import logging; logging.info(...) or remove the debug line.'
    },

    # SEC-CODE-001: 禁止硬编码凭据（test file 降级为 WARN，其余 BLOCK）
    @{
        RuleId          = 'SEC-CODE-001'
        Name            = 'NoHardcodedCredentials'
        Description     = 'Block hardcoded passwords, API keys, and tokens'
        Severity        = 'CRITICAL'
        Scope           = 'Security'
        ApplicableTools = @('write_to_file', 'replace_in_file', 'edit_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.rb$', '\.cs$', '\.php$', '\.ps1$'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $fileName = [System.IO.Path]::GetFileName($filePath)

            # ========== 第1层：关键词匹配 ==========
            $sq = [char]39
            $dq = [char]34
            $credPatterns = @(
                "(?i)(password|passwd|pwd)\s*=\s*[$dq$sq]",
                "(?i)(api_key|apikey)\s*=\s*[$dq$sq]",
                "(?i)(secret|token)\s*=\s*[$dq$sq]"
            )
            $hasKeyword = $false
            foreach ($pat in $credPatterns) {
                if ($content -match $pat) { $hasKeyword = $true; break }
            }
            if (-not $hasKeyword) { return @() }

            # ========== 第2层：白名单豁免 ==========
            # 变量名以 SAMPLE_/DEMO_/TEST_/EXAMPLE_/FAKE_/MOCK_ 开头的豁免
            if ($content -match '(?i)(sample|demo|test|example|fake|mock)_\w*\s*=\s*') {
                return @()
            }

            # ========== 第3层：值模式检测 ==========
            # 只有值符合真实凭据模式才拦截
            $sqVal = [char]39
            $dqVal = [char]34
            $realCredPatterns = @(
                # 已知凭据前缀模式
                "(?i)=$dqVal[sqVal]sk-[a-zA-Z0-9]{20,}[$dqVal$sqVal]",           # OpenAI/Stripe key
                "(?i)=$dqVal[sqVal]ghp_[a-zA-Z0-9]{36}[$dqVal$sqVal]",         # GitHub token
                "(?i)=$dqVal[sqVal]AKIA[0-9A-Z]{16}[$dqVal$sqVal]",            # AWS key
                "(?i)=$dqVal[sqVal]xox[baprs]-[a-zA-Z0-9\-]+[$dqVal$sqVal]",   # Slack token
                # 高熵值凭据（随机字符多）
                "(?i)=(?:$dqVal|$sqVal)[a-zA-Z0-9+/]{40,}={0,2}(?:$dqVal|$sqVal)"  # Base64 长串
            )
            $hasRealCred = $false
            foreach ($pat in $realCredPatterns) {
                if ($content -match $pat) { $hasRealCred = $true; break }
            }
            if (-not $hasRealCred) { return @() }

            # Test/conftest files: downgrade to WARN
            if ($fileName -match '^(test_|conftest)') {
                $errors += '[WARN_DOWNGRADE] Test file detected — hardcoded credentials still discouraged but not blocked.'
                return $errors
            }
            $errors += 'Hardcoded credentials detected — not allowed in production code.'
            return $errors
        }
        ErrorMessage    = 'Hardcoded credentials detected. Use env vars or secret manager (AWS Secrets Manager, Azure Key Vault).'
        FixSuggestion   = 'Replace with: password = os.getenv("DB_PASSWORD"). Set the env var in .env (do NOT commit .env).'
    },

    # ==================== Ponytail 黄金原则（OpenAI 工程启发 P0）====================
    # 将 01-ponytail.md 的编码品味编码为可机械执行的规则

    # PT-YAGNI-001: 禁止在未请求的情况下创建新抽象
    # 对应 ponytail: "No abstractions that weren't explicitly requested."
    @{
        RuleId          = 'PT-YAGNI-001'
        Name            = 'NoUnrequestedAbstractions'
        Description     = 'Warn when code introduces classes/interfaces not explicitly requested'
        Severity        = 'MEDIUM'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.tsx$', '\.jsx$'
        )
        Action          = 'WARN'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $ext = [System.IO.Path]::GetExtension($filePath).ToLower()
            if ($ext -eq '.py') {
                $classLines = [regex]::Matches($content, '(?m)^\s*class\s+\w+')
                if ($classLines.Count -gt 0) {
                    $errors += 'New class/interface detected. Per ponytail rule: ensure this abstraction was explicitly requested, not assumed.'
                }
            }
            return $errors
        }
        ErrorMessage    = 'Unrequested abstraction detected. Per ponytail: "No abstractions that were explicitly requested."'
        FixSuggestion   = 'If the class is essential, document why in a comment. Otherwise, prefer standalone functions (YAGNI).'
    },

    # PT-DEP-001: 禁止在未请求的情况下引入新依赖
    # 对应 ponytail: "No new dependency if it can be avoided."
    @{
        RuleId          = 'PT-DEP-001'
        Name            = 'NoUnrequestedDependencies'
        Description     = 'Detect changes to dependency manifest files'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Path'
        Patterns        = @(
            '(?i)(requirements\.txt|pyproject\.toml|setup\.cfg|package\.json|pnpm-lock\.yaml|yarn\.lock|Gemfile|go\.mod|go\.sum)'
        )
        Action          = 'WARN'
        Enabled         = $true
        ErrorMessage    = 'Dependency file changed. Per ponytail: justify why stdlib/existing deps cannot solve this.'
        FixSuggestion   = 'Check stdlib first (e.g. json, csv, pathlib). If truly needed, pin version: "package>=X.Y,<Z.W".'
    },

    # PT-BOILER-001: 禁止生成无人要求的 boilerplate
    # 对应 ponytail: "No boilerplate nobody asked for."
    @{
        RuleId          = 'PT-BOILER-001'
        Name            = 'NoUnrequestedBoilerplate'
        Description     = 'Detect common boilerplate patterns in new files'
        Severity        = 'LOW'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$'
        )
        Action          = 'WARN'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $boilerplatePatterns = @(
                '^class \w+\(.*Factory.*\):',
                '^def __init__\(self.*args=\[\], kwargs=\{\}\):',
                '@(abstractmethod|staticmethod|classmethod).*\s+def \w+.*:.*\s+pass\s*$',
                'try:\s*\n\s*except Exception:\s*\n\s*pass'
            )
            foreach ($bp in $boilerplatePatterns) {
                if ($content -match $bp) {
                    $errors += 'Potential boilerplate detected. Per ponytail: "No boilerplate nobody asked for."'
                    break
                }
            }
            return $errors
        }
        ErrorMessage    = 'Boilerplate pattern detected. Per ponytail: "No boilerplate nobody asked for."'
        FixSuggestion   = 'Remove the boilerplate. Prefer simple functions over Factory/Abstract patterns until the complexity is justified.'
    },

    # PT-MINIMAL-001: 新文件行数警戒线 >500 行（WARN，建议拆分）
    # 对应 ponytail: "Fewest files possible" + "Shortest working diff wins"
    @{
        RuleId          = 'PT-MINIMAL-001'
        Name            = 'FileSizeGuardWarn'
        Description     = 'WARN when file exceeds 500 lines — suggests splitting'
        Severity        = 'LOW'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.rb$', '\.cs$'
        )
        Action          = 'WARN'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $lineCount = ($content -split "`n").Count

            if ($lineCount -gt 500) {
                $errors += "文件 $lineCount 行，超过 500 行建议上限。可以考虑按职责拆分。"
            }

            return $errors
        }
        ErrorMessage    = '文件行数超过 500 行建议上限。'
        FixSuggestion   = '拆分为多个 100-200 行的小文件，按职责组织。参考 00-core §4 单一职责原则。'
    },

    # PT-MINIMAL-002: 新文件行数警戒线 >800 行（ALERT，强烈建议拆分）
    @{
        RuleId          = 'PT-MINIMAL-002'
        Name            = 'FileSizeGuardAlert'
        Description     = 'ALERT when file exceeds 800 lines — strongly suggests splitting'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.rb$', '\.cs$'
        )
        Action          = 'ALERT'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $lineCount = ($content -split "`n").Count

            if ($lineCount -gt 800) {
                $errors += "文件 $lineCount 行，超过 800 行建议上限。强烈建议拆分。"
            }

            return $errors
        }
        ErrorMessage    = '文件行数超过 800 行建议上限，强烈建议拆分。'
        FixSuggestion   = '拆分为多个 100-200 行的小文件，按职责组织。参考 00-core §4 单一职责原则。'
    },

    # PT-MINIMAL-003: 新文件行数警戒线 >1000 行（BLOCK，必须拆分）
    @{
        RuleId          = 'PT-MINIMAL-003'
        Name            = 'FileSizeGuardBlock'
        Description     = 'BLOCK when file exceeds 1000 lines — splitting is mandatory'
        Severity        = 'CRITICAL'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.rb$', '\.cs$'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $lineCount = ($content -split "`n").Count

            if ($lineCount -gt 1000) {
                $errors += "文件 $lineCount 行，超过 1000 行限制。必须拆分为更小模块。"
            }

            return $errors
        }
        ErrorMessage    = '文件行数超过 1000 行限制，必须拆分。'
        FixSuggestion   = '拆分为多个 100-200 行的小文件，按职责组织。参考 00-core §4 单一职责原则。'
    },

    # ==================== Memory Bank 强门禁 ====================

    # MEM-BANK-001: 禁止创建未格式化的 Memory Bank 文件
    @{
        RuleId          = 'MEM-BANK-001'
        Name            = 'RequireMemoryBankHeader'
        Description     = 'New Memory Bank files must have a markdown header'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '^\.clinerules[\\/]memory[\\/](progress|blockers|decisions)\.md$'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            if (-not ($content -match '^#')) {
                $errors += 'Memory Bank file must start with Markdown header (#)'
            }
            return $errors
        }
        ErrorMessage    = 'Memory Bank file must start with # header.'
        FixSuggestion   = 'Add "# " as first line, e.g. "# Progress — YYYY-MM-DD" or "# Decisions — Architecture Decision Records".'
    },

    # MEM-BANK-002: 禁止对 Memory Bank 使用 replace_in_file
    @{
        RuleId          = 'MEM-BANK-002'
        Name            = 'BlockPartialMemoryUpdate'
        Description     = 'Memory Bank must use write_to_file for full overwrite'
        Severity        = 'HIGH'
        Scope           = 'FileAccess'
        ApplicableTools = @('replace_in_file')
        MatchTarget     = 'Path'
        Patterns        = @(
            '^\.clinerules[\\/]memory[\\/](progress|blockers|decisions)\.md$'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ErrorMessage    = 'Memory Bank must use write_to_file for full overwrite. Do not use replace_in_file.'
        FixSuggestion   = 'Use read_file → append to content variable → write_to_file (full overwrite). See session-end.md Phase 3 for the exact pattern.'
    },

    # MEM-BANK-003: Memory Bank 格式校验
    @{
        RuleId          = 'MEM-BANK-003'
        Name            = 'ValidateMemoryBankFormat'
        Description     = 'Validate Memory Bank file format on write'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '^\.clinerules[\\/]memory[\\/](progress|blockers|decisions)\.md$'
        )
        Action          = 'BLOCK'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)

            $errors = @()

            # Template exemption: if content contains placeholder markers, skip strict checks
            $placeholders = @('YYYY-MM-DD', 'AC-\d{3}', 'ADR-\d{4}', '# Title', 'Description \.\.\.')
            $isTemplate = $false
            foreach ($p in $placeholders) {
                if ($content -match $p) { $isTemplate = $true; break }
            }

            $sessionPattern = '^## Session — \d{4}-\d{2}-\d{2} \d{2}:\d{2} ~ \d{2}:\d{2}$'

            if ($filePath -match 'progress\.md$') {
                if (-not ($content -match $sessionPattern) -and -not $isTemplate) {
                    $errors += 'Missing Session Header (## Session — YYYY-MM-DD HH:MM ~ HH:MM)'
                }
                if (-not ($content -match '^### Verification') -and -not $isTemplate) {
                    $errors += 'Missing ### Verification section'
                }
                if (-not ($content -match '^### Next') -and -not $isTemplate) {
                    $errors += 'Missing ### Next section'
                }
            }

            if ($filePath -match 'blockers\.md$') {
                if ($content -match '^\s*-\s*\[\s*\]\s*' -and -not $isTemplate) {
                    $errors += 'blockers.md must not contain unchecked items. Move to progress.md'
                }
            }

            if ($filePath -match 'decisions\.md$') {
                if (-not ($content -match '^## ADR-\d{4}') -and -not $isTemplate) {
                    $errors += 'decisions.md must use ADR-XXXX format for entries'
                }
            }

            return $errors
        }
        ErrorMessage    = 'Memory Bank format validation failed.'
        FixSuggestion   = 'Fix per errors above. See session-end.md for exact format templates for each file type.'
    },

    # ==================== 泛化性规则 ====================

    # GEN-001: 禁止在业务代码中使用典型测试数据/示例值
    # 对应 00-core §3.2 泛化原则
    @{
        RuleId          = 'GEN-001'
        Name            = 'NoTestDataInProductionCode'
        Description     = 'Alert when code uses typical test/example values directly in production code'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.rb$', '\.cs$', '\.php$'
        )
        Action          = 'ALERT'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()

            # 跳过测试文件
            $fileName = [System.IO.Path]::GetFileName($filePath)
            if ($fileName -match '(?i)^test_|_test\.|_spec\.|\bt\b') { return @() }

            # 典型测试数据/示例值模式
            $testPatterns = @(
                # 测试邮箱/用户名
                @{ Pattern = '(?i)test@example\.com|demo@.*\.com|fake@email'; Hint = '测试邮箱' },
                # 测试密码
                @{ Pattern = '(?i)password123|admin123|test123|123456'; Hint = '测试密码' },
                # 测试姓名
                @{ Pattern = '(?i)("John Doe"|Jane Smith|Test User|Fake Name)'; Hint = '测试姓名' },
                # 测试金额
                @{ Pattern = '(?i)(amount\s*[=:]\s*(100|200|1000|99\.99)|price\s*[=:]\s*0)'; Hint = '测试金额' },
                # 示例 URL
                @{ Pattern = 'http://example\.com(/|$)'; Hint = '示例 URL' },
                # 测试 ID 字面量
                @{ Pattern = '"test_id"|"sample_id"|"fake_id"|"placeholder"'; Hint = '测试 ID' }
            )

            foreach ($tp in $testPatterns) {
                if ($content -match $tp.Pattern) {
                    $errors += "可能包含测试数据：$($tp.Hint)"
                }
            }

            return $errors
        }
        ErrorMessage    = '测试数据/示例值检测到生产代码中。请使用配置常量或工厂函数替代。'
        FixSuggestion   = '将测试值抽取为配置常量（如 DEFAULT_EMAIL = "user@example.com"）或使用工厂函数生成测试数据。参考 00-core §3.2 泛化原则。'
    },

    # ==================== 长字符串完整性规则 ====================

    # STR-001: 禁止截断程序运行依赖的长字符串
    # 对应 00-core §3.4 长字符串完整性原则
    @{
        RuleId          = 'STR-001'
        Name            = 'NoTruncatedLongStrings'
        Description     = 'Alert when code contains suspiciously truncated long strings used in program execution'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.sh$', '\.ps1$'
        )
        Action          = 'ALERT'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()

            # 典型截断长字符串模式
            $truncPatterns = @(
                # URL 截断
                @{ Pattern = 'https?://[^"\s]{50,}[^"\s\)]'; Hint = '可能被截断的 URL（>50 字符且无结束符）' },
                # Base64 截断
                @{ Pattern = '[A-Za-z0-9+/]{100,}={0,2}[^A-Za-z0-9+/=]'; Hint = '可能被截断的 Base64 编码' },
                # SQL 查询截断
                @{ Pattern = '(?i)(SELECT|INSERT|UPDATE|DELETE)[^";]{200,}[^";\)]'; Hint = '可能被截断的 SQL 查询' },
                # 文件路径截断（Windows）
                @{ Pattern = 'C:\\[^"\r\n]{100,}[^"\r\n\\]'; Hint = '可能被截断的 Windows 文件路径' },
                # JSON payload 截断
                @{ Pattern = '\{[^"\\]{200,}\}'; Hint = '可能被截断的 JSON payload' }
            )

            foreach ($tp in $truncPatterns) {
                if ($content -match $tp.Pattern) {
                    $errors += "$($tp.Hint)"
                }
            }

            return $errors
        }
        ErrorMessage    = '检测到可能被截断的长字符串。参考 00-core §3.4 长字符串完整性原则。'
        FixSuggestion   = '确认该字符串是否会被程序直接使用（curl/requests/os.path.join/Agent 工具调用）。如是，则完整输出，禁止截断。'
    },

    # ==================== 代码重复检测 ====================

    # DUP-001: 检测文件中函数数量过多时警告（单一职责原则）
    @{
        RuleId          = 'DUP-001'
        Name            = 'TooManyFunctionsInFile'
        Description     = 'Warn when file contains too many function definitions — suggests splitting by responsibility'
        Severity        = 'MEDIUM'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$'
        )
        Action          = 'WARN'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()
            $ext = [System.IO.Path]::GetExtension($filePath).ToLower()
            
            if ($ext -eq '.py') {
                $funcMatches = [regex]::Matches($content, '(?m)^\s*def\s+\w+')
                if ($funcMatches.Count -gt 20) {
                    $errors += "文件包含 $($funcMatches.Count) 个函数，超过 20 个建议上限。考虑按职责拆分模块。"
                }
            }
            elseif ($ext -eq '.js' -or $ext -eq '.ts') {
                # 检测 function/const/arrow function 定义
                $funcMatches = [regex]::Matches($content, '(?m)^\s*(export\s+)?(?:async\s+)?function\s+\w+|^\s*(?:export\s+)?const\s+\w+\s*=\s*(?:async\s+)?\(?.*?\)\s*=>')
                if ($funcMatches.Count -gt 30) {
                    $errors += "文件包含 $($funcMatches.Count) 个函数定义，超过 30 个建议上限。考虑按职责拆分模块。"
                }
            }
            
            return $errors
        }
        ErrorMessage    = '函数数量过多，建议按职责拆分。'
        FixSuggestion   = '将相关函数分组到不同的子模块中。参考 00-core §4 单一职责原则。'
    },

    # ==================== 数据库规则 ====================

    # DB-001: 禁止在启动代码中自动写入种子数据
    # 对应 00-core 新增指导原则：Seed Data 必须显式调用
    @{
        RuleId          = 'DB-001'
        Name            = 'NoAutoSeedDataOnStartup'
        Description     = 'Alert when startup code auto-writes seed/demo data to database'
        Severity        = 'HIGH'
        Scope           = 'CodeQuality'
        ApplicableTools = @('write_to_file', 'replace_in_file')
        MatchTarget     = 'Content'
        Patterns        = @(
            '\.py$', '\.js$', '\.ts$', '\.java$', '\.go$', '\.cs$'
        )
        Action          = 'ALERT'
        Enabled         = $true
        ValidationLogic = {
            param($content, $filePath)
            $errors = @()

            # 典型自动 seed 数据模式：需要同时匹配"空检查"和"写入操作"
            $seedPatterns = @(
                # Python: if db_is_empty() / if not Table.objects.exists() + seed/insert
                @{ Pattern = '(?i)(db_is_empty|table\.objects\.exists|queryset\.count\(\)\s*==\s*0|\.isempty\(\))\s*:?\s*\n\s*.*?(seed|insert|create|populate|bootstrap).*?(demo|initial|fixture|sample)'; Hint = '检测到启动时自动写入种子数据的模式' },
                # JS/TS: if (await collection.count() === 0) + seed/populate
                @{ Pattern = '(?i)(count\(\)\s*===?\s*0|length\s*===?\s*0|isEmpty)\s*\{?.*?(seed|populate|bootstrap).*?(data|demo|initial|fixture)'; Hint = '检测到启动时自动初始化数据的模式' },
                # Java: if (repository.count() == 0) + seed/init
                @{ Pattern = '(?i)(repository|dao)\.\s*(count|exists|findAll)\s*\(\s*\)\s*[=!<>]=?\s*0.*?(seed|init|populate).*?(data|demo|fixture)'; Hint = '检测到启动时自动填充数据的模式' }
            )

            foreach ($sp in $seedPatterns) {
                if ($content -match $sp.Pattern) {
                    $errors += "$($sp.Hint)"
                }
            }

            return $errors
        }
        ErrorMessage    = '检测到启动代码中自动写入种子数据的模式。参考 00-core 指导原则：Seed Data 必须显式调用。'
        FixSuggestion   = '改为显式调用：python manage.py seed_demo_data（通过环境变量或命令行参数控制，不要启动时自动执行）。'
    }
)