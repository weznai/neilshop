param(
    [switch]$Fast,
    [string[]]$Suite
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }

$ServerDir = Join-Path $PSScriptRoot 'server'
$Py = Join-Path $ServerDir '.venv\Scripts\python.exe'
$VerifyPs1 = 'C:\Users\lihui\AppData\Local\Temp\opencode\verify.ps1'
$SlowMark = [char]0x23F1

function Get-SummaryLine([string]$Text) {
    $m = [regex]::Matches($Text, '(?m)(\d+)\s+passed,\s*(\d+)\s+failed')
    if ($m.Count -gt 0) {
        return ('{0}/{1}' -f [int]$m[$m.Count - 1].Groups[1].Value,
            (([int]$m[$m.Count - 1].Groups[1].Value) + ([int]$m[$m.Count - 1].Groups[2].Value)))
    }
    $m = [regex]::Matches($Text, '(?m)(\d+)\s*/\s*(\d+)\s+passed')
    if ($m.Count -gt 0) {
        return ('{0}/{1}' -f [int]$m[$m.Count - 1].Groups[1].Value, [int]$m[$m.Count - 1].Groups[2].Value)
    }
    $m = [regex]::Matches($Text, '(?m)ALL PASS:\s*(\d+)/(\d+)')
    if ($m.Count -gt 0) {
        return ('{0}/{1}' -f [int]$m[$m.Count - 1].Groups[1].Value, [int]$m[$m.Count - 1].Groups[2].Value)
    }
    $m = [regex]::Matches($Text, '(?m)built in [\d.]+s')
    if ($m.Count -gt 0) {
        return ('SPA built ({0}x)' -f $m.Count)
    }
    return ''
}

Write-Output ('=' * 72)
Write-Output 'GLOWMAG one-click regression runner'
Write-Output ('=' * 72)

if (-not (Test-Path -LiteralPath $Py)) {
    Write-Output "[FATAL] venv python not found: $Py"
    exit 1
}
Write-Output "[precheck] venv python : OK"
$mysql = Get-Service -Name 'MySQL80' -ErrorAction SilentlyContinue
if (-not $mysql -or $mysql.Status -ne 'Running') {
    Write-Warning '[precheck] MySQL80 service not running - DB suites will fail naturally'
} else {
    Write-Output '[precheck] MySQL80     : Running'
}
if ($Fast) { Write-Output '[mode] -Fast : skip test_concurrency' }
if ($Suite) { Write-Output ("[mode] -Suite filter: {0}" -f ($Suite -join ', ')) }

$Entries = @()
foreach ($n in @('test_a', 'test_b', 'test_admin_ext', 'test_admin_ops_ext', 'test_c', 'test_ai_ext', 'test_worker', 'test_worker_ext', 'test_refsub', 'test_payments',
'test_obs', 'test_sec', 'test_sec_ext', 'test_perf', 'test_perf_ext', 'test_p0', 'test_p0b', 'test_exchanges',
'test_stocknotify', 'test_emailpref', 'test_digest', 'test_hardening', 'test_cache', 'test_catalog_ext', 'test_tplpreview', 'test_concurrency')) {
    $Entries += [pscustomobject]@{ Name = $n; Slow = ($n -eq 'test_concurrency'); Kind = 'py' }
}
$Entries += [pscustomobject]@{ Name = 'frontend-verify'; Slow = $false; Kind = 'verify' }

if ($Suite) {
    $Entries = @($Entries | Where-Object {
            $e = $_.Name
            @($Suite | Where-Object { $e -like $_ }).Count -gt 0
        })
}
if ($Fast) {
    $Entries = @($Entries | Where-Object { $_.Name -ne 'test_concurrency' })
}
if (-not $Entries -or $Entries.Count -eq 0) {
    Write-Output '[FATAL] no suite matched by -Suite filter'
    exit 1
}

$Results = @()
$TotalSw = [System.Diagnostics.Stopwatch]::StartNew()
foreach ($e in $Entries) {
    $label = if ($e.Slow) { "$($e.Name) $SlowMark" } else { $e.Name }
    Write-Output ''
    Write-Output ('-' * 72)
    Write-Output ">>> $label"
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $out = @()
    $code = 0
    $skip = $false
    if ($e.Kind -eq 'py') {
        $script = Join-Path $ServerDir ("tests\" + $e.Name + ".py")
        & $Py $script 2>&1 | Tee-Object -Variable out
        $code = $LASTEXITCODE
    } elseif ($e.Kind -eq 'verify') {
        # npm workspace 一条命令双 SPA 构建（vite build 含模板/JS 全量编译检查，产物统一 web/dist）
        Push-Location $PSScriptRoot
        npm run build 2>&1 | Tee-Object -Variable out
        $code = $LASTEXITCODE
        Pop-Location
    } else {
        Write-Output "SKIP unknown kind"
        $skip = $true
    }
    $sw.Stop()
    $secs = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    if ($skip) {
        $Results += [pscustomobject]@{ Suite = $label; Secs = $secs; Result = 'SKIP'; Detail = '' }
        continue
    }
    $text = $out | Out-String
    $status = ''
    if ($e.Kind -eq 'verify') {
        $bad = ($code -ne 0) -or ($text -match 'Build failed|error during build')
        $status = if ($bad) { 'FAIL' } else { 'PASS' }
    } else {
        $status = if ($code -eq 0) { 'PASS' } else { 'FAIL' }
    }
    $detail = Get-SummaryLine $text
    $Results += [pscustomobject]@{ Suite = $label; Secs = $secs; Result = $status; Detail = $detail }
}
$TotalSw.Stop()

Write-Output ''
Write-Output ('=' * 72)
Write-Output 'SUMMARY'
Write-Output ('=' * 72)
$Results | Format-Table -AutoSize -Property `
    @{ L = 'Suite'; E = { $_.Suite }; Align = 'Left' }, `
    @{ L = 'Secs'; E = { $_.Secs } }, `
    @{ L = 'Result'; E = { $_.Result } }, `
    @{ L = 'Detail'; E = { $_.Detail } } | Out-String -Width 120 | Write-Output

$failCount = @($Results | Where-Object { $_.Result -eq 'FAIL' }).Count
$passCount = @($Results | Where-Object { $_.Result -eq 'PASS' }).Count
$skipCount = @($Results | Where-Object { $_.Result -eq 'SKIP' }).Count
Write-Output ("total {0} suite(s): {1} PASS / {2} FAIL / {3} SKIP  -  elapsed {4:n1}s" -f `
        $Results.Count, $passCount, $failCount, $skipCount, $TotalSw.Elapsed.TotalSeconds)
if ($failCount -gt 0 -or $passCount -eq 0) { exit 1 }
exit 0
