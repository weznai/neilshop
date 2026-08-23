param(
    [int]$Port = 8000,
    [string]$BindHost = '127.0.0.1',
    [switch]$NoWorker,
    [switch]$NoBrowser,
    [switch]$Reset,
    [switch]$Restart
)

$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }

$Root = $PSScriptRoot
$ServerDir = Join-Path $Root 'server'
$Py = Join-Path $ServerDir '.venv\Scripts\python.exe'
$UvPidFile = Join-Path $Root 'uvicorn.pid'
$WkPidFile = Join-Path $Root 'worker.pid'
$LogDir = Join-Path $env:TEMP 'opencode\glowmag'
$DbUrl = 'mysql+pymysql://glowmag:glowmag123@127.0.0.1:3306/glowmag?charset=utf8mb4'

function Test-PidAlive([int]$Id) {
    if ($Id -le 0) { return $false }
    $p = Get-Process -Id $Id -ErrorAction SilentlyContinue
    return ($null -ne $p -and -not $p.HasExited)
}

function Get-PidFromFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    try {
        return [int]((Get-Content -LiteralPath $Path -ErrorAction Stop | Select-Object -First 1).Trim())
    } catch { return 0 }
}

function Stop-PidSafe([int]$Id) {
    if (-not (Test-PidAlive $Id)) { return }
    $p = Get-Process -Id $Id -ErrorAction SilentlyContinue
    if ($p -and $p.ProcessName -like 'python*') {
        Stop-Process -Id $Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Output ('=' * 64)
Write-Output 'GLOWMAG one-click start (start.ps1)'
Write-Output ('=' * 64)

if (-not (Test-Path -LiteralPath $Py)) {
    Write-Output "[FATAL] venv python not found: $Py"
    Write-Output 'install first:'
    Write-Output '  cd server'
    Write-Output '  python -m venv .venv'
    Write-Output "  .venv\Scripts\pip install -r requirements.txt    # CN mirror: -i https://mirrors.aliyun.com/pypi/simple/"
    exit 1
}
Write-Output "[env] venv python : OK"

$spaFront = Join-Path $Root 'web\dist\index.html'
$spaAdmin = Join-Path $Root 'web\dist\admin\index.html'
if ((Test-Path -LiteralPath $spaFront) -and (Test-Path -LiteralPath $spaAdmin)) {
    Write-Output '[env] web/dist SPA : OK (front / + admin /admin/)'
} else {
    Write-Output '[env] web/dist SPA : MISSING - / and /admin/ will 404 (API still served)'
    Write-Output '       build first at repo root: npm install; npm run build'
}

$mysql = Get-Service -Name 'MySQL80' -ErrorAction SilentlyContinue
if (-not $mysql) { $mysql = Get-Service -Name 'MySQL' -ErrorAction SilentlyContinue }
if (-not $mysql) {
    Write-Output '[FATAL] service MySQL80/MySQL not found (local demo needs MySQL 8, glowmag/glowmag123@127.0.0.1)'
    exit 1
}
if ($mysql.Status -ne 'Running') {
    Write-Output "[env] $($mysql.Name) not running, try Start-Service ..."
    try {
        Start-Service -Name $mysql.Name -ErrorAction Stop
        Start-Sleep -Seconds 2
    } catch {
        Write-Output "[FATAL] Start-Service $($mysql.Name) failed: $($_.Exception.Message)"
        Write-Output "       run as admin or: net start $($mysql.Name)"
        exit 1
    }
}
if ($mysql.Status -ne 'Running') {
    Write-Output '[FATAL] MySQL still not running, abort'
    exit 1
}
Write-Output "[env] $($mysql.Name): Running"

$oldUv = Get-PidFromFile $UvPidFile
$oldWk = Get-PidFromFile $WkPidFile
if ($Restart) {
    if ((Test-PidAlive $oldUv) -or (Test-PidAlive $oldWk)) {
        Write-Output "[restart] -Restart: kill existing uvicorn=$oldUv worker=$oldWk"
        Stop-PidSafe $oldUv
        Stop-PidSafe $oldWk
        Start-Sleep -Milliseconds 800
    }
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.OwningProcess -gt 0) {
            Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
} elseif (Test-PidAlive $oldUv) {
    Write-Output "[skip] uvicorn already running (pid=$oldUv from uvicorn.pid), refuse duplicate start"
    Write-Output "       entry: http://localhost:$Port/  |  stop: .\stop.ps1  |  force restart: .\start.ps1 -Restart"
    exit 0
} else {
    $portOwner = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($portOwner -and $portOwner.OwningProcess -gt 0) {
        Write-Output ("[skip] port {0} already in use by pid={1} (no live uvicorn.pid) - run .\stop.ps1 first or use -Restart" -f $Port, $portOwner.OwningProcess)
        exit 0
    }
}

$probe = @'
try:
    import pymysql
    c = pymysql.connect(host='127.0.0.1', port=3306, user='glowmag',
                        password='glowmag123', database='glowmag', connect_timeout=3)
    cur = c.cursor()
    cur.execute('SELECT COUNT(*) FROM products')
    print('OK:' + str(cur.fetchone()[0]))
except Exception:
    print('NEED_SEED')
'@

$oldDb = $env:GM_DB
$env:GM_DB = $DbUrl
try {
    $productCount = -1
    $probeOut = (& $Py -c $probe) 2>&1 | Out-String
    if ($probeOut -match 'OK:(\d+)') { $productCount = [int]$Matches[1] }

    if ($Reset -or $productCount -le 0) {
        if ($Reset) { Write-Output '[db] -Reset: force reseed (drop_all + seed) ...' }
        elseif ($productCount -eq 0) { Write-Output '[db] products table empty, seeding ...' }
        else { Write-Output '[db] glowmag db/table unreachable, seeding ...' }
        & $Py (Join-Path $ServerDir 'scripts\seed.py') --reset
        if ($LASTEXITCODE -ne 0) {
            Write-Output "[FATAL] seed.py failed (exit=$LASTEXITCODE) - check MySQL80 and glowmag db grants"
            exit 1
        }
        $probeOut2 = (& $Py -c $probe) 2>&1 | Out-String
        if ($probeOut2 -match 'OK:(\d+)') { $productCount = [int]$Matches[1] }
        Write-Output "[db] seed done, products=$productCount"
    } else {
        Write-Output "[db] glowmag db ready, skip seed (products=$productCount)"
    }

    if (-not (Test-Path -LiteralPath $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
    $uvOut = Join-Path $LogDir 'uvicorn.log'
    $uvErr = Join-Path $LogDir 'uvicorn.err.log'
    $wkProc = $null

    $apiProc = Start-Process -FilePath $Py -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', "$BindHost", '--port', "$Port") `
        -WorkingDirectory $ServerDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $uvOut -RedirectStandardError $uvErr
    Set-Content -LiteralPath $UvPidFile -Value $apiProc.Id -Encoding ASCII
    Write-Output ("[api] uvicorn pid={0} host={1} port={2} (log: {3})" -f $apiProc.Id, $BindHost, $Port, $uvErr)

    if ($NoWorker) {
        Write-Output '[worker] -NoWorker: skip background worker'
    } elseif (Test-PidAlive $oldWk) {
        Write-Output "[worker] already running (pid=$oldWk), skip duplicate start"
    } else {
        $wkOut = Join-Path $LogDir 'worker.log'
        $wkErr = Join-Path $LogDir 'worker.err.log'
        $wkProc = Start-Process -FilePath $Py -ArgumentList @('scripts\worker.py', '--loop', '--interval', '60') `
            -WorkingDirectory $ServerDir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $wkOut -RedirectStandardError $wkErr
        Set-Content -LiteralPath $WkPidFile -Value $wkProc.Id -Encoding ASCII
        Write-Output ("[worker] pid={0} (--loop --interval 60, log: {1})" -f $wkProc.Id, $wkErr)
    }
} finally {
    if ($null -ne $oldDb) { $env:GM_DB = $oldDb } else { Remove-Item Env:\GM_DB -ErrorAction SilentlyContinue }
}

Write-Output "[probe] polling http://127.0.0.1:$Port/api/health (max 30s, every 2s) ..."
$ready = $false
$waited = 0
for ($i = 0; $i -lt 15; $i++) {
    Start-Sleep -Seconds 2
    $waited += 2
    if ($apiProc.HasExited) { break }
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200 -and $r.Content -match '"ok":\s*true') { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    Write-Output "[FATAL] /api/health not ready in 30s (uvicorn exited=$($apiProc.HasExited)) - rolling back"
    Write-Output "        error log: $uvErr"
    Stop-PidSafe $apiProc.Id
    if ($wkProc) { Stop-PidSafe $wkProc.Id }
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.OwningProcess -gt 0) { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }
    Remove-Item -LiteralPath $UvPidFile, $WkPidFile -Force -ErrorAction SilentlyContinue
    exit 1
}
Write-Output "[probe] /api/health 200 OK (${waited}s)"

Write-Output ''
Write-Output ('=' * 64)
Write-Output 'READY - entry points'
Write-Output ('=' * 64)
@(
    [pscustomobject]@{ 'entry' = 'home'; 'url' = "http://localhost:$Port/" }
    [pscustomobject]@{ 'entry' = 'admin login'; 'url' = "http://localhost:$Port/admin/" }
    [pscustomobject]@{ 'entry' = 'API docs'; 'url' = "http://localhost:$Port/docs" }
    [pscustomobject]@{ 'entry' = 'metrics'; 'url' = "http://localhost:$Port/metrics" }
) | Format-Table -AutoSize | Out-String -Width 120 | Write-Output

Write-Output "seed account : ops / glowmag123 (quick names admin/ops/cs/emma auto-append @glowmag.com on admin login)"
Write-Output "products     : $productCount"
Write-Output 'stop demo    : .\stop.ps1    (force restart: .\start.ps1 -Restart)'

if ($NoBrowser) {
    Write-Output '[browser] -NoBrowser: skip opening browser'
} else {
    Start-Process "http://localhost:$Port/"
}
