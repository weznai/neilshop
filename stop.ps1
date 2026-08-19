$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }

$Root = $PSScriptRoot
$killed = New-Object System.Collections.Generic.List[string]

Write-Output ('=' * 64)
Write-Output 'GLOWMAG one-click stop (stop.ps1)'
Write-Output ('=' * 64)

foreach ($name in @('uvicorn.pid', 'worker.pid')) {
    $file = Join-Path $Root $name
    if (-not (Test-Path -LiteralPath $file)) {
        Write-Output "[pid] $name not found, skip"
        continue
    }
    $id = 0
    try {
        $id = [int]((Get-Content -LiteralPath $file -ErrorAction Stop | Select-Object -First 1).Trim())
    } catch { }
    $p = Get-Process -Id $id -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -like 'python*') {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
        $killed.Add(("$name -> pid=$id"))
        Write-Output "[pid] $name -> Stop-Process pid=$id"
    } elseif ($p) {
        Write-Output "[pid] $name -> pid=$id alive but not python (name=$($p.ProcessName)), skip kill"
    } else {
        Write-Output "[pid] $name -> pid=$id already dead"
    }
    Remove-Item -LiteralPath $file -Force -ErrorAction SilentlyContinue
}

Write-Output '[sweep] scanning leftover python procs (uvicorn app.main / worker.py) ...'
$leftover = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.CommandLine -match 'uvicorn app\.main') -or
        ($_.CommandLine -match '(?<!test_)worker\.py')
    }
if ($leftover) {
    foreach ($w in $leftover) {
        Stop-Process -Id $w.ProcessId -Force -ErrorAction SilentlyContinue
        $killed.Add(("sweep -> pid=$($w.ProcessId)"))
        Write-Output ("[sweep] Stop-Process pid={0} :: {1}" -f $w.ProcessId, $w.CommandLine)
    }
} else {
    Write-Output '[sweep] no leftover process'
}

Start-Sleep -Milliseconds 800
$still = Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
    Where-Object {
        ($_.CommandLine -match 'uvicorn app\.main') -or
        ($_.CommandLine -match '(?<!test_)worker\.py')
    }
Write-Output ''
if ($still) {
    Write-Output ("[done] WARNING: {0} process(es) still alive:" -f @($still).Count)
    foreach ($s in $still) { Write-Output ("       pid={0} :: {1}" -f $s.ProcessId, $s.CommandLine) }
    exit 1
}
Write-Output ("[done] clean. killed this run: {0}" -f ($(if ($killed.Count) { $killed -join '; ' } else { 'none (nothing was running)' })))
exit 0
